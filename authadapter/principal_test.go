package authadapter_test

import (
	"testing"
	"time"

	"github.com/clawchain/clawchain/authadapter"
	"github.com/stretchr/testify/require"
)

func TestPrincipalRejectsExpiredManualAction(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	principal := authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: now.Add(time.Minute),
	}

	require.NoError(t, principal.ValidateMutation(now.Add(30*time.Second)))
	err := principal.ValidateMutation(now.Add(time.Minute + time.Nanosecond))
	require.ErrorIs(t, err, authadapter.ErrTokenExpired)
}

func TestMutationMinerMismatchRejectsBeforeDomain(t *testing.T) {
	principal := authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: time.Now().Add(time.Hour),
	}

	err := authadapter.ValidateMutationMiner(principal, "claw1local-8")
	require.ErrorIs(t, err, authadapter.ErrMinerAddressMismatch)

	require.NoError(t, authadapter.ValidateMutationMiner(principal, "  CLAW1LOCAL-7  "))
}
