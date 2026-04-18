package sidecar_test

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/clawchain/clawchain/pokermtt/sidecar"
	"github.com/stretchr/testify/require"
)

func TestClientStartUsesControlSurfaceAndIdempotency(t *testing.T) {
	t.Helper()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "/v1/mtt/start", r.URL.Path)
		require.Equal(t, "poker_mtt:start:t-1", r.Header.Get("Idempotency-Key"))

		payload := decodeJSONBody(t, r)
		require.Equal(t, "t-1", payload["ID"])
		require.Equal(t, "mtt", payload["type"])

		writeJSON(t, w, map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data": map[string]any{
				"tournamentID": "t-1",
				"roomID":       "room-1",
				"state":        "sidecar_starting",
			},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        time.Second,
	}

	resp, err := client.Start(context.Background(), sidecar.StartRequest{TournamentID: "t-1"})
	require.NoError(t, err)
	require.Equal(t, "t-1", resp.TournamentID)
	require.Equal(t, "room-1", resp.RoutingRoomID)
	require.Equal(t, "sidecar_starting", resp.State)
}

func TestClientGetRoomQueriesCurrentRoom(t *testing.T) {
	t.Helper()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodGet, r.Method)
		require.Equal(t, "/v1/mtt/getMTTRoomByID", r.URL.Path)
		require.Equal(t, "t-1", r.URL.Query().Get("ID"))
		require.Equal(t, "7", r.URL.Query().Get("userID"))

		writeJSON(t, w, map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data": map[string]any{
				"tournamentID": "t-1",
				"userID":       "7",
				"roomID":       "room-1",
				"tableID":      "table-1",
				"state":        "running",
			},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        time.Second,
	}

	resp, err := client.GetRoom(context.Background(), sidecar.RoomRequest{
		TournamentID: "t-1",
		UserID:       "7",
	})
	require.NoError(t, err)
	require.Equal(t, "t-1", resp.TournamentID)
	require.Equal(t, "7", resp.UserID)
	require.Equal(t, "room-1", resp.RoutingRoomID)
	require.Equal(t, "table-1", resp.TableID)
	require.Equal(t, "running", resp.State)
}

func TestClientJoinUsesPlayerSurfaceAndIdempotency(t *testing.T) {
	t.Helper()

	fixed := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "/v1/join_game", r.URL.Path)
		require.Equal(t, "t-1", r.URL.Query().Get("id"))
		require.Equal(t, "mtt", r.URL.Query().Get("type"))
		require.Equal(t, "Bearer local-user:7", r.Header.Get("Authorization"))
		require.Equal(t, "7", r.Header.Get("Mock-Userid"))
		require.Equal(t, "poker_mtt:join:t-1:7:session-001", r.Header.Get("Idempotency-Key"))
		require.Equal(t, "room-1", r.Header.Get("X-Poker-MTT-Routing-Room-ID"))

		payload := decodeJSONBody(t, r)
		require.Equal(t, "tester", payload["playerName"])
		require.Equal(t, "7", payload["userID"])
		require.Equal(t, "room-1", payload["roomID"])
		require.Equal(t, float64(fixed.Unix()), payload["time"])

		writeJSON(t, w, map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data": map[string]any{
				"tournamentID": "t-1",
				"userID":       "7",
				"roomID":       "room-1",
				"sessionID":    "session-abc",
				"state":        "running",
			},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        time.Second,
	}

	resp, err := client.Join(context.Background(), sidecar.JoinRequest{
		TournamentID:  "t-1",
		UserID:        "7",
		PlayerName:    "tester",
		Authorization: "Bearer local-user:7",
		MockUserID:    "7",
		SessionKey:    "session-001",
		RoutingRoomID: "room-1",
		RequestedAt:   fixed,
	})
	require.NoError(t, err)
	require.Equal(t, "t-1", resp.TournamentID)
	require.Equal(t, "7", resp.UserID)
	require.Equal(t, "room-1", resp.RoutingRoomID)
	require.Equal(t, "session-abc", resp.SessionID)
	require.Equal(t, "running", resp.State)
}

