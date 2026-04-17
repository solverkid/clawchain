package service_test

import (
	"context"
	"net/http"
	"testing"
	"time"

	"github.com/clawchain/clawchain/pokermtt/service"
	"github.com/clawchain/clawchain/pokermtt/sidecar"
	"github.com/stretchr/testify/require"
)

func TestOrchestratorMapsRuntimeStatesAndCancelsWithoutLeakingDTOs(t *testing.T) {
	t.Helper()

	client := &fakeRuntimeClient{
		startResp: sidecar.StartResponse{
			TournamentID:  "t-1",
			RoutingRoomID: "room-1",
			State:         "sidecar_starting",
		},
		cancelResp: sidecar.CancelResponse{
			TournamentID: "t-1",
			State:        "cancelled",
		},
	}
	orch := service.Orchestrator{
		Client: client,
		WS:     &fakeWSConnector{},
	}

	started, err := orch.Start(context.Background(), "t-1")
	require.NoError(t, err)
	require.Equal(t, service.RuntimeStateSidecarStarting, started.State)
	require.Equal(t, "room-1", started.RoutingRoomID)

	cancelled, err := orch.Cancel(context.Background(), "t-1", "manual_review")
	require.NoError(t, err)
	require.Equal(t, service.RuntimeStateCancelled, cancelled.State)
	require.Equal(t, "t-1", cancelled.TournamentID)
}

func TestOrchestratorRequeriesRoomOnReconnectAndUsesReentry(t *testing.T) {
	t.Helper()

	client := &fakeRuntimeClient{
		rooms: []sidecar.RoomResponse{
			{
				TournamentID:  "t-1",
				UserID:        "7",
				RoutingRoomID: "room-1",
				TableID:       "table-1",
				State:         "running",
			},
			{
				TournamentID:  "t-1",
				UserID:        "7",
				RoutingRoomID: "room-2",
				TableID:       "table-2",
				State:         "running",
			},
		},
		reentries: []sidecar.ReentryResponse{
			{
				TournamentID:  "t-1",
				UserID:        "7",
				SessionID:     "session-reentry",
				RoutingRoomID: "room-1",
				State:         "seating_ready",
			},
			{
				TournamentID:  "t-1",
				UserID:        "7",
				SessionID:     "session-reentry",
				RoutingRoomID: "room-2",
				State:         "seating_ready",
			},
		},
	}
	ws := &fakeWSConnector{}
	fixed := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	orch := service.Orchestrator{
		Client: client,
		WS:     ws,
		Now:    func() time.Time { return fixed },
	}

	req := service.SessionRequest{
		TournamentID:  "t-1",
		UserID:        "7",
		PlayerName:    "tester",
		Authorization: "Bearer local-user:7",
		MockUserID:    "7",
		SessionKey:    "session-001",
		Reentry:       true,
		EntryNumber:   2,
	}

	first, err := orch.AcquireSession(context.Background(), req)
	require.NoError(t, err)
	require.Equal(t, service.RuntimeStateSeatingReady, first.State)
	require.Equal(t, "room-1", first.RoutingRoomID)
	require.Equal(t, "session-reentry", first.SessionID)
	require.Equal(t, "room-1", ws.lastConnect.RoutingRoomID)

	second, err := orch.AcquireSession(context.Background(), req)
	require.NoError(t, err)
	require.Equal(t, service.RuntimeStateSeatingReady, second.State)
	require.Equal(t, "room-2", second.RoutingRoomID)
	require.Equal(t, "session-reentry", second.SessionID)
	require.Equal(t, "room-2", ws.lastConnect.RoutingRoomID)
	require.Equal(t, 2, client.roomCalls)
	require.Equal(t, 2, client.reentryCalls)
	require.Equal(t, fixed, client.lastReentryRequest.RequestedAt)
}

