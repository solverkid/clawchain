package types_test

import (
	"testing"

	"github.com/clawchain/clawchain/x/challenge/types"
	"github.com/stretchr/testify/require"
)

func TestGetTaskTier(t *testing.T) {
	require.Equal(t, types.TierBasic, types.GetTaskTier(types.ChallengeMath))
	require.Equal(t, types.TierBasic, types.GetTaskTier(types.ChallengeLogic))
	require.Equal(t, types.TierBasic, types.GetTaskTier(types.ChallengeHash))

	require.Equal(t, types.TierMedium, types.GetTaskTier(types.ChallengeSentiment))
	require.Equal(t, types.TierMedium, types.GetTaskTier(types.ChallengeClassification))

	require.Equal(t, types.TierAdvanced, types.GetTaskTier(types.ChallengeTextSummary))
	require.Equal(t, types.TierAdvanced, types.GetTaskTier(types.ChallengeTranslation))
	require.Equal(t, types.TierAdvanced, types.GetTaskTier(types.ChallengeEntityExtraction))
}

func TestGetTierMultiplier(t *testing.T) {
	require.Equal(t, uint64(1), types.GetTierMultiplier(types.TierBasic))
	require.Equal(t, uint64(2), types.GetTierMultiplier(types.TierMedium))
	require.Equal(t, uint64(3), types.GetTierMultiplier(types.TierAdvanced))
}

func TestMinReputationForTier(t *testing.T) {
	require.Equal(t, int32(0), types.MinReputationForTier(types.TierBasic))
	require.Equal(t, int32(600), types.MinReputationForTier(types.TierMedium))
	require.Equal(t, int32(800), types.MinReputationForTier(types.TierAdvanced))
}
