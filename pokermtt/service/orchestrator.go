package service

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/clawchain/clawchain/pokermtt/sidecar"
)

var ErrUnknownRuntimeState = errors.New("unknown runtime state")

type RuntimeState string

const (
	RuntimeStateScheduled          RuntimeState = "scheduled"
	RuntimeStateStartRequested     RuntimeState = "start_requested"
	RuntimeStateSidecarStarting    RuntimeState = "sidecar_starting"
	RuntimeStateSeatingReady       RuntimeState = "seating_ready"
	RuntimeStateRunning            RuntimeState = "running"
	RuntimeStateFinalizing         RuntimeState = "finalizing"
	RuntimeStateStandingsReady     RuntimeState = "standings_ready"
	RuntimeStateCompleted          RuntimeState = "completed"
	RuntimeStateFailedToStart      RuntimeState = "failed_to_start"
	RuntimeStateCancelled          RuntimeState = "cancelled"
	RuntimeStateVoid               RuntimeState = "void"
	RuntimeStateDegraded           RuntimeState = "degraded"
	RuntimeStateManualReview       RuntimeState = "manual_review"
	RuntimeStateConflict           RuntimeState = "conflict"
	RuntimeStateCorrectionRequired RuntimeState = "correction_required"
)

type RuntimeClient interface {
	Start(context.Context, sidecar.StartRequest) (sidecar.StartResponse, error)
	GetRoom(context.Context, sidecar.RoomRequest) (sidecar.RoomResponse, error)
	Join(context.Context, sidecar.JoinRequest) (sidecar.JoinResponse, error)
	Reentry(context.Context, sidecar.ReentryRequest) (sidecar.ReentryResponse, error)
	Cancel(context.Context, sidecar.CancelRequest) (sidecar.CancelResponse, error)
	Health(context.Context) (sidecar.HealthResponse, error)
}

type WSConnector interface {
	PlayerConnection(PlayerConnectionRequest) (PlayerConnection, error)
}

type Orchestrator struct {
	Client RuntimeClient
	WS     WSConnector
	Now    func() time.Time
}

type StartStatus struct {
	TournamentID  string
	RoutingRoomID string
	State         RuntimeState
}

type CancelStatus struct {
	TournamentID string
	State        RuntimeState
}

type HealthStatus struct {
	Healthy bool
	Status  string
}

type SessionRequest struct {
	TournamentID  string
	UserID        string
	PlayerName    string
	Authorization string
	MockUserID    string
	SessionKey    string
	Reentry       bool
	EntryNumber   int
}

type PlayerConnectionRequest struct {
	TournamentID  string
	UserID        string
	RoutingRoomID string
	SessionID     string
	Authorization string
	MockUserID    string
}

type PlayerConnection struct {
	URL           string
	Headers       map[string][]string
	Subprotocols  []string
	RoutingRoomID string
}

type SessionHandle struct {
	TournamentID  string
	UserID        string
	RoutingRoomID string
	SessionID     string
	State         RuntimeState
	Connection    PlayerConnection
}

type SidecarWSConnector struct {
	Connector interface {
		ConnectSpec(sidecar.ConnectRequest) (sidecar.ConnectSpec, error)
	}
}

func (c SidecarWSConnector) PlayerConnection(req PlayerConnectionRequest) (PlayerConnection, error) {
	if c.Connector == nil {
		return PlayerConnection{}, errors.New("missing sidecar ws connector")
	}
	spec, err := c.Connector.ConnectSpec(sidecar.ConnectRequest{
		TournamentID:  req.TournamentID,
		UserID:        req.UserID,
		RoutingRoomID: req.RoutingRoomID,
		SessionID:     req.SessionID,
		Authorization: req.Authorization,
		MockUserID:    req.MockUserID,
	})
	if err != nil {
		return PlayerConnection{}, err
	}
	return PlayerConnection{
		URL:           spec.URL,
		Headers:       map[string][]string(spec.Headers),
		Subprotocols:  append([]string(nil), spec.Subprotocols...),
		RoutingRoomID: spec.RoutingRoomID,
	}, nil
}

func (o Orchestrator) Start(ctx context.Context, tournamentID string) (StartStatus, error) {
	if o.Client == nil {
		return StartStatus{}, errors.New("missing runtime client")
	}
	resp, err := o.Client.Start(ctx, sidecar.StartRequest{TournamentID: tournamentID})
	if err != nil {
		return StartStatus{}, err
	}
	state, err := mapRuntimeState(resp.State)
	if err != nil {
		return StartStatus{}, err
	}
	return StartStatus{
		TournamentID:  resp.TournamentID,
		RoutingRoomID: resp.RoutingRoomID,
		State:         state,
	}, nil
}

func (o Orchestrator) Cancel(ctx context.Context, tournamentID, reason string) (CancelStatus, error) {
	if o.Client == nil {
		return CancelStatus{}, errors.New("missing runtime client")
	}
	resp, err := o.Client.Cancel(ctx, sidecar.CancelRequest{TournamentID: tournamentID, Reason: reason})
	if err != nil {
		return CancelStatus{}, err
	}
	state, err := mapRuntimeState(resp.State)
	if err != nil {
		return CancelStatus{}, err
	}
	return CancelStatus{
		TournamentID: resp.TournamentID,
		State:        state,
	}, nil
}

