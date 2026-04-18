package sidecar

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/clawchain/clawchain/pokermtt/model"
)

const (
	defaultRequestTimeout = 5 * time.Second
	defaultRetryAttempts  = 3
	defaultRetryBackoff   = 25 * time.Millisecond

	routingRoomHeaderName = "X-Poker-MTT-Routing-Room-ID"
)

var (
	ErrInvalidConfiguration = errors.New("invalid sidecar configuration")
	ErrInvalidResponse      = errors.New("invalid sidecar response")
	ErrUnexpectedStatus     = errors.New("unexpected sidecar status")
	ErrTimeout              = errors.New("sidecar request timeout")
)

type RequestError struct {
	Op         string
	Method     string
	URL        string
	StatusCode int
	Timeout    bool
	Message    string
	Err        error
}

func (e *RequestError) Error() string {
	if e == nil {
		return "<nil>"
	}
	switch {
	case e.Timeout:
		return fmt.Sprintf("%s %s %s: timeout", e.Op, e.Method, e.URL)
	case e.StatusCode > 0 && e.Message != "":
		return fmt.Sprintf("%s %s %s: status %d: %s", e.Op, e.Method, e.URL, e.StatusCode, e.Message)
	case e.StatusCode > 0:
		return fmt.Sprintf("%s %s %s: status %d: %v", e.Op, e.Method, e.URL, e.StatusCode, e.Err)
	default:
		return fmt.Sprintf("%s %s %s: %v", e.Op, e.Method, e.URL, e.Err)
	}
}

func (e *RequestError) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Err
}

func (e *RequestError) Is(target error) bool {
	switch target {
	case ErrTimeout:
		return e != nil && e.Timeout
	case ErrInvalidConfiguration, ErrInvalidResponse, ErrUnexpectedStatus:
		return e != nil && errors.Is(e.Err, target)
	default:
		return false
	}
}

type Client struct {
	ControlBaseURL string
	PlayerBaseURL  string
	HTTPClient     *http.Client
	Timeout        time.Duration
}

type StartRequest struct {
	TournamentID string
}

type StartResponse struct {
	TournamentID  string
	RoutingRoomID string
	State         string
}

type RoomRequest struct {
	TournamentID string
	UserID       string
}

type RoomResponse struct {
	TournamentID  string
	UserID        string
	RoutingRoomID string
	TableID       string
	State         string
}

type JoinRequest struct {
	TournamentID  string
	UserID        string
	PlayerName    string
	Authorization string
	MockUserID    string
	SessionKey    string
	RoutingRoomID string
	RequestedAt   time.Time
}

type JoinResponse struct {
	TournamentID  string
	UserID        string
	SessionID     string
	RoutingRoomID string
	State         string
}

type ReentryRequest struct {
	TournamentID  string
	UserID        string
	EntryNumber   int
	Authorization string
	MockUserID    string
	SessionKey    string
	RoutingRoomID string
	RequestedAt   time.Time
}

type ReentryResponse = JoinResponse

type CancelRequest struct {
	TournamentID string
	Reason       string
}

type CancelResponse struct {
	TournamentID string
	State        string
}

type HealthResponse struct {
	Healthy bool
	Status  string
}

type envelope struct {
	Code    int             `json:"code"`
	Msg     string          `json:"msg"`
	Success bool            `json:"success"`
	Data    json.RawMessage `json:"data"`
}

type startData struct {
	TournamentID string `json:"tournamentID"`
	RoomID       string `json:"roomID"`
	State        string `json:"state"`
}

type roomData struct {
	TournamentID string `json:"tournamentID"`
	UserID       string `json:"userID"`
	RoomID       string `json:"roomID"`
	TableID      string `json:"tableID"`
	State        string `json:"state"`
}

type admissionData struct {
	TournamentID string `json:"tournamentID"`
	UserID       string `json:"userID"`
	SessionID    string `json:"sessionID"`
	RoomID       string `json:"roomID"`
	State        string `json:"state"`
}

type cancelData struct {
	TournamentID string `json:"tournamentID"`
	State        string `json:"state"`
}

type healthData struct {
	Status string `json:"status"`
}

