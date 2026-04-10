package session

import "testing"

import "github.com/stretchr/testify/require"

func TestSessionHandoffReplacesChannelNotSeatAuthority(t *testing.T) {
	manager := NewManager()

	first := manager.Attach("miner_1", "session-a")
	second := manager.Attach("miner_1", "session-b")

	require.NotEqual(t, first.SessionID, second.SessionID)
	require.Equal(t, "session-b", manager.Active("miner_1").SessionID)
}
