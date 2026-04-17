package sidecar

import (
	"errors"
	"net/http"
	"net/url"
	"strings"

	"github.com/clawchain/clawchain/pokermtt/model"
)

type WS struct {
	BaseURL string
}

type ConnectRequest struct {
	TournamentID  string
	UserID        string
	RoutingRoomID string
	SessionID     string
	Authorization string
	MockUserID    string
}

type ConnectSpec struct {
	URL           string
	Headers       http.Header
	Subprotocols  []string
	RoutingRoomID string
}

func (w WS) ConnectSpec(req ConnectRequest) (ConnectSpec, error) {
	if strings.TrimSpace(req.TournamentID) == "" || strings.TrimSpace(req.SessionID) == "" {
		return ConnectSpec{}, &RequestError{Op: "ws_connect", Method: http.MethodGet, URL: w.wsURL(req.TournamentID), Err: ErrInvalidConfiguration}
	}

	specURL, err := w.connectURL(req.TournamentID)
	if err != nil {
		return ConnectSpec{}, &RequestError{Op: "ws_connect", Method: http.MethodGet, URL: w.wsURL(req.TournamentID), Err: ErrInvalidConfiguration}
	}

	headers := make(http.Header)
	if req.Authorization != "" {
		headers.Set("Authorization", req.Authorization)
	}
	if req.MockUserID != "" {
		headers.Set(model.MockUserIDHeader, req.MockUserID)
	}
	if req.RoutingRoomID != "" {
		headers.Set(routingRoomHeaderName, req.RoutingRoomID)
	}

	return ConnectSpec{
		URL:           specURL,
		Headers:       headers,
		Subprotocols:  []string{wsTokenFromAuthorization(req.Authorization), req.SessionID},
		RoutingRoomID: req.RoutingRoomID,
	}, nil
}

func (w WS) connectURL(tournamentID string) (string, error) {
	trimmed := strings.TrimSpace(w.BaseURL)
	if trimmed == "" {
		return "", errors.New("missing websocket base url")
	}
	base, err := url.Parse(trimmed)
	if err != nil {
		return "", err
	}
	switch base.Scheme {
	case "http":
		base.Scheme = "ws"
	case "https":
		base.Scheme = "wss"
	case "ws", "wss":
	default:
		return "", errors.New("unsupported websocket base url scheme")
	}
	base.Path = strings.TrimRight(base.Path, "/") + "/v1/ws"
	query := base.Query()
	query.Set("id", tournamentID)
	query.Set("type", model.GameTypeMTT)
	base.RawQuery = query.Encode()
	return base.String(), nil
}

func (w WS) wsURL(tournamentID string) string {
	if strings.TrimSpace(w.BaseURL) == "" {
		return "/v1/ws?id=" + url.QueryEscape(strings.TrimSpace(tournamentID)) + "&type=" + model.GameTypeMTT
	}
	parsed, err := w.connectURL(tournamentID)
	if err != nil {
		return "/v1/ws?id=" + url.QueryEscape(strings.TrimSpace(tournamentID)) + "&type=" + model.GameTypeMTT
	}
	return parsed
}

func wsTokenFromAuthorization(authorization string) string {
	token := strings.TrimSpace(authorization)
	if token == "" {
		return "-1"
	}
	token = strings.TrimSpace(strings.TrimPrefix(token, "Bearer "))
	if token == "" {
		return "-1"
	}
	return token
}
