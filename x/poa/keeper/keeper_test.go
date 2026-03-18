package keeper_test

import (
	"testing"
	"time"

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

	"github.com/clawchain/clawchain/x/poa/keeper"
	"github.com/clawchain/clawchain/x/poa/types"
)

func setupKeeper(t *testing.T) (keeper.Keeper, sdk.Context) {
	storeKey := storetypes.NewKVStoreKey(types.StoreKey)

	db := dbm.NewMemDB()
	stateStore := store.NewCommitMultiStore(db, log.NewNopLogger(), metrics.NewNoOpMetrics())
	stateStore.MountStoreWithDB(storeKey, storetypes.StoreTypeIAVL, db)
	require.NoError(t, stateStore.LoadLatestVersion())

	registry := codectypes.NewInterfaceRegistry()
	cdc := codec.NewProtoCodec(registry)

	k := keeper.NewKeeper(cdc, storeKey)

	ctx := sdk.NewContext(stateStore, cmtproto.Header{Height: 1, Time: time.Now()}, false, log.NewNopLogger())
	return k, ctx
}

func TestRegisterMiner(t *testing.T) {
	k, ctx := setupKeeper(t)

	// Register a new miner
	err := k.RegisterMiner(ctx, "claw1abc123")
	require.NoError(t, err)

	// Verify miner exists
	miner, err := k.GetMiner(ctx, "claw1abc123")
	require.NoError(t, err)
	require.Equal(t, "claw1abc123", miner.Address)
	require.Equal(t, types.MinerStatusInactive, miner.Status)
	require.Equal(t, int32(500), miner.ReputationScore)
	require.Equal(t, uint64(0), miner.StakeAmount)
}

func TestRegisterMinerDuplicate(t *testing.T) {
	k, ctx := setupKeeper(t)

	err := k.RegisterMiner(ctx, "claw1abc123")
	require.NoError(t, err)

	// Duplicate registration should fail
	err = k.RegisterMiner(ctx, "claw1abc123")
	require.Error(t, err)
	require.ErrorIs(t, err, types.ErrMinerAlreadyRegistered)
}

func TestStakeMiner(t *testing.T) {
	k, ctx := setupKeeper(t)

	// Register first
	err := k.RegisterMiner(ctx, "claw1abc123")
	require.NoError(t, err)

	// Stake below minimum - should stay inactive
	err = k.StakeMiner(ctx, "claw1abc123", 50_000_000)
	require.NoError(t, err)

	miner, _ := k.GetMiner(ctx, "claw1abc123")
	require.Equal(t, types.MinerStatusInactive, miner.Status)
	require.Equal(t, uint64(50_000_000), miner.StakeAmount)

	// Stake above minimum - should activate
	err = k.StakeMiner(ctx, "claw1abc123", 50_000_000)
	require.NoError(t, err)

	miner, _ = k.GetMiner(ctx, "claw1abc123")
	require.Equal(t, types.MinerStatusActive, miner.Status)
	require.Equal(t, uint64(100_000_000), miner.StakeAmount)
}

func TestStakeMinerNotFound(t *testing.T) {
	k, ctx := setupKeeper(t)

	err := k.StakeMiner(ctx, "nonexistent", 100)
	require.Error(t, err)
	require.ErrorIs(t, err, types.ErrMinerNotFound)
}

func TestUnstakeMiner(t *testing.T) {
	k, ctx := setupKeeper(t)

	// Setup: register and stake
	err := k.RegisterMiner(ctx, "claw1abc123")
	require.NoError(t, err)
	err = k.StakeMiner(ctx, "claw1abc123", 200_000_000)
	require.NoError(t, err)

	// Unstake partial
	err = k.UnstakeMiner(ctx, "claw1abc123", 50_000_000)
	require.NoError(t, err)

	miner, _ := k.GetMiner(ctx, "claw1abc123")
	require.Equal(t, uint64(150_000_000), miner.StakeAmount)
}

func TestUnstakeMinerInsufficientStake(t *testing.T) {
	k, ctx := setupKeeper(t)

	err := k.RegisterMiner(ctx, "claw1abc123")
	require.NoError(t, err)
	err = k.StakeMiner(ctx, "claw1abc123", 100_000_000)
	require.NoError(t, err)

	err = k.UnstakeMiner(ctx, "claw1abc123", 200_000_000)
	require.Error(t, err)
	require.ErrorIs(t, err, types.ErrInsufficientStake)
}

func TestGetActiveMiners(t *testing.T) {
	k, ctx := setupKeeper(t)

	// Register and activate 2 miners
	k.RegisterMiner(ctx, "claw1active1")
	k.StakeMiner(ctx, "claw1active1", 200_000_000)

	k.RegisterMiner(ctx, "claw1active2")
	k.StakeMiner(ctx, "claw1active2", 200_000_000)

	// Register but don't activate
	k.RegisterMiner(ctx, "claw1inactive")

	miners := k.GetActiveMiners(ctx)
	require.Len(t, miners, 2)
}