func (c Client) Start(ctx context.Context, req StartRequest) (StartResponse, error) {
	rawURL, urlErr := c.controlURL(model.DonorStartMTTPath)
	if urlErr != nil {
		return StartResponse{}, &RequestError{Op: "start", Method: http.MethodPost, URL: model.DonorStartMTTPath, Err: urlErr}
	}
	if strings.TrimSpace(req.TournamentID) == "" {
		return StartResponse{}, &RequestError{Op: "start", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidConfiguration}
	}

	env, err := c.postEnvelope(ctx, "start", rawURL, map[string]any{
		"ID":   req.TournamentID,
		"type": model.GameTypeMTT,
	}, func(r *http.Request) {
		r.Header.Set("Idempotency-Key", fmt.Sprintf("poker_mtt:start:%s", req.TournamentID))
	})
	if err != nil {
		return StartResponse{}, err
	}

	data, err := decodeData[startData](env.Data)
	if err != nil {
		return StartResponse{}, &RequestError{Op: "start", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidResponse}
	}
	return StartResponse{
		TournamentID:  firstNonEmpty(data.TournamentID, req.TournamentID),
		RoutingRoomID: data.RoomID,
		State:         data.State,
	}, nil
}

func (c Client) GetRoom(ctx context.Context, req RoomRequest) (RoomResponse, error) {
	rawURL, urlErr := c.controlURL(model.DonorGetMTTRoomByIDPath)
	if urlErr != nil {
		return RoomResponse{}, &RequestError{Op: "get_room", Method: http.MethodGet, URL: model.DonorGetMTTRoomByIDPath, Err: urlErr}
	}
	if strings.TrimSpace(req.TournamentID) == "" || strings.TrimSpace(req.UserID) == "" {
		return RoomResponse{}, &RequestError{Op: "get_room", Method: http.MethodGet, URL: rawURL, Err: ErrInvalidConfiguration}
	}

	u, err := url.Parse(rawURL)
	if err != nil {
		return RoomResponse{}, &RequestError{Op: "get_room", Method: http.MethodGet, URL: rawURL, Err: ErrInvalidConfiguration}
	}
	query := u.Query()
	query.Set("ID", req.TournamentID)
	query.Set("userID", req.UserID)
	u.RawQuery = query.Encode()

	env, err := c.getEnvelope(ctx, "get_room", u.String(), nil)
	if err != nil {
		return RoomResponse{}, err
	}

	data, err := decodeData[roomData](env.Data)
	if err != nil {
		return RoomResponse{}, &RequestError{Op: "get_room", Method: http.MethodGet, URL: u.String(), Err: ErrInvalidResponse}
	}
	return RoomResponse{
		TournamentID:  firstNonEmpty(data.TournamentID, req.TournamentID),
		UserID:        firstNonEmpty(data.UserID, req.UserID),
		RoutingRoomID: data.RoomID,
		TableID:       data.TableID,
		State:         data.State,
	}, nil
}

func (c Client) Join(ctx context.Context, req JoinRequest) (JoinResponse, error) {
	rawURL, urlErr := c.playerURL(model.DonorJoinGamePath)
	if urlErr != nil {
		return JoinResponse{}, &RequestError{Op: "join", Method: http.MethodPost, URL: model.DonorJoinGamePath, Err: urlErr}
	}
	if strings.TrimSpace(req.TournamentID) == "" || strings.TrimSpace(req.UserID) == "" {
		return JoinResponse{}, &RequestError{Op: "join", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidConfiguration}
	}
	if req.RequestedAt.IsZero() {
		return JoinResponse{}, &RequestError{Op: "join", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidConfiguration}
	}

	body := map[string]any{
		"playerName": req.PlayerName,
		"time":       requestUnix(req.RequestedAt),
		"userID":     req.UserID,
	}
	if req.RoutingRoomID != "" {
		body["roomID"] = req.RoutingRoomID
	}

	u, err := url.Parse(rawURL)
	if err != nil {
		return JoinResponse{}, &RequestError{Op: "join", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidConfiguration}
	}
	query := u.Query()
	query.Set("id", req.TournamentID)
	query.Set("type", model.GameTypeMTT)
	u.RawQuery = query.Encode()

	env, err := c.postEnvelope(ctx, "join", u.String(), body, func(r *http.Request) {
		r.Header.Set("Idempotency-Key", fmt.Sprintf("poker_mtt:join:%s:%s:%s", req.TournamentID, req.UserID, joinSessionKey(req)))
		if req.Authorization != "" {
			r.Header.Set("Authorization", req.Authorization)
		}
		if req.MockUserID != "" {
			r.Header.Set(model.MockUserIDHeader, req.MockUserID)
		}
		if req.RoutingRoomID != "" {
			r.Header.Set(routingRoomHeaderName, req.RoutingRoomID)
		}
	})
	if err != nil {
		return JoinResponse{}, err
	}

	data, err := decodeData[admissionData](env.Data)
	if err != nil {
		return JoinResponse{}, &RequestError{Op: "join", Method: http.MethodPost, URL: u.String(), Err: ErrInvalidResponse}
	}
	return JoinResponse{
		TournamentID:  firstNonEmpty(data.TournamentID, req.TournamentID),
		UserID:        firstNonEmpty(data.UserID, req.UserID),
		SessionID:     data.SessionID,
		RoutingRoomID: data.RoomID,
		State:         data.State,
	}, nil
}

