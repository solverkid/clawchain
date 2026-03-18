package types_test

import (
	"testing"

	"github.com/clawchain/clawchain/x/poa/types"
	"github.com/stretchr/testify/require"
)

func TestGetEarlyBirdMultiplier(t *testing.T) {
	require.Equal(t, uint64(300), types.GetEarlyBirdMultiplier(1))
	require.Equal(t, uint64(300), types.GetEarlyBirdMultiplier(1000))
	require.Equal(t, uint64(200), types.GetEarlyBirdMultiplier(1001))
	require.Equal(t, uint64(200), types.GetEarlyBirdMultiplier(5000))
	require.Equal(t, uint64(150), types.GetEarlyBirdMultiplier(5001))
	require.Equal(t, uint64(150), types.GetEarlyBirdMultiplier(10000))
	require.Equal(t, uint64(100), types.GetEarlyBirdMultiplier(10001))
	require.Equal(t, uint64(100), types.GetEarlyBirdMultiplier(1000000))
}

func TestGetStreakBonus(t *testing.T) {
	require.Equal(t, uint64(100), types.GetStreakBonus(0))
	require.Equal(t, uint64(100), types.GetStreakBonus(6))
	require.Equal(t, uint64(110), types.GetStreakBonus(7))
	require.Equal(t, uint64(110), types.GetStreakBonus(29))
	require.Equal(t, uint64(125), types.GetStreakBonus(30))
	require.Equal(t, uint64(125), types.GetStreakBonus(89))
	require.Equal(t, uint64(150), types.GetStreakBonus(90))
	require.Equal(t, uint64(150), types.GetStreakBonus(365))
}
