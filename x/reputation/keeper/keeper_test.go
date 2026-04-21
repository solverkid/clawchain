package keeper_test

import (
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

	"github.com/clawchain/clawchain/x/reputation/keeper"
	"github.com/clawchain/clawchain/x/reputation/types"
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
	ctx := sdk.NewContext(stateStore, cmtproto.Header{Height: 1}, false, log.NewNopLogger())
	return k, ctx
}

func TestInitMiner(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1test")

	score, found := k.GetScore(ctx, "claw1test")
	require.True(t, found)
	require.Equal(t, int32(500), score.Score)
	require.Equal(t, "low", score.Level) // 500 < NormalThreshold(600), so "low"
	require.Equal(t, "claw1test", score.MinerAddress)
}

func TestUpdateScorePositive(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1test")

	// Add points
	k.UpdateScore(ctx, "claw1test", types.RewardChallengeComplete, "challenge_complete")

	score, _ := k.GetScore(ctx, "claw1test")
	require.Equal(t, int32(505), score.Score)
}

func TestUpdateScoreNegative(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1test")

	// Deduct points
	k.UpdateScore(ctx, "claw1test", types.PenaltyChallengeFail, "challenge_failed")

	score, _ := k.GetScore(ctx, "claw1test")
	require.Equal(t, int32(480), score.Score)
}

func TestUpdateScoreCheatPenalty(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1cheater")

	// Cheat penalty (-500)
	k.UpdateScore(ctx, "claw1cheater", types.PenaltyCheat, "cheating")

	score, _ := k.GetScore(ctx, "claw1cheater")
	require.Equal(t, int32(0), score.Score)
	require.Equal(t, "suspended", score.Level)
}

func TestUpdateScoreMaxCap(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1elite")

	// Push to max
	k.UpdateScore(ctx, "claw1elite", 600, "boost")

	score, _ := k.GetScore(ctx, "claw1elite")
	require.Equal(t, types.MaxScore, score.Score) // capped at 1000
	require.Equal(t, "elite", score.Level)
}

func TestUpdateScoreMinCap(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1bad")

	// Push below 0
	k.UpdateScore(ctx, "claw1bad", -600, "severe_penalty")

	score, _ := k.GetScore(ctx, "claw1bad")
	require.Equal(t, types.MinScore, score.Score) // capped at 0
	require.Equal(t, "suspended", score.Level)
}

func TestGetLevel(t *testing.T) {
	require.Equal(t, "elite", types.GetLevel(800))
	require.Equal(t, "elite", types.GetLevel(1000))
	require.Equal(t, "normal", types.GetLevel(600))
	require.Equal(t, "normal", types.GetLevel(799))
	require.Equal(t, "low", types.GetLevel(100))
	require.Equal(t, "low", types.GetLevel(500))
	require.Equal(t, "suspended", types.GetLevel(99))
	require.Equal(t, "suspended", types.GetLevel(0))
}

func TestGetAllScores(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1a")
	k.InitMiner(ctx, "claw1b")
	k.InitMiner(ctx, "claw1c")

	scores := k.GetAllScores(ctx)
	require.Len(t, scores, 3)
}

func TestUpdateScoreAutoInit(t *testing.T) {
	k, ctx := setupKeeper(t)

	// UpdateScore should auto-init miner if not found
	k.UpdateScore(ctx, "claw1new", 10, "auto_init_test")

	score, found := k.GetScore(ctx, "claw1new")
	require.True(t, found)
	require.Equal(t, int32(510), score.Score) // 500 initial + 10
}

func TestUpdateStreak(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1streak")

	// Day 1: first activity
	k.UpdateStreak(ctx, "claw1streak", 86400*1) // day 1
	score, _ := k.GetScore(ctx, "claw1streak")
	require.Equal(t, uint64(1), score.ConsecutiveDays)

	// Same day: no change
	k.UpdateStreak(ctx, "claw1streak", 86400*1+100)
	score, _ = k.GetScore(ctx, "claw1streak")
	require.Equal(t, uint64(1), score.ConsecutiveDays)

	// Day 2: consecutive
	k.UpdateStreak(ctx, "claw1streak", 86400*2)
	score, _ = k.GetScore(ctx, "claw1streak")
	require.Equal(t, uint64(2), score.ConsecutiveDays)

	// Day 4: gap — reset
	k.UpdateStreak(ctx, "claw1streak", 86400*4)
	score, _ = k.GetScore(ctx, "claw1streak")
	require.Equal(t, uint64(1), score.ConsecutiveDays)
}

