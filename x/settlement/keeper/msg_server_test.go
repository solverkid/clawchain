package keeper_test

import (
	"bytes"
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

	"github.com/clawchain/clawchain/x/settlement/keeper"
	"github.com/clawchain/clawchain/x/settlement/types"
)

func setupSettlementMsgServer(t *testing.T) (types.MsgServer, keeper.Keeper, sdk.Context) {
	storeKey := storetypes.NewKVStoreKey(types.StoreKey)

	db := dbm.NewMemDB()
	stateStore := store.NewCommitMultiStore(db, log.NewNopLogger(), metrics.NewNoOpMetrics())
	stateStore.MountStoreWithDB(storeKey, storetypes.StoreTypeIAVL, db)
	require.NoError(t, stateStore.LoadLatestVersion())

	registry := codectypes.NewInterfaceRegistry()
	cdc := codec.NewProtoCodec(registry)

	k := keeper.NewKeeper(cdc, storeKey)
	ctx := sdk.NewContext(stateStore, cmtproto.Header{Height: 7, Time: time.Now()}, false, log.NewNopLogger())
	return keeper.NewMsgServerImpl(k), k, ctx
}

func testAnchorMsg() *types.MsgAnchorSettlementBatch {
	return &types.MsgAnchorSettlementBatch{
		Submitter:           sdk.AccAddress(bytes.Repeat([]byte{0x01}, 20)).String(),
		SettlementBatchId:   "sb_2026_04_10_0001",
		AnchorJobId:         "anchor_job_01",
		Lane:                "fast",
		SchemaVersion:       "settlement.v1",
		CanonicalRoot:       "sha256:canonical",
		AnchorPayloadHash:   "sha256:payload",
		RewardWindowIdsRoot: "sha256:windows",
		TaskRunIdsRoot:      "sha256:tasks",
		MinerRewardRowsRoot: "sha256:miners",
		WindowEndAt:         "2026-04-10T03:15:00Z",
		TotalRewardAmount:   12345,
	}
}

func TestAnchorSettlementBatchIsIdempotentWhenAlreadyAnchored(t *testing.T) {
	msgServer, k, ctx := setupSettlementMsgServer(t)
	msg := testAnchorMsg()

	firstResp, err := msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), msg)
	require.NoError(t, err)
	require.Equal(t, msg.SettlementBatchId, firstResp.SettlementBatchId)

	secondResp, err := msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), msg)
	require.NoError(t, err)
	require.Equal(t, msg.SettlementBatchId, secondResp.SettlementBatchId)

	anchor, found := k.GetSettlementAnchor(ctx, msg.SettlementBatchId)
	require.True(t, found)
	require.Equal(t, msg.CanonicalRoot, anchor.CanonicalRoot)

	events := ctx.EventManager().Events()
	require.Len(t, events, 2)
	require.Equal(t, "settlement_anchor_recorded", events[1].Type)
	require.Equal(t, "anchor_status", string(events[1].Attributes[4].Key))
	require.Equal(t, "already_anchored", string(events[1].Attributes[4].Value))
}

func TestAnchorSettlementBatchRejectsDuplicateWithDifferentRoot(t *testing.T) {
	msgServer, k, ctx := setupSettlementMsgServer(t)
	msg := testAnchorMsg()

	_, err := msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), msg)
	require.NoError(t, err)

	conflicting := *msg
	conflicting.CanonicalRoot = "sha256:canonical-mutated"
	conflicting.AnchorPayloadHash = "sha256:payload-mutated"
	_, err = msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), &conflicting)
	require.Error(t, err)
	require.Contains(t, err.Error(), "settlement anchor conflict")

	anchor, found := k.GetSettlementAnchor(ctx, msg.SettlementBatchId)
	require.True(t, found)
	require.Equal(t, msg.CanonicalRoot, anchor.CanonicalRoot)
	require.Equal(t, msg.AnchorPayloadHash, anchor.AnchorPayloadHash)
}