func TestSlashMiner(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.RegisterMiner(ctx, "claw1slash")
	k.StakeMiner(ctx, "claw1slash", 200_000_000)

	// Slash 10%
	err := k.SlashMiner(ctx, "claw1slash", 10)
	require.NoError(t, err)

	miner, _ := k.GetMiner(ctx, "claw1slash")
	require.Equal(t, uint64(180_000_000), miner.StakeAmount)
}

func TestSlashMinerBelowMinStake(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.RegisterMiner(ctx, "claw1slash")
	k.StakeMiner(ctx, "claw1slash", 100_000_000) // exactly min

	// Slash 50%
	err := k.SlashMiner(ctx, "claw1slash", 50)
	require.NoError(t, err)

	miner, _ := k.GetMiner(ctx, "claw1slash")
	require.Equal(t, uint64(50_000_000), miner.StakeAmount)
	require.Equal(t, types.MinerStatusSuspended, miner.Status)
}

func TestGetCurrentEpoch(t *testing.T) {
	k, ctx := setupKeeper(t)

	// Height 1: epoch 0
	require.Equal(t, uint64(0), k.GetCurrentEpoch(ctx))

	// Height 100: epoch 1
	ctx = ctx.WithBlockHeight(100)
	require.Equal(t, uint64(1), k.GetCurrentEpoch(ctx))

	// Height 250: epoch 2
	ctx = ctx.WithBlockHeight(250)
	require.Equal(t, uint64(2), k.GetCurrentEpoch(ctx))
}

func TestIsEpochEnd(t *testing.T) {
	k, ctx := setupKeeper(t)

	ctx = ctx.WithBlockHeight(0)
	require.False(t, k.IsEpochEnd(ctx)) // height 0 excluded

	ctx = ctx.WithBlockHeight(100)
	require.True(t, k.IsEpochEnd(ctx))

	ctx = ctx.WithBlockHeight(50)
	require.False(t, k.IsEpochEnd(ctx))

	ctx = ctx.WithBlockHeight(200)
	require.True(t, k.IsEpochEnd(ctx))
}

func TestCalculateEpochReward(t *testing.T) {
	params := types.DefaultParams()

	// Epoch 0: 50 CLAW (50_000_000 uclaw)
	r := types.CalculateEpochReward(0, params)
	require.Equal(t, uint64(50_000_000), r)

	// Epoch 209999: still 50 CLAW (before first halving)
	r = types.CalculateEpochReward(209999, params)
	require.Equal(t, uint64(50_000_000), r)

	// Epoch 210000: 25 CLAW (first halving)
	r = types.CalculateEpochReward(210000, params)
	require.Equal(t, uint64(25_000_000), r)

	// Epoch 420000: 12.5 CLAW (second halving)
	r = types.CalculateEpochReward(420000, params)
	require.Equal(t, uint64(12_500_000), r)
}

func TestDistributeEpochRewards(t *testing.T) {
	k, ctx := setupKeeper(t)

	// Register miners
	k.RegisterMiner(ctx, "claw1miner1")
	k.StakeMiner(ctx, "claw1miner1", 200_000_000)
	k.RegisterMiner(ctx, "claw1miner2")
	k.StakeMiner(ctx, "claw1miner2", 200_000_000)

	// Distribute rewards
	k.DistributeEpochRewards(ctx, 1, []string{"claw1miner1", "claw1miner2"})

	m1, _ := k.GetMiner(ctx, "claw1miner1")
	m2, _ := k.GetMiner(ctx, "claw1miner2")

	// Base: 50_000_000 * 60% = 30_000_000 / 2 miners = 15_000_000 each
	// Early bird: regIndex 1,2 → 3x (300)
	// Streak: 0 days → 1x (100)
	// Cold start: <100 challenges → /2
	// Actual: 15_000_000 * 300 * 100 / 10000 / 2 = 22_500_000
	require.Equal(t, uint64(22_500_000), m1.TotalRewards)
	require.Equal(t, uint64(22_500_000), m2.TotalRewards)
	require.Equal(t, uint64(1), m1.ChallengesCompleted)
}

func TestEarlyBirdAndStreakIntegration(t *testing.T) {
	k, ctx := setupKeeper(t)

	// Register miner with index 1 (early bird 3x)
	k.RegisterMiner(ctx, "claw1early")
	k.StakeMiner(ctx, "claw1early", 200_000_000)

	miner, _ := k.GetMiner(ctx, "claw1early")
	require.Equal(t, uint64(1), miner.RegistrationIndex)

	// Verify early bird multiplier
	mult := types.GetEarlyBirdMultiplier(miner.RegistrationIndex)
	require.Equal(t, uint64(300), mult)
}

func TestRegistrationIndexIncrement(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.RegisterMiner(ctx, "claw1a")
	k.RegisterMiner(ctx, "claw1b")
	k.RegisterMiner(ctx, "claw1c")

	m1, _ := k.GetMiner(ctx, "claw1a")
	m2, _ := k.GetMiner(ctx, "claw1b")
	m3, _ := k.GetMiner(ctx, "claw1c")

	require.Equal(t, uint64(1), m1.RegistrationIndex)
	require.Equal(t, uint64(2), m2.RegistrationIndex)
	require.Equal(t, uint64(3), m3.RegistrationIndex)
}
