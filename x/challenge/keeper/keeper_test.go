package keeper_test

import (
	"context"
	"encoding/json"
	"testing"

	"cosmossdk.io/log"
	"cosmossdk.io/store"
	"cosmossdk.io/store/metrics"
	storetypes "cosmossdk.io/store/types"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/x/challenge/keeper"
	"github.com/clawchain/clawchain/x/challenge/types"
)

// mockBankKeeper is a mock for BankKeeper interface
type mockBankKeeper struct {
	balances map[string]sdk.Coins
}

func newMockBankKeeper() *mockBankKeeper {
	return &mockBankKeeper{balances: make(map[string]sdk.Coins)}
}

func (m *mockBankKeeper) SendCoinsFromModuleToAccount(_ context.Context, _ string, addr sdk.AccAddress, amt sdk.Coins) error {
	m.balances[addr.String()] = m.balances[addr.String()].Add(amt...)
	return nil
}

func (m *mockBankKeeper) GetBalance(_ context.Context, addr sdk.AccAddress, denom string) sdk.Coin {
	for _, c := range m.balances[addr.String()] {
		if c.Denom == denom {
			return c
		}
	}
	return sdk.NewInt64Coin(denom, 0)
}

func (m *mockBankKeeper) MintCoins(_ context.Context, _ string, _ sdk.Coins) error {
	return nil
}

func setupKeeper(t *testing.T) (keeper.Keeper, sdk.Context, *mockBankKeeper) {
	storeKey := storetypes.NewKVStoreKey(types.StoreKey)

	db := dbm.NewMemDB()
	stateStore := store.NewCommitMultiStore(db, log.NewNopLogger(), metrics.NewNoOpMetrics())
	stateStore.MountStoreWithDB(storeKey, storetypes.StoreTypeIAVL, db)
	require.NoError(t, stateStore.LoadLatestVersion())

	registry := codectypes.NewInterfaceRegistry()
	cdc := codec.NewProtoCodec(registry)

	bk := newMockBankKeeper()
	k := keeper.NewKeeper(cdc, storeKey, bk)

	ctx := sdk.NewContext(stateStore, cmtproto.Header{Height: 10}, false, log.NewNopLogger())
	return k, ctx, bk
}

func TestGenerateChallenges(t *testing.T) {
	k, ctx, _ := setupKeeper(t)

	activeMiners := []string{"miner1", "miner2", "miner3", "miner4", "miner5"}
	challenges := k.GenerateChallenges(ctx, 1, activeMiners)

	require.NotEmpty(t, challenges)
	require.Equal(t, 10, len(challenges)) // default ChallengesPerEpoch = 10

	for _, ch := range challenges {
		require.NotEmpty(t, ch.ID)
		require.Equal(t, uint64(1), ch.Epoch)
		require.Equal(t, types.ChallengeStatusPending, ch.Status)
		require.NotEmpty(t, ch.Prompt)
	}
}

func TestGenerateChallengesNoMiners(t *testing.T) {
	k, ctx, _ := setupKeeper(t)

	challenges := k.GenerateChallenges(ctx, 1, nil)
	require.Nil(t, challenges)
}

func TestGetBlockReward(t *testing.T) {
	k, _, _ := setupKeeper(t)

	// Epoch 0 (height 0): 30,000,000 uclaw (30 CLAW miner pool per epoch)
	r := k.GetBlockReward(0)
	require.Equal(t, int64(30_000_000), r)

	// Height 5000 (epoch 50): still 30,000,000 (no halving yet)
	r = k.GetBlockReward(5000)
	require.Equal(t, int64(30_000_000), r)

	// Height 21,000,000 (epoch 210,000): first halving → 15,000,000
	r = k.GetBlockReward(21_000_000)
	require.Equal(t, int64(15_000_000), r)

	// Height 42,000,000 (epoch 420,000): second halving → 7,500,000
	r = k.GetBlockReward(42_000_000)
	require.Equal(t, int64(7_500_000), r)
}

func TestGetBlockRewardMinimum(t *testing.T) {
	k, _, _ := setupKeeper(t)

	// Very high height should not go below minimum (1 uclaw)
	r := k.GetBlockReward(10_000_000_000)
	require.GreaterOrEqual(t, r, int64(1))
}

func TestChallengeTypes(t *testing.T) {
	// Verify challenge type constants exist
	require.NotEmpty(t, string(types.ChallengeMath))
	require.NotEmpty(t, string(types.ChallengeLogic))
	require.NotEmpty(t, string(types.ChallengeSentiment))
	require.NotEmpty(t, string(types.ChallengeTextSummary))
}

// mockReputationKeeper for tier/spot check tests
type mockReputationKeeper struct {
	scores map[string]int32
}

func newMockReputationKeeper() *mockReputationKeeper {
	return &mockReputationKeeper{scores: make(map[string]int32)}
}

