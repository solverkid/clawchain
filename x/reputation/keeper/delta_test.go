package keeper_test

import (
	"bytes"
	"testing"
	"time"

	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/stretchr/testify/require"

	challengekeeper "github.com/clawchain/clawchain/x/challenge/keeper"
	"github.com/clawchain/clawchain/x/reputation/keeper"
	"github.com/clawchain/clawchain/x/reputation/types"
)

var _ challengekeeper.ReputationKeeper = keeper.Keeper{}

func testDeltaController() string {
	return sdk.AccAddress(bytes.Repeat([]byte{0x07}, 20)).String()
}

func testReputationDelta(deltaID string) types.ReputationDelta {
	return types.ReputationDelta{
		DeltaID:               deltaID,
		MinerAddress:          "claw1delta",
		SettlementBatchID:     "sb_2026_04_21_0001",
		RewardWindowID:        "rw_2026_04_21_daily",
		Lane:                  "poker_mtt_daily",
		PolicyVersion:         "poker_mtt_reputation_delta_v1",
		PriorScoreRef:         "rating:claw1delta:2026-04-20",
		Reason:                "poker_mtt_window_performance",
		Delta:                 7,
		DeltaCap:              10,
		ScoreWeight:           0.7,
		GrossRewardAmount:     12.5,
		SubmissionCount:       4,
		SourceResultRoot:      "sha256:" + "a" + string(bytes.Repeat([]byte("a"), 63)),
		CorrectionLineageRoot: "sha256:" + "b" + string(bytes.Repeat([]byte("b"), 63)),
	}
}

func TestApplyReputationDeltaRequiresAuthorizedController(t *testing.T) {
	k, ctx := setupKeeper(t)

	_, err := k.ApplyReputationDelta(ctx, testDeltaController(), testReputationDelta("delta:unauthorized"))
	require.ErrorIs(t, err, types.ErrUnauthorizedDeltaController)
}

func TestApplyReputationDeltaAppliesAndStoresReceipt(t *testing.T) {
	k, ctx := setupKeeper(t)
	ctx = ctx.WithBlockTime(time.Unix(1_713_715_200, 0))
	controller := testDeltaController()
	require.NoError(t, k.SetAuthorizedDeltaController(ctx, controller))

	receipt, err := k.ApplyReputationDelta(ctx, controller, testReputationDelta("delta:apply"))
	require.NoError(t, err)
	require.Equal(t, int32(500), receipt.OldScore)
	require.Equal(t, int32(507), receipt.NewScore)
	require.Equal(t, controller, receipt.Controller)

	score, found := k.GetScore(ctx, "claw1delta")
	require.True(t, found)
	require.Equal(t, int32(507), score.Score)

	stored, found := k.GetAppliedReputationDelta(ctx, "delta:apply")
	require.True(t, found)
	require.Equal(t, receipt.PayloadHash, stored.PayloadHash)

	events := ctx.EventManager().Events()
	require.Len(t, events, 2)
	require.Equal(t, types.EventTypeScoreUpdate, events[0].Type)
	require.Equal(t, types.EventTypeReputationDeltaApplied, events[1].Type)
}

func TestApplyReputationDeltaIsIdempotentOnSamePayload(t *testing.T) {
	k, ctx := setupKeeper(t)
	controller := testDeltaController()
	require.NoError(t, k.SetAuthorizedDeltaController(ctx, controller))

	first, err := k.ApplyReputationDelta(ctx, controller, testReputationDelta("delta:idempotent"))
	require.NoError(t, err)
	second, err := k.ApplyReputationDelta(ctx, controller, testReputationDelta("delta:idempotent"))
	require.NoError(t, err)

	score, found := k.GetScore(ctx, "claw1delta")
	require.True(t, found)
	require.Equal(t, int32(507), score.Score)
	require.Equal(t, first.PayloadHash, second.PayloadHash)
	require.Equal(t, first.NewScore, second.NewScore)
}

func TestApplyReputationDeltaRejectsPayloadConflict(t *testing.T) {
	k, ctx := setupKeeper(t)
	controller := testDeltaController()
	require.NoError(t, k.SetAuthorizedDeltaController(ctx, controller))

	delta := testReputationDelta("delta:conflict")
	_, err := k.ApplyReputationDelta(ctx, controller, delta)
	require.NoError(t, err)

	conflicting := delta
	conflicting.Delta = 8
	_, err = k.ApplyReputationDelta(ctx, controller, conflicting)
	require.ErrorIs(t, err, types.ErrReputationDeltaConflict)
}

func TestApplyReputationDeltaRespectsScoreCap(t *testing.T) {
	k, ctx := setupKeeper(t)
	controller := testDeltaController()
	require.NoError(t, k.SetAuthorizedDeltaController(ctx, controller))

	delta := testReputationDelta("delta:cap")
	delta.Delta = 600
	delta.DeltaCap = 600
	receipt, err := k.ApplyReputationDelta(ctx, controller, delta)
	require.NoError(t, err)
	require.Equal(t, types.MaxScore, receipt.NewScore)
}

func TestGenesisExportImportIncludesAuthorizedControllersAndAppliedDeltas(t *testing.T) {
	k, ctx := setupKeeper(t)
	controller := testDeltaController()
	require.NoError(t, k.SetAuthorizedDeltaController(ctx, controller))
	_, err := k.ApplyReputationDelta(ctx, controller, testReputationDelta("delta:genesis"))
	require.NoError(t, err)

	gs := k.ExportGenesis(ctx)
	require.Len(t, gs.AuthorizedDeltaControllers, 1)
	require.Len(t, gs.AppliedDeltas, 1)

	k2, ctx2 := setupKeeper(t)
	k2.InitGenesis(ctx2, *gs)
	require.True(t, k2.IsAuthorizedDeltaController(ctx2, controller))
	receipt, found := k2.GetAppliedReputationDelta(ctx2, "delta:genesis")
	require.True(t, found)
	require.Equal(t, int32(507), receipt.NewScore)
}