func TestClientReentryUsesControlSurfaceAndIdempotency(t *testing.T) {
	t.Helper()

	fixed := time.Date(2026, 4, 14, 10, 5, 0, 0, time.UTC)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "/v1/mtt/reentryMTTGame", r.URL.Path)
		require.Equal(t, "poker_mtt:reentry:t-1:7:2", r.Header.Get("Idempotency-Key"))
		require.Equal(t, "room-2", r.Header.Get("X-Poker-MTT-Routing-Room-ID"))

		payload := decodeJSONBody(t, r)
		require.Equal(t, "7", payload["userID"])
		require.Equal(t, float64(2), payload["entryNumber"])
		require.Equal(t, "room-2", payload["roomID"])
		require.Equal(t, float64(fixed.Unix()), payload["time"])

		writeJSON(t, w, map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data": map[string]any{
				"tournamentID": "t-1",
				"userID":       "7",
				"roomID":       "room-2",
				"sessionID":    "session-reentry",
				"state":        "seating_ready",
			},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        time.Second,
	}

	resp, err := client.Reentry(context.Background(), sidecar.ReentryRequest{
		TournamentID:  "t-1",
		UserID:        "7",
		EntryNumber:   2,
		Authorization: "Bearer local-user:7",
		MockUserID:    "7",
		RoutingRoomID: "room-2",
		RequestedAt:   fixed,
	})
	require.NoError(t, err)
	require.Equal(t, "session-reentry", resp.SessionID)
	require.Equal(t, "room-2", resp.RoutingRoomID)
	require.Equal(t, "seating_ready", resp.State)
}

func TestClientCancelUsesControlSurfaceAndIdempotency(t *testing.T) {
	t.Helper()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "/v1/mtt/cancel", r.URL.Path)
		require.Equal(t, "poker_mtt:cancel:t-1", r.Header.Get("Idempotency-Key"))

		payload := decodeJSONBody(t, r)
		require.Equal(t, "t-1", payload["ID"])
		require.Equal(t, "manual_review", payload["reason"])

		writeJSON(t, w, map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data": map[string]any{
				"tournamentID": "t-1",
				"state":        "cancelled",
			},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        time.Second,
	}

	resp, err := client.Cancel(context.Background(), sidecar.CancelRequest{
		TournamentID: "t-1",
		Reason:       "manual_review",
	})
	require.NoError(t, err)
	require.Equal(t, "t-1", resp.TournamentID)
	require.Equal(t, "cancelled", resp.State)
}

func TestClientHealthChecksPlayerSurface(t *testing.T) {
	t.Helper()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodGet, r.Method)
		require.Equal(t, "/v1/hello", r.URL.Path)

		writeJSON(t, w, map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data": map[string]any{
				"status": "ok",
			},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        time.Second,
	}

	resp, err := client.Health(context.Background())
	require.NoError(t, err)
	require.True(t, resp.Healthy)
	require.Equal(t, "ok", resp.Status)
}

func TestClientStartRetriesTransient503ThenOK(t *testing.T) {
	t.Helper()

	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/v1/mtt/start", r.URL.Path)
		if attempts.Add(1) == 1 {
			w.WriteHeader(http.StatusServiceUnavailable)
			writeJSON(t, w, map[string]any{
				"code":    503,
				"msg":     "donor sidecar warming",
				"success": false,
				"data":    map[string]any{},
			})
			return
		}
		writeJSON(t, w, map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data": map[string]any{
				"tournamentID": "t-retry",
				"roomID":       "room-retry",
				"state":        "running",
			},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        time.Second,
	}

	resp, err := client.Start(context.Background(), sidecar.StartRequest{TournamentID: "t-retry"})
	require.NoError(t, err)
	require.Equal(t, int32(2), attempts.Load())
	require.Equal(t, "room-retry", resp.RoutingRoomID)
}