func (c Client) Reentry(ctx context.Context, req ReentryRequest) (ReentryResponse, error) {
	rawURL, urlErr := c.controlURL(model.DonorReentryMTTGamePath)
	if urlErr != nil {
		return ReentryResponse{}, &RequestError{Op: "reentry", Method: http.MethodPost, URL: model.DonorReentryMTTGamePath, Err: urlErr}
	}
	if strings.TrimSpace(req.TournamentID) == "" || strings.TrimSpace(req.UserID) == "" {
		return ReentryResponse{}, &RequestError{Op: "reentry", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidConfiguration}
	}
	if req.RequestedAt.IsZero() {
		return ReentryResponse{}, &RequestError{Op: "reentry", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidConfiguration}
	}

	body := map[string]any{
		"ID":          req.TournamentID,
		"type":        model.GameTypeMTT,
		"entryNumber": req.EntryNumber,
		"time":        requestUnix(req.RequestedAt),
		"userID":      req.UserID,
	}
	if req.RoutingRoomID != "" {
		body["roomID"] = req.RoutingRoomID
	}

	env, err := c.postEnvelope(ctx, "reentry", rawURL, body, func(r *http.Request) {
		r.Header.Set("Idempotency-Key", fmt.Sprintf("poker_mtt:reentry:%s:%s:%d", req.TournamentID, req.UserID, req.EntryNumber))
		if req.Authorization != "" {
			r.Header.Set("Authorization", req.Authorization)
		}
		if req.MockUserID != "" {
			r.Header.Set(model.MockUserIDHeader, req.MockUserID)
		}
		if req.RoutingRoomID != "" {
			r.Header.Set(routingRoomHeaderName, req.RoutingRoomID)
		}
	})
	if err != nil {
		return ReentryResponse{}, err
	}

	data, err := decodeData[admissionData](env.Data)
	if err != nil {
		return ReentryResponse{}, &RequestError{Op: "reentry", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidResponse}
	}
	return ReentryResponse{
		TournamentID:  firstNonEmpty(data.TournamentID, req.TournamentID),
		UserID:        firstNonEmpty(data.UserID, req.UserID),
		SessionID:     data.SessionID,
		RoutingRoomID: data.RoomID,
		State:         data.State,
	}, nil
}

func (c Client) Cancel(ctx context.Context, req CancelRequest) (CancelResponse, error) {
	rawURL, urlErr := c.controlURL(model.DonorCancelMTTPath)
	if urlErr != nil {
		return CancelResponse{}, &RequestError{Op: "cancel", Method: http.MethodPost, URL: model.DonorCancelMTTPath, Err: urlErr}
	}
	if strings.TrimSpace(req.TournamentID) == "" {
		return CancelResponse{}, &RequestError{Op: "cancel", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidConfiguration}
	}

	env, err := c.postEnvelope(ctx, "cancel", rawURL, map[string]any{
		"ID":     req.TournamentID,
		"type":   model.GameTypeMTT,
		"reason": req.Reason,
	}, func(r *http.Request) {
		r.Header.Set("Idempotency-Key", fmt.Sprintf("poker_mtt:cancel:%s", req.TournamentID))
	})
	if err != nil {
		return CancelResponse{}, err
	}

	data, err := decodeData[cancelData](env.Data)
	if err != nil {
		return CancelResponse{}, &RequestError{Op: "cancel", Method: http.MethodPost, URL: rawURL, Err: ErrInvalidResponse}
	}
	return CancelResponse{
		TournamentID: firstNonEmpty(data.TournamentID, req.TournamentID),
		State:        data.State,
	}, nil
}