func (m *mockReputationKeeper) GetMinerScore(_ sdk.Context, addr string) (int32, bool) {
	s, ok := m.scores[addr]
	return s, ok
}

func (m *mockReputationKeeper) UpdateScore(_ sdk.Context, addr string, delta int32, _ string) {
	m.scores[addr] += delta
}

func TestTierAutoAssignment(t *testing.T) {
	k, ctx, _ := setupKeeper(t)
	activeMiners := []string{"m1", "m2", "m3"}
	challenges := k.GenerateChallenges(ctx, 100, activeMiners)

	for _, ch := range challenges {
		expectedTier := types.GetTaskTier(ch.Type)
		require.Equal(t, expectedTier, ch.Tier, "challenge %s type %s should have tier %d", ch.ID, ch.Type, expectedTier)
	}
}

func TestSubmitAnswerWithTierCheck(t *testing.T) {
	k, ctx, _ := setupKeeper(t)

	rk := newMockReputationKeeper()
	rk.scores["low_rep"] = 400
	rk.scores["mid_rep"] = 650
	rk.scores["high_rep"] = 850
	k.SetReputationKeeper(rk)

	// Create a Tier 3 challenge manually
	store := ctx.KVStore(k.StoreKey())
	ch := types.Challenge{
		ID:            "ch-test-tier3",
		Type:          types.ChallengeTextSummary,
		Tier:          types.TierAdvanced,
		Status:        types.ChallengeStatusPending,
		Commits:       make(map[string]string),
		Reveals:       make(map[string]string),
	}
	bz, _ := json.Marshal(ch)
	store.Set([]byte("challenge:ch-test-tier3"), bz)

	// Low rep miner should be rejected
	err := k.SubmitAnswerWithChecks(ctx, "ch-test-tier3", "low_rep", "answer")
	require.ErrorIs(t, err, types.ErrInsufficientReputation)

	// Mid rep miner should also be rejected for Tier 3
	err = k.SubmitAnswerWithChecks(ctx, "ch-test-tier3", "mid_rep", "answer")
	require.ErrorIs(t, err, types.ErrInsufficientReputation)

	// High rep miner should pass
	err = k.SubmitAnswerWithChecks(ctx, "ch-test-tier3", "high_rep", "answer")
	require.NoError(t, err)
}

func TestSpotCheckPenalty(t *testing.T) {
	k, ctx, _ := setupKeeper(t)

	rk := newMockReputationKeeper()
	rk.scores["miner1"] = 500
	rk.scores["miner2"] = 500
	k.SetReputationKeeper(rk)

	store := ctx.KVStore(k.StoreKey())
	ch := types.Challenge{
		ID:          "ch-spot-1",
		Type:        types.ChallengeMath,
		Tier:        types.TierBasic,
		Status:      types.ChallengeStatusPending,
		IsSpotCheck: true,
		KnownAnswer: "42",
		Commits:     make(map[string]string),
		Reveals:     make(map[string]string),
	}
	bz, _ := json.Marshal(ch)
	store.Set([]byte("challenge:ch-spot-1"), bz)

	// Wrong answer: -50
	err := k.SubmitAnswerWithChecks(ctx, "ch-spot-1", "miner1", "wrong")
	require.NoError(t, err)
	require.Equal(t, int32(450), rk.scores["miner1"])

	// Correct answer: +10
	err = k.SubmitAnswerWithChecks(ctx, "ch-spot-1", "miner2", "42")
	require.NoError(t, err)
	require.Equal(t, int32(510), rk.scores["miner2"])
}

func TestSpotCheckNonSpot(t *testing.T) {
	k, ctx, _ := setupKeeper(t)

	rk := newMockReputationKeeper()
	rk.scores["miner1"] = 500
	k.SetReputationKeeper(rk)

	store := ctx.KVStore(k.StoreKey())
	ch := types.Challenge{
		ID:          "ch-normal",
		Type:        types.ChallengeMath,
		Tier:        types.TierBasic,
		Status:      types.ChallengeStatusPending,
		IsSpotCheck: false,
		Commits:     make(map[string]string),
		Reveals:     make(map[string]string),
	}
	bz, _ := json.Marshal(ch)
	store.Set([]byte("challenge:ch-normal"), bz)

	// Non-spot check: no reputation change
	err := k.SubmitAnswerWithChecks(ctx, "ch-normal", "miner1", "any")
	require.NoError(t, err)
	require.Equal(t, int32(500), rk.scores["miner1"])
}

func TestDefaultChallengeParams(t *testing.T) {
	params := types.DefaultChallengeParams()
	require.Equal(t, uint32(10), params.ChallengesPerEpoch)
	require.Equal(t, uint32(3), params.AssigneesPerChallenge)
	require.Equal(t, int64(5), params.ResponseWindowBlocks)
}
