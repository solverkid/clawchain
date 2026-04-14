package authadapter_test

import (
	"testing"
	"time"

	"github.com/clawchain/clawchain/authadapter"
	"github.com/stretchr/testify/require"
)

func TestSessionAuthStateRejectsExpiredAndRevokedActions(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	state := authadapter.NewSessionAuthState(authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: now.Add(time.Minute),
	})

	require.NoError(t, state.AuthorizeManualAction(now.Add(30*time.Second)))
	require.ErrorIs(t, state.AuthorizeManualAction(now.Add(time.Minute)), authadapter.ErrTokenExpired)

	state.Revoked = true
	require.ErrorIs(t, state.AuthorizeManualAction(now.Add(30*time.Second)), authadapter.ErrPrincipalRevoked)
}

func TestSessionAuthStateReconnectWithFreshTokenPreservesAcceptedActions(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	state := authadapter.NewSessionAuthState(authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: now.Add(time.Minute),
	})
	state.RecordAcceptedAction("action-1")

	fresh := authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "CLAW1LOCAL-7",
		TokenExpiresAt: now.Add(time.Hour),
	}
	reconnected, err := state.Reconnect(fresh, now.Add(2*time.Minute))
	require.NoError(t, err)
	require.Equal(t, fresh.TokenExpiresAt, reconnected.Principal.TokenExpiresAt)
	require.True(t, reconnected.HasAcceptedAction("action-1"))
}

func TestSessionAuthStateReconnectRejectsDifferentMiner(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	state := authadapter.NewSessionAuthState(authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: now.Add(time.Minute),
	})

	_, err := state.Reconnect(authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-8",
		TokenExpiresAt: now.Add(time.Hour),
	}, now)
	require.ErrorIs(t, err, authadapter.ErrMinerAddressMismatch)
}
