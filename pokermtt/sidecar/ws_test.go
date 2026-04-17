package sidecar_test

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	"github.com/clawchain/clawchain/pokermtt/sidecar"
	"github.com/stretchr/testify/require"
)

func TestWSConnectSpecUsesDonorBoundaryMetadata(t *testing.T) {
	t.Helper()

	server := httptest.NewServer(http.NotFoundHandler())
	defer server.Close()

	ws := sidecar.WS{BaseURL: server.URL}
	spec, err := ws.ConnectSpec(sidecar.ConnectRequest{
		TournamentID:  "t-1",
		UserID:        "7",
		RoutingRoomID: "room-9",
		SessionID:     "session-1",
		Authorization: "Bearer local-user:7",
		MockUserID:    "7",
	})
	require.NoError(t, err)

	parsedBase, err := url.Parse(server.URL)
	require.NoError(t, err)
	parsedBase.Scheme = "ws"
	require.Equal(t, parsedBase.String()+"/v1/ws?id=t-1&type=mtt", spec.URL)
	require.Equal(t, "room-9", spec.RoutingRoomID)
	require.Equal(t, "Bearer local-user:7", spec.Headers.Get("Authorization"))
	require.Equal(t, "7", spec.Headers.Get("Mock-Userid"))
	require.Equal(t, []string{"local-user:7", "session-1"}, spec.Subprotocols)

	parsed, err := url.Parse(spec.URL)
	require.NoError(t, err)
	require.Empty(t, parsed.Query().Get("roomID"))
}

func TestWSConnectSpecFallsBackToPlaceholderToken(t *testing.T) {
	t.Helper()

	server := httptest.NewServer(http.NotFoundHandler())
	defer server.Close()

	ws := sidecar.WS{BaseURL: server.URL}
	spec, err := ws.ConnectSpec(sidecar.ConnectRequest{
		TournamentID: "t-1",
		SessionID:    "session-1",
	})
	require.NoError(t, err)

	require.Equal(t, []string{"-1", "session-1"}, spec.Subprotocols)
	require.Empty(t, spec.Headers.Get("Authorization"))
	require.Empty(t, spec.Headers.Get("Mock-Userid"))
}
