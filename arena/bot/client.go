package bot

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
)

var (
	ErrNotFound = errors.New("arena resource not found")
	ErrConflict = errors.New("arena state conflict")
)

type Client struct {
	baseURL      string
	tournamentID string
	minerID      string
	httpClient   *http.Client
}

type SeatAssignment struct {
	TableID   string `json:"table_id"`
	SeatNo    int    `json:"seat_no"`
	StateSeq  int64  `json:"state_seq"`
	ReadOnly  bool   `json:"read_only"`
	SessionID string `json:"session_id,omitempty"`
}

type VisibleStack struct {
	SeatNo    int    `json:"seat_no"`
	SeatState string `json:"seat_state"`
	Stack     int64  `json:"stack"`
}

type SeatPublicAction struct {
	SeatNo            int   `json:"seat_no"`
	CommittedThisHand int64 `json:"committed_this_hand"`
	Folded            bool  `json:"folded"`
	AllIn             bool  `json:"all_in"`
	TimedOutThisHand  bool  `json:"timed_out_this_hand"`
	ManualAction      bool  `json:"manual_action"`
}

type LiveTable struct {
	ActingSeatNo      int                `json:"acting_seat_no"`
	LevelNo           int                `json:"level_no"`
	SmallBlind        int64              `json:"small_blind"`
	BigBlind          int64              `json:"big_blind"`
	Ante              int64              `json:"ante"`
	PotMain           int64              `json:"pot_main"`
	CurrentPhase      string             `json:"current_phase"`
	CurrentToCall     int64              `json:"current_to_call"`
	MinRaiseSize      int64              `json:"min_raise_size"`
	MinRaiseTo        int64              `json:"min_raise_to"`
	MaxRaiseTo        int64              `json:"max_raise_to"`
	HandNumber        int                `json:"hand_number"`
	StateSeq          int64              `json:"state_seq"`
	LegalActions      []string           `json:"legal_actions"`
	VisibleStacks     []VisibleStack     `json:"visible_stacks"`
	SeatPublicActions []SeatPublicAction `json:"seat_public_actions"`
}

type Standing struct {
	Status           string `json:"status"`
	CompletedReason  string `json:"completed_reason"`
	PlayersRemaining int    `json:"players_remaining"`
	WinnerMinerID    string `json:"winner_miner_id"`
}

type Decision struct {
	ActionType string
	Amount     int64
	Reason     string
}

func NewClient(baseURL, tournamentID, minerID string) *Client {
	return NewClientWithHTTP(baseURL, tournamentID, minerID, nil)
}

func NewClientWithHTTP(baseURL, tournamentID, minerID string, httpClient *http.Client) *Client {
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	return &Client{
		baseURL:      strings.TrimRight(baseURL, "/"),
		tournamentID: tournamentID,
		minerID:      minerID,
		httpClient:   httpClient,
	}
}

func (c *Client) Standing(ctx context.Context) (Standing, error) {
	var standing Standing
	err := c.get(ctx, fmt.Sprintf("/v1/tournaments/%s/standing", c.tournamentID), &standing)
	return standing, err
}

func (c *Client) SeatAssignment(ctx context.Context) (SeatAssignment, error) {
	var assignment SeatAssignment
	err := c.get(ctx, fmt.Sprintf("/v1/tournaments/%s/seat-assignment/%s", c.tournamentID, c.minerID), &assignment)
	return assignment, err
}

func (c *Client) LiveTable(ctx context.Context, tableID string) (LiveTable, error) {
	var liveTable LiveTable
	err := c.get(ctx, fmt.Sprintf("/v1/tournaments/%s/live-table/%s", c.tournamentID, tableID), &liveTable)
	return liveTable, err
}

func (c *Client) Reconnect(ctx context.Context, sessionID string) (SeatAssignment, error) {
	var assignment SeatAssignment
	payload := map[string]string{
		"miner_id":   c.minerID,
		"session_id": sessionID,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return assignment, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+fmt.Sprintf("/v1/tournaments/%s/sessions/reconnect", c.tournamentID), bytes.NewReader(body))
	if err != nil {
		return assignment, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return assignment, err
	}
	defer resp.Body.Close()

	err = decodeArenaResponse(resp, &assignment)
	return assignment, err
}

func (c *Client) SubmitAction(ctx context.Context, assignment SeatAssignment, decision Decision, requestID string) error {
	payload := map[string]any{
		"request_id":         requestID,
		"table_id":           assignment.TableID,
		"miner_id":           c.minerID,
		"session_id":         assignment.SessionID,
		"seat_no":            assignment.SeatNo,
		"action_type":        decision.ActionType,
		"amount":             decision.Amount,
		"expected_state_seq": assignment.StateSeq,
		"signature":          fmt.Sprintf("sig:%s", c.minerID),
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+fmt.Sprintf("/v1/tournaments/%s/actions", c.tournamentID), bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	return decodeArenaResponse(resp, nil)
}

func (c *Client) get(ctx context.Context, path string, target any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return err
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	return decodeArenaResponse(resp, target)
}

func decodeArenaResponse(resp *http.Response, target any) error {
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	switch resp.StatusCode {
	case http.StatusOK:
		if target == nil {
			return nil
		}
		return json.Unmarshal(body, target)
	case http.StatusNotFound:
		return ErrNotFound
	case http.StatusConflict:
		return ErrConflict
	default:
		var payload struct {
			Error string `json:"error"`
		}
		if err := json.Unmarshal(body, &payload); err == nil && payload.Error != "" {
			return fmt.Errorf("arena request failed (%d): %s", resp.StatusCode, payload.Error)
		}
		return fmt.Errorf("arena request failed (%d): %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
}