func (c Client) Health(ctx context.Context) (HealthResponse, error) {
	ctx, cancel := c.withTimeout(ctx)
	defer cancel()

	url, urlErr := c.playerURL("/v1/hello")
	if urlErr != nil {
		return HealthResponse{}, &RequestError{Op: "health", Method: http.MethodGet, URL: "/v1/hello", Err: urlErr}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return HealthResponse{}, &RequestError{Op: "health", Method: http.MethodGet, URL: url, Err: err}
	}

	resp, err := c.httpClient().Do(req)
	if err != nil {
		return HealthResponse{}, c.wrapError("health", http.MethodGet, url, err, 0)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return HealthResponse{}, &RequestError{Op: "health", Method: http.MethodGet, URL: url, StatusCode: resp.StatusCode, Err: err}
	}

	trimmed := strings.TrimSpace(string(raw))
	if trimmed == "ok" {
		return HealthResponse{Healthy: true, Status: "ok"}, nil
	}

	env, err := decodeEnvelope(raw)
	if err != nil {
		return HealthResponse{}, &RequestError{Op: "health", Method: http.MethodGet, URL: url, StatusCode: resp.StatusCode, Err: ErrInvalidResponse}
	}
	if resp.StatusCode >= http.StatusBadRequest || !env.Success || env.Code != 0 {
		return HealthResponse{}, c.statusError("health", http.MethodGet, url, resp.StatusCode, env.Msg)
	}

	data, err := decodeData[healthData](env.Data)
	if err != nil {
		return HealthResponse{}, &RequestError{Op: "health", Method: http.MethodGet, URL: url, StatusCode: resp.StatusCode, Err: ErrInvalidResponse}
	}
	return HealthResponse{
		Healthy: true,
		Status:  data.Status,
	}, nil
}

func (c Client) postEnvelope(ctx context.Context, op, rawURL string, body any, configure func(*http.Request)) (envelope, error) {
	payload, err := json.Marshal(body)
	if err != nil {
		return envelope{}, &RequestError{Op: op, Method: http.MethodPost, URL: rawURL, Err: err}
	}

	return c.retryEnvelope(ctx, func() (envelope, error) {
		return c.postEnvelopeOnce(ctx, op, rawURL, payload, configure)
	})
}

func (c Client) postEnvelopeOnce(ctx context.Context, op, rawURL string, payload []byte, configure func(*http.Request)) (envelope, error) {
	ctx, cancel := c.withTimeout(ctx)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, rawURL, bytes.NewReader(payload))
	if err != nil {
		return envelope{}, &RequestError{Op: op, Method: http.MethodPost, URL: rawURL, Err: err}
	}
	req.Header.Set("Content-Type", "application/json")
	if configure != nil {
		configure(req)
	}

	resp, err := c.httpClient().Do(req)
	if err != nil {
		return envelope{}, c.wrapError(op, http.MethodPost, rawURL, err, 0)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return envelope{}, &RequestError{Op: op, Method: http.MethodPost, URL: rawURL, StatusCode: resp.StatusCode, Err: err}
	}
	env, err := decodeEnvelope(raw)
	if err != nil {
		return envelope{}, &RequestError{Op: op, Method: http.MethodPost, URL: rawURL, StatusCode: resp.StatusCode, Err: ErrInvalidResponse}
	}
	if resp.StatusCode >= http.StatusBadRequest || !env.Success || env.Code != 0 {
		return envelope{}, c.statusError(op, http.MethodPost, rawURL, resp.StatusCode, env.Msg)
	}
	return env, nil
}

func (c Client) getEnvelope(ctx context.Context, op, rawURL string, configure func(*http.Request)) (envelope, error) {
	return c.retryEnvelope(ctx, func() (envelope, error) {
		return c.getEnvelopeOnce(ctx, op, rawURL, configure)
	})
}

func (c Client) getEnvelopeOnce(ctx context.Context, op, rawURL string, configure func(*http.Request)) (envelope, error) {
	ctx, cancel := c.withTimeout(ctx)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return envelope{}, &RequestError{Op: op, Method: http.MethodGet, URL: rawURL, Err: err}
	}
	if configure != nil {
		configure(req)
	}

	resp, err := c.httpClient().Do(req)
	if err != nil {
		return envelope{}, c.wrapError(op, http.MethodGet, rawURL, err, 0)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return envelope{}, &RequestError{Op: op, Method: http.MethodGet, URL: rawURL, StatusCode: resp.StatusCode, Err: err}
	}
	env, err := decodeEnvelope(raw)
	if err != nil {
		return envelope{}, &RequestError{Op: op, Method: http.MethodGet, URL: rawURL, StatusCode: resp.StatusCode, Err: ErrInvalidResponse}
	}
	if resp.StatusCode >= http.StatusBadRequest || !env.Success || env.Code != 0 {
		return envelope{}, c.statusError(op, http.MethodGet, rawURL, resp.StatusCode, env.Msg)
	}
	return env, nil
}

