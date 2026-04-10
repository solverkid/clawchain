package httpapi

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/gateway"
	"github.com/clawchain/clawchain/arena/session"
)

func TestWaveRegistrationLifecycle(t *testing.T) {
	srv := newHTTPServerForTest(t)

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/arena/waves/wave_1/register", bytes.NewBufferString(`{"miner_id":"miner_1"}`))
	srv.Handler().ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)

	resp = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodDelete, "/v1/arena/waves/wave_1/registration/miner_1", nil)
	srv.Handler().ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)
}

func TestSeatAssignmentEndpointReturnsLatestTableAfterMove(t *testing.T) {
	srv := newHTTPServerForTest(t)

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tournaments/tour_1/seat-assignment/miner_1", nil)
	srv.Handler().ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)

	var body map[string]any
	require.NoError(t, json.Unmarshal(resp.Body.Bytes(), &body))
	require.Equal(t, "tbl:tour_1:02", body["table_id"])
}

func TestReconnectAfterAutoActionGetsHydratedReadOnlyState(t *testing.T) {
	srv := newHTTPServerForTest(t)

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/tournaments/tour_1/sessions/reconnect", bytes.NewBufferString(`{"miner_id":"miner_1","session_id":"session-b"}`))
	srv.Handler().ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)

	var body map[string]any
	require.NoError(t, json.Unmarshal(resp.Body.Bytes(), &body))
	require.Equal(t, "session-b", body["session_id"])
	require.Equal(t, true, body["read_only"])
}

func TestStandingAndLiveTableEndpointsExposeFrozenShape(t *testing.T) {
	srv := newHTTPServerForTest(t)

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tournaments/tour_1/standing", nil)
	srv.Handler().ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)
	require.Contains(t, resp.Body.String(), `"players_remaining"`)

	resp = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/v1/tournaments/tour_1/live-table/tbl:tour_1:01", nil)
	srv.Handler().ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)
	require.Contains(t, resp.Body.String(), `"acting_seat_no"`)
}

func newHTTPServerForTest(t *testing.T) *Server {
	t.Helper()

	return NewServer(Dependencies{
		Gateway:  gateway.New(gateway.Config{}),
		Sessions: session.NewManager(),
		WaveRegistrations: map[string]map[string]bool{
			"wave_1": {},
		},
		StandingView: map[string]map[string]any{
			"tour_1": {
				"players_remaining": 17,
				"round_no":          3,
			},
		},
		LiveTableView: map[string]map[string]map[string]any{
			"tour_1": {
				"tbl:tour_1:01": {
					"acting_seat_no": 7,
					"pot_main":       120,
				},
			},
		},
		SeatAssignments: map[string]map[string]SeatAssignment{
			"tour_1": {
				"miner_1": {
					TableID:   "tbl:tour_1:02",
					StateSeq:  8,
					ReadOnly:  true,
					SessionID: "session-a",
				},
			},
		},
	})
}