func TestGetStreakInfo(t *testing.T) {
	k, ctx := setupKeeper(t)

	// Not found
	_, bonus, found := k.GetStreakInfo(ctx, "claw1nonexist")
	require.False(t, found)
	require.Equal(t, uint64(100), bonus)

	// Init and build streak
	k.InitMiner(ctx, "claw1s")
	for i := int64(1); i <= 7; i++ {
		k.UpdateStreak(ctx, "claw1s", 86400*i)
	}
	days, bonus, found := k.GetStreakInfo(ctx, "claw1s")
	require.True(t, found)
	require.Equal(t, uint64(7), days)
	require.Equal(t, uint64(110), bonus) // 7 days = +10%
}

func TestStreakBonusValues(t *testing.T) {
	require.Equal(t, uint64(100), types.GetStreakBonus(0))
	require.Equal(t, uint64(100), types.GetStreakBonus(6))
	require.Equal(t, uint64(110), types.GetStreakBonus(7))
	require.Equal(t, uint64(110), types.GetStreakBonus(29))
	require.Equal(t, uint64(125), types.GetStreakBonus(30))
	require.Equal(t, uint64(125), types.GetStreakBonus(89))
	require.Equal(t, uint64(150), types.GetStreakBonus(90))
	require.Equal(t, uint64(150), types.GetStreakBonus(365))
}

func TestGenesisExportImport(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1a")
	k.UpdateScore(ctx, "claw1a", 100, "test")
	k.InitMiner(ctx, "claw1b")

	// Export
	gs := k.ExportGenesis(ctx)
	require.Len(t, gs.Scores, 2)

	// Re-import into new keeper
	k2, ctx2 := setupKeeper(t)
	k2.InitGenesis(ctx2, *gs)

	score, found := k2.GetScore(ctx2, "claw1a")
	require.True(t, found)
	require.Equal(t, int32(600), score.Score)
}

func TestGetLeaderboard(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1a")
	k.InitMiner(ctx, "claw1b")
	k.InitMiner(ctx, "claw1c")
	k.UpdateScore(ctx, "claw1a", 250, "boost")
	k.UpdateScore(ctx, "claw1b", 50, "boost")
	k.UpdateScore(ctx, "claw1c", -100, "penalty")

	leaderboard := k.GetLeaderboard(ctx, 2)
	require.Len(t, leaderboard, 2)
	require.Equal(t, "claw1a", leaderboard[0].MinerAddress)
	require.Equal(t, int32(750), leaderboard[0].Score)
	require.Equal(t, "claw1b", leaderboard[1].MinerAddress)
	require.Equal(t, int32(550), leaderboard[1].Score)
}

func TestQueryScore(t *testing.T) {
	k, ctx := setupKeeper(t)
	k.InitMiner(ctx, "claw1query")

	server := keeper.NewQueryServerImpl(k)
	resp, err := server.Score(sdk.WrapSDKContext(ctx), &types.QueryScoreRequest{MinerAddress: "claw1query"})
	require.NoError(t, err)
	require.Equal(t, "claw1query", resp.Score.MinerAddress)
	require.Equal(t, int32(500), resp.Score.Score)
}

func TestQueryScoreNotFound(t *testing.T) {
	k, ctx := setupKeeper(t)
	server := keeper.NewQueryServerImpl(k)

	_, err := server.Score(sdk.WrapSDKContext(ctx), &types.QueryScoreRequest{MinerAddress: "claw1missing"})
	require.ErrorIs(t, err, types.ErrMinerNotFound)
}

func TestQueryLeaderboard(t *testing.T) {
	k, ctx := setupKeeper(t)

	k.InitMiner(ctx, "claw1x")
	k.InitMiner(ctx, "claw1y")
	k.UpdateScore(ctx, "claw1x", 300, "boost")
	k.UpdateScore(ctx, "claw1y", -50, "penalty")

	server := keeper.NewQueryServerImpl(k)
	resp, err := server.Leaderboard(sdk.WrapSDKContext(ctx), &types.QueryLeaderboardRequest{Limit: 1})
	require.NoError(t, err)
	require.Len(t, resp.Scores, 1)
	require.Equal(t, "claw1x", resp.Scores[0].MinerAddress)
}
