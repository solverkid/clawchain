package authadapter_test

import (
	"context"
	"testing"
	"time"

	"github.com/clawchain/clawchain/authadapter"
	"github.com/stretchr/testify/require"
)

func TestLocalAdapterVerifyBearerLocalUser(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	adapter := authadapter.LocalAdapter{
		Now:      func() time.Time { return now },
		TokenTTL: time.Hour,
	}

	principal, err := adapter.Verify(context.Background(), "Bearer local-user:7")
	require.NoError(t, err)
	require.Equal(t, "7", principal.UserID)
	require.Equal(t, "7", principal.DisplayName)
	require.Equal(t, "claw1local-7", principal.MinerAddress)
	require.Equal(t, authadapter.AuthSourceLocal, principal.AuthSource)
	require.True(t, principal.IsSynthetic)
	require.True(t, principal.TokenExpiresAt.Equal(now.Add(time.Hour)))
}

func TestLocalMockPrincipalRequiresExplicitRewardBinding(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	adapter := authadapter.LocalAdapter{Now: func() time.Time { return now }}

	principal, err := adapter.Verify(context.Background(), "Bearer local-user:7")
	require.NoError(t, err)
	require.False(t, principal.PokerMTTRewardEligible())

	principal.Roles = append(principal.Roles, authadapter.RolePokerMTTRewardBound)
	require.True(t, principal.PokerMTTRewardEligible())
}

func TestLocalAdapterRejectsMalformedToken(t *testing.T) {
	adapter := authadapter.LocalAdapter{}

	_, err := adapter.Verify(context.Background(), "Bearer not-a-local-token")
	require.Error(t, err)
}