func TestClientGetRoomRetriesTimeoutThenOK(t *testing.T) {
	t.Helper()

	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/v1/mtt/getMTTRoomByID", r.URL.Path)
		if attempts.Add(1) == 1 {
			time.Sleep(80 * time.Millisecond)
			return
		}
		writeJSON(t, w, map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data": map[string]any{
				"tournamentID": "t-timeout",
				"userID":       "7",
				"roomID":       "room-timeout",
				"tableID":      "table-timeout",
				"state":        "running",
			},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        20 * time.Millisecond,
	}

	resp, err := client.GetRoom(context.Background(), sidecar.RoomRequest{TournamentID: "t-timeout", UserID: "7"})
	require.NoError(t, err)
	require.Equal(t, int32(2), attempts.Load())
	require.Equal(t, "room-timeout", resp.RoutingRoomID)
}

func TestClientJoinDoesNotRetryUnauthorizedAndIncludesDonorMessage(t *testing.T) {
	t.Helper()

	var attempts atomic.Int32
	fixed := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts.Add(1)
		require.Equal(t, "/v1/join_game", r.URL.Path)
		w.WriteHeader(http.StatusUnauthorized)
		writeJSON(t, w, map[string]any{
			"code":    401,
			"msg":     "donor token expired",
			"success": false,
			"data":    map[string]any{},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        time.Second,
	}

	_, err := client.Join(context.Background(), sidecar.JoinRequest{
		TournamentID:  "t-auth",
		UserID:        "7",
		PlayerName:    "tester",
		Authorization: "Bearer expired",
		RequestedAt:   fixed,
	})
	require.Error(t, err)
	require.Equal(t, int32(1), attempts.Load())
	require.Contains(t, err.Error(), "donor token expired")

	var reqErr *sidecar.RequestError
	require.True(t, errors.As(err, &reqErr))
	require.Equal(t, http.StatusUnauthorized, reqErr.StatusCode)
}

func TestClientTimeoutReturnsTypedError(t *testing.T) {
	t.Helper()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(100 * time.Millisecond)
		writeJSON(t, w, map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data":    map[string]any{},
		})
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        10 * time.Millisecond,
	}

	_, err := client.Start(context.Background(), sidecar.StartRequest{TournamentID: "t-1"})
	require.Error(t, err)

	var reqErr *sidecar.RequestError
	require.True(t, errors.As(err, &reqErr))
	require.True(t, reqErr.Timeout)
}

func TestClientMissingBaseURLReturnsTypedConfigurationError(t *testing.T) {
	t.Helper()

	client := sidecar.Client{}
	_, err := client.Start(context.Background(), sidecar.StartRequest{TournamentID: "t-1"})
	require.ErrorIs(t, err, sidecar.ErrInvalidConfiguration)

	var reqErr *sidecar.RequestError
	require.True(t, errors.As(err, &reqErr))
	require.Equal(t, "/v1/mtt/start", reqErr.URL)
}

func TestClientJoinRequiresStableRequestedAt(t *testing.T) {
	t.Helper()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatalf("join should fail before sending request when RequestedAt is zero")
	}))
	defer server.Close()

	client := sidecar.Client{
		ControlBaseURL: server.URL,
		PlayerBaseURL:  server.URL,
		HTTPClient:     server.Client(),
		Timeout:        time.Second,
	}

	_, err := client.Join(context.Background(), sidecar.JoinRequest{
		TournamentID: "t-1",
		UserID:       "7",
	})
	require.ErrorIs(t, err, sidecar.ErrInvalidConfiguration)
}

func decodeJSONBody(t *testing.T, r *http.Request) map[string]any {
	t.Helper()

	body, err := io.ReadAll(r.Body)
	require.NoError(t, err)
	var payload map[string]any
	require.NoError(t, json.Unmarshal(body, &payload))
	return payload
}

func writeJSON(t *testing.T, w http.ResponseWriter, payload any) {
	t.Helper()
	w.Header().Set("Content-Type", "application/json")
	require.NoError(t, json.NewEncoder(w).Encode(payload))
}