func TestOrchestratorEntryNumberOneUsesInitialJoin(t *testing.T) {
	t.Helper()

	client := &fakeRuntimeClient{
		rooms: []sidecar.RoomResponse{
			{
				TournamentID:  "t-1",
				UserID:        "7",
				RoutingRoomID: "room-1",
				TableID:       "table-1",
				State:         "running",
			},
		},
		joinResp: sidecar.JoinResponse{
			TournamentID:  "t-1",
			UserID:        "7",
			SessionID:     "session-join",
			RoutingRoomID: "room-1",
			State:         "seating_ready",
		},
	}
	orch := service.Orchestrator{
		Client: client,
		WS:     &fakeWSConnector{},
	}

	handle, err := orch.AcquireSession(context.Background(), service.SessionRequest{
		TournamentID:  "t-1",
		UserID:        "7",
		PlayerName:    "tester",
		Authorization: "Bearer local-user:7",
		MockUserID:    "7",
		SessionKey:    "session-001",
		EntryNumber:   1,
	})

	require.NoError(t, err)
	require.Equal(t, "session-join", handle.SessionID)
	require.Equal(t, 1, client.joinCalls)
	require.Equal(t, 0, client.reentryCalls)
	require.Equal(t, "room-1", client.lastJoinRequest.RoutingRoomID)
}

func TestOrchestratorRejectsRetryForBettingActions(t *testing.T) {
	t.Helper()

	orch := service.Orchestrator{}
	require.False(t, orch.CanRetryAction("bet"))
	require.False(t, orch.CanRetryAction("raise"))
	require.False(t, orch.CanRetryAction("call"))
	require.True(t, orch.CanRetryAction("ping"))
}

type fakeRuntimeClient struct {
	startResp  sidecar.StartResponse
	rooms      []sidecar.RoomResponse
	joinResp   sidecar.JoinResponse
	reentries  []sidecar.ReentryResponse
	cancelResp sidecar.CancelResponse
	healthResp sidecar.HealthResponse

	roomCalls    int
	joinCalls    int
	reentryCalls int
	cancelCalls  int
	healthCalls  int

	lastRoomRequest    sidecar.RoomRequest
	lastJoinRequest    sidecar.JoinRequest
	lastReentryRequest sidecar.ReentryRequest
}

func (c *fakeRuntimeClient) Start(context.Context, sidecar.StartRequest) (sidecar.StartResponse, error) {
	return c.startResp, nil
}

func (c *fakeRuntimeClient) GetRoom(_ context.Context, req sidecar.RoomRequest) (sidecar.RoomResponse, error) {
	c.roomCalls++
	c.lastRoomRequest = req
	if len(c.rooms) == 0 {
		return sidecar.RoomResponse{}, nil
	}
	resp := c.rooms[0]
	c.rooms = c.rooms[1:]
	return resp, nil
}

func (c *fakeRuntimeClient) Join(_ context.Context, req sidecar.JoinRequest) (sidecar.JoinResponse, error) {
	c.joinCalls++
	c.lastJoinRequest = req
	return c.joinResp, nil
}

func (c *fakeRuntimeClient) Reentry(_ context.Context, req sidecar.ReentryRequest) (sidecar.ReentryResponse, error) {
	c.reentryCalls++
	c.lastReentryRequest = req
	if len(c.reentries) == 0 {
		return sidecar.ReentryResponse{}, nil
	}
	resp := c.reentries[0]
	c.reentries = c.reentries[1:]
	return resp, nil
}

func (c *fakeRuntimeClient) Cancel(context.Context, sidecar.CancelRequest) (sidecar.CancelResponse, error) {
	c.cancelCalls++
	return c.cancelResp, nil
}

func (c *fakeRuntimeClient) Health(context.Context) (sidecar.HealthResponse, error) {
	c.healthCalls++
	return c.healthResp, nil
}

type fakeWSConnector struct {
	lastConnect service.PlayerConnectionRequest
}

func (c *fakeWSConnector) PlayerConnection(req service.PlayerConnectionRequest) (service.PlayerConnection, error) {
	c.lastConnect = req
	headers := make(http.Header)
	if req.Authorization != "" {
		headers.Set("Authorization", req.Authorization)
	}
	if req.MockUserID != "" {
		headers.Set("Mock-Userid", req.MockUserID)
	}
	return service.PlayerConnection{
		URL:           "ws://example.invalid/v1/ws?id=" + req.TournamentID + "&type=mtt",
		Headers:       map[string][]string(headers),
		Subprotocols:  []string{"-1", req.SessionID},
		RoutingRoomID: req.RoutingRoomID,
	}, nil
}
