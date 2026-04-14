package identity_test

import (
	"testing"
	"time"

	"github.com/clawchain/clawchain/authadapter"
	"github.com/clawchain/clawchain/pokermtt/identity"
	"github.com/stretchr/testify/require"
)

func TestAuthorizeMutationUsesPrincipalMinerAddress(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	principal := authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "CLAW1LOCAL-7",
		TokenExpiresAt: now.Add(time.Hour),
	}

	authorized, err := identity.MutationAuthorizer{}.Authorize(principal, identity.MutationRequest{
		RequestMinerID: "claw1local-7",
		Now:            now,
	})
	require.NoError(t, err)
	require.Equal(t, "7", authorized.UserID)
	require.Equal(t, "claw1local-7", authorized.MinerAddress)
}

func TestAuthorizeMutationRejectsRequestMinerMismatchBeforeDomain(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	principal := authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: now.Add(time.Hour),
	}

	_, err := identity.MutationAuthorizer{}.Authorize(principal, identity.MutationRequest{
		RequestMinerID: "claw1local-8",
		Now:            now,
	})
	require.ErrorIs(t, err, authadapter.ErrMinerAddressMismatch)
}

func TestAuthorizeMutationRejectsExpiredPrincipal(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	principal := authadapter.Principal{
		UserID:         "7",
		MinerAddress:   "claw1local-7",
		TokenExpiresAt: now.Add(time.Minute),
	}

	_, err := identity.MutationAuthorizer{}.Authorize(principal, identity.MutationRequest{
		RequestMinerID: "claw1local-7",
		Now:            now.Add(time.Minute),
	})
	require.ErrorIs(t, err, authadapter.ErrTokenExpired)
}
