package session_test

import (
	"testing"
	"time"

	"github.com/clawchain/clawchain/authadapter"
	"github.com/clawchain/clawchain/pokermtt/session"
	"github.com/stretchr/testify/require"
)

func TestManagerRejectsExpiredAndRevokedActions(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	manager := session.NewManager()
	manager.Attach("session-1", authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: now.Add(time.Minute),
	})

	require.NoError(t, manager.AuthorizeManualAction("session-1", now.Add(30*time.Second)))
	require.ErrorIs(t, manager.AuthorizeManualAction("session-1", now.Add(time.Minute)), authadapter.ErrTokenExpired)

	require.NoError(t, manager.Revoke("session-1"))
	require.ErrorIs(t, manager.AuthorizeManualAction("session-1", now.Add(30*time.Second)), authadapter.ErrPrincipalRevoked)
}

func TestManagerReconnectWithFreshTokenPreservesAcceptedActions(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	manager := session.NewManager()
	manager.Attach("session-1", authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: now.Add(time.Minute),
	})
	require.NoError(t, manager.RecordAcceptedAction("session-1", "action-1"))

	require.NoError(t, manager.Reconnect("session-1", authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "CLAW1LOCAL-7",
		TokenExpiresAt: now.Add(time.Hour),
	}, now.Add(2*time.Minute)))

	require.NoError(t, manager.AuthorizeManualAction("session-1", now.Add(30*time.Minute)))
	require.True(t, manager.HasAcceptedAction("session-1", "action-1"))
}

func TestManagerReconnectRejectsDifferentMiner(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	manager := session.NewManager()
	manager.Attach("session-1", authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: now.Add(time.Minute),
	})

	err := manager.Reconnect("session-1", authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-8",
		TokenExpiresAt: now.Add(time.Hour),
	}, now)
	require.ErrorIs(t, err, authadapter.ErrMinerAddressMismatch)
}