func (o Orchestrator) Health(ctx context.Context) (HealthStatus, error) {
	if o.Client == nil {
		return HealthStatus{}, errors.New("missing runtime client")
	}
	resp, err := o.Client.Health(ctx)
	if err != nil {
		return HealthStatus{}, err
	}
	return HealthStatus{
		Healthy: resp.Healthy,
		Status:  resp.Status,
	}, nil
}

func (o Orchestrator) AcquireSession(ctx context.Context, req SessionRequest) (SessionHandle, error) {
	if o.Client == nil || o.WS == nil {
		return SessionHandle{}, errors.New("missing runtime adapters")
	}

	room, err := o.Client.GetRoom(ctx, sidecar.RoomRequest{
		TournamentID: req.TournamentID,
		UserID:       req.UserID,
	})
	if err != nil {
		return SessionHandle{}, err
	}

	var admission sidecar.JoinResponse
	requestedAt := o.now()
	if req.Reentry || req.EntryNumber > 1 {
		reentry, err := o.Client.Reentry(ctx, sidecar.ReentryRequest{
			TournamentID:  req.TournamentID,
			UserID:        req.UserID,
			EntryNumber:   req.EntryNumber,
			Authorization: req.Authorization,
			MockUserID:    req.MockUserID,
			SessionKey:    req.SessionKey,
			RoutingRoomID: room.RoutingRoomID,
			RequestedAt:   requestedAt,
		})
		if err != nil {
			return SessionHandle{}, err
		}
		admission = sidecar.JoinResponse(reentry)
	} else {
		joined, err := o.Client.Join(ctx, sidecar.JoinRequest{
			TournamentID:  req.TournamentID,
			UserID:        req.UserID,
			PlayerName:    req.PlayerName,
			Authorization: req.Authorization,
			MockUserID:    req.MockUserID,
			SessionKey:    req.SessionKey,
			RoutingRoomID: room.RoutingRoomID,
			RequestedAt:   requestedAt,
		})
		if err != nil {
			return SessionHandle{}, err
		}
		admission = joined
	}

	routingRoomID := room.RoutingRoomID
	if admission.RoutingRoomID != "" {
		routingRoomID = admission.RoutingRoomID
	}

	connection, err := o.WS.PlayerConnection(PlayerConnectionRequest{
		TournamentID:  req.TournamentID,
		UserID:        req.UserID,
		RoutingRoomID: routingRoomID,
		SessionID:     admission.SessionID,
		Authorization: req.Authorization,
		MockUserID:    req.MockUserID,
	})
	if err != nil {
		return SessionHandle{}, err
	}

	stateRaw := admission.State
	if strings.TrimSpace(stateRaw) == "" {
		stateRaw = room.State
	}
	state, err := mapRuntimeState(stateRaw)
	if err != nil {
		return SessionHandle{}, err
	}

	return SessionHandle{
		TournamentID:  req.TournamentID,
		UserID:        req.UserID,
		RoutingRoomID: routingRoomID,
		SessionID:     admission.SessionID,
		State:         state,
		Connection:    connection,
	}, nil
}

func (o Orchestrator) now() time.Time {
	if o.Now != nil {
		return o.Now().UTC()
	}
	return time.Now().UTC()
}

func (o Orchestrator) CanRetryAction(action string) bool {
	switch normalizeActionName(action) {
	case "bet", "raise", "call", "check", "fold", "all_in":
		return false
	default:
		return true
	}
}

func mapRuntimeState(raw string) (RuntimeState, error) {
	switch normalizeStateName(raw) {
	case string(RuntimeStateScheduled):
		return RuntimeStateScheduled, nil
	case string(RuntimeStateStartRequested):
		return RuntimeStateStartRequested, nil
	case string(RuntimeStateSidecarStarting):
		return RuntimeStateSidecarStarting, nil
	case string(RuntimeStateSeatingReady):
		return RuntimeStateSeatingReady, nil
	case string(RuntimeStateRunning):
		return RuntimeStateRunning, nil
	case string(RuntimeStateFinalizing):
		return RuntimeStateFinalizing, nil
	case string(RuntimeStateStandingsReady):
		return RuntimeStateStandingsReady, nil
	case string(RuntimeStateCompleted), "finished":
		return RuntimeStateCompleted, nil
	case string(RuntimeStateFailedToStart), "start_failed":
		return RuntimeStateFailedToStart, nil
	case string(RuntimeStateCancelled), "canceled":
		return RuntimeStateCancelled, nil
	case string(RuntimeStateVoid):
		return RuntimeStateVoid, nil
	case string(RuntimeStateDegraded):
		return RuntimeStateDegraded, nil
	case string(RuntimeStateManualReview):
		return RuntimeStateManualReview, nil
	case string(RuntimeStateConflict):
		return RuntimeStateConflict, nil
	case string(RuntimeStateCorrectionRequired):
		return RuntimeStateCorrectionRequired, nil
	default:
		return "", ErrUnknownRuntimeState
	}
}

func normalizeStateName(raw string) string {
	normalized := strings.TrimSpace(strings.ToLower(raw))
	normalized = strings.ReplaceAll(normalized, "-", "_")
	normalized = strings.ReplaceAll(normalized, " ", "_")
	return normalized
}

func normalizeActionName(raw string) string {
	normalized := strings.TrimSpace(strings.ToLower(raw))
	normalized = strings.ReplaceAll(normalized, "-", "_")
	normalized = strings.ReplaceAll(normalized, " ", "_")
	return normalized
}
