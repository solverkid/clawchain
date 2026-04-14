package session

import "testing"

import "github.com/stretchr/testify/require"

func TestSessionHandoffReplacesChannelNotSeatAuthority(t *testing.T) {
	manager := NewManager()

	first := manager.Attach("tour_1", "miner_1", "session-a")
	second := manager.Attach("tour_1", "miner_1", "session-b")

	require.NotEqual(t, first.SessionID, second.SessionID)
	require.Equal(t, "session-b", manager.Active("tour_1", "miner_1").SessionID)
}

func TestSessionScopeIsPerTournament(t *testing.T) {
	manager := NewManager()

	manager.Attach("tour_1", "miner_1", "session-a")
	manager.Attach("tour_2", "miner_1", "session-b")

	require.Equal(t, "session-a", manager.Active("tour_1", "miner_1").SessionID)
	require.Equal(t, "session-b", manager.Active("tour_2", "miner_1").SessionID)
}