func (c Client) retryEnvelope(ctx context.Context, call func() (envelope, error)) (envelope, error) {
	var lastErr error
	for attempt := 1; attempt <= defaultRetryAttempts; attempt++ {
		env, err := call()
		if err == nil {
			return env, nil
		}
		lastErr = err
		if attempt == defaultRetryAttempts || !isRetryableSidecarError(err) {
			return envelope{}, err
		}
		if err := sleepRetryBackoff(ctx, attempt); err != nil {
			return envelope{}, err
		}
	}
	return envelope{}, lastErr
}

func isRetryableSidecarError(err error) bool {
	var reqErr *RequestError
	if !errors.As(err, &reqErr) {
		return false
	}
	if reqErr.Timeout {
		return true
	}
	switch reqErr.StatusCode {
	case http.StatusTooManyRequests, http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return true
	default:
		return false
	}
}

func sleepRetryBackoff(ctx context.Context, attempt int) error {
	if ctx == nil {
		ctx = context.Background()
	}
	delay := time.Duration(attempt) * defaultRetryBackoff
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-timer.C:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (c Client) withTimeout(ctx context.Context) (context.Context, context.CancelFunc) {
	if ctx == nil {
		ctx = context.Background()
	}
	timeout := c.Timeout
	if timeout <= 0 {
		timeout = defaultRequestTimeout
	}
	return context.WithTimeout(ctx, timeout)
}

func (c Client) httpClient() *http.Client {
	if c.HTTPClient != nil {
		return c.HTTPClient
	}
	return http.DefaultClient
}

func (c Client) controlURL(path string) (string, error) {
	return joinBaseURL(c.ControlBaseURL, path)
}

func (c Client) playerURL(path string) (string, error) {
	return joinBaseURL(c.PlayerBaseURL, path)
}

func (c Client) wrapError(op, method, rawURL string, err error, statusCode int) error {
	reqErr := &RequestError{
		Op:         op,
		Method:     method,
		URL:        rawURL,
		StatusCode: statusCode,
		Err:        err,
	}
	if isTimeoutError(err) {
		reqErr.Timeout = true
	}
	return reqErr
}

func (c Client) statusError(op, method, rawURL string, statusCode int, message string) error {
	if message == "" {
		message = ErrUnexpectedStatus.Error()
	}
	return &RequestError{
		Op:         op,
		Method:     method,
		URL:        rawURL,
		StatusCode: statusCode,
		Message:    message,
		Err:        ErrUnexpectedStatus,
	}
}

func decodeEnvelope(raw []byte) (envelope, error) {
	var env envelope
	if err := json.Unmarshal(raw, &env); err != nil {
		return envelope{}, err
	}
	return env, nil
}

func decodeData[T any](raw json.RawMessage) (T, error) {
	var out T
	if len(bytes.TrimSpace(raw)) == 0 {
		return out, ErrInvalidResponse
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return out, err
	}
	return out, nil
}

func joinBaseURL(baseURL, path string) (string, error) {
	trimmed := strings.TrimSpace(baseURL)
	if trimmed == "" {
		return "", ErrInvalidConfiguration
	}
	parsed, err := url.Parse(trimmed)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return "", ErrInvalidConfiguration
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + path
	return parsed.String(), nil
}

func requestUnix(requestedAt time.Time) int64 {
	return requestedAt.UTC().Unix()
}

func joinSessionKey(req JoinRequest) string {
	if trimmed := strings.TrimSpace(req.SessionKey); trimmed != "" {
		return trimmed
	}
	if trimmed := strings.TrimSpace(req.RoutingRoomID); trimmed != "" {
		return trimmed
	}
	if trimmed := strings.TrimSpace(req.UserID); trimmed != "" {
		return trimmed
	}
	return "session"
}

func isTimeoutError(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	var netErr net.Error
	if errors.As(err, &netErr) && netErr.Timeout() {
		return true
	}
	return false
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
