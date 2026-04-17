package keeper_test

import (
	"bytes"
	"strings"
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

func setupSettlementMsgServer(t *testing.T, authorizedSubmitters ...string) (types.MsgServer, keeper.Keeper, sdk.Context) {
	storeKey := storetypes.NewKVStoreKey(types.StoreKey)

	db := dbm.NewMemDB()
	stateStore := store.NewCommitMultiStore(db, log.NewNopLogger(), metrics.NewNoOpMetrics())
	stateStore.MountStoreWithDB(storeKey, storetypes.StoreTypeIAVL, db)
	require.NoError(t, stateStore.LoadLatestVersion())

	registry := codectypes.NewInterfaceRegistry()
	cdc := codec.NewProtoCodec(registry)

	k := keeper.NewKeeper(cdc, storeKey)
	ctx := sdk.NewContext(stateStore, cmtproto.Header{Height: 7, Time: time.Now()}, false, log.NewNopLogger())
	k.InitGenesis(ctx, types.GenesisState{AuthorizedSubmitters: authorizedSubmitters})
	return keeper.NewMsgServerImpl(k), k, ctx
}

func testAnchorSubmitter() string {
	return sdk.AccAddress(bytes.Repeat([]byte{0x01}, 20)).String()
}

func testAnchorMsg() *types.MsgAnchorSettlementBatch {
	return &types.MsgAnchorSettlementBatch{
		Submitter:           testAnchorSubmitter(),
		SettlementBatchId:   "sb_2026_04_10_0001",
		AnchorJobId:         "anchor_job_01",
		Lane:                "fast",
		SchemaVersion:       "settlement.v1",
		PolicyBundleVersion: "policy.v1",
		CanonicalRoot:       "sha256:" + strings.Repeat("a", 64),
		AnchorPayloadHash:   "sha256:" + strings.Repeat("b", 64),
		RewardWindowIdsRoot: "sha256:" + strings.Repeat("c", 64),
		TaskRunIdsRoot:      "sha256:" + strings.Repeat("d", 64),
		MinerRewardRowsRoot: "sha256:" + strings.Repeat("e", 64),
		WindowEndAt:         "2026-04-10T03:15:00Z",
		TotalRewardAmount:   12345,
	}
}

func TestAnchorSettlementBatchIsIdempotentWhenAlreadyAnchored(t *testing.T) {
	msgServer, k, ctx := setupSettlementMsgServer(t, testAnchorSubmitter())
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
	msgServer, k, ctx := setupSettlementMsgServer(t, testAnchorSubmitter())
	msg := testAnchorMsg()

	_, err := msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), msg)
	require.NoError(t, err)

	conflicting := *msg
	conflicting.CanonicalRoot = "sha256:" + strings.Repeat("f", 64)
	conflicting.AnchorPayloadHash = "sha256:" + strings.Repeat("0", 64)
	_, err = msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), &conflicting)
	require.Error(t, err)
	require.Contains(t, err.Error(), "settlement anchor conflict")

	anchor, found := k.GetSettlementAnchor(ctx, msg.SettlementBatchId)
	require.True(t, found)
	require.Equal(t, msg.CanonicalRoot, anchor.CanonicalRoot)
	require.Equal(t, msg.AnchorPayloadHash, anchor.AnchorPayloadHash)
}

func TestAnchorSettlementBatchRejectsDuplicateWithMetadataDrift(t *testing.T) {
	msgServer, k, ctx := setupSettlementMsgServer(t, testAnchorSubmitter())
	msg := testAnchorMsg()

	_, err := msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), msg)
	require.NoError(t, err)

	conflicting := *msg
	conflicting.PolicyBundleVersion = "policy.v2"
	conflicting.TotalRewardAmount = msg.TotalRewardAmount - 1
	_, err = msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), &conflicting)
	require.Error(t, err)
	require.Contains(t, err.Error(), "settlement anchor conflict")

	anchor, found := k.GetSettlementAnchor(ctx, msg.SettlementBatchId)
	require.True(t, found)
	require.Equal(t, msg.PolicyBundleVersion, anchor.PolicyBundleVersion)
	require.Equal(t, msg.TotalRewardAmount, anchor.TotalRewardAmount)
}

func TestAnchorSettlementBatchRejectsUnauthorizedSubmitter(t *testing.T) {
	msgServer, k, ctx := setupSettlementMsgServer(t)
	msg := testAnchorMsg()

	_, err := msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), msg)
	require.Error(t, err)
	require.Contains(t, err.Error(), "unauthorized settlement anchor submitter")

	require.False(t, k.HasSettlementAnchor(ctx, msg.SettlementBatchId))
}

func TestQuerySettlementAnchorReturnsStoredAnchor(t *testing.T) {
	msgServer, k, ctx := setupSettlementMsgServer(t, testAnchorSubmitter())
	msg := testAnchorMsg()
	_, err := msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), msg)
	require.NoError(t, err)

	queryServer := keeper.NewQueryServerImpl(k)
	resp, err := queryServer.SettlementAnchor(
		sdk.WrapSDKContext(ctx),
		&types.QuerySettlementAnchorRequest{SettlementBatchId: msg.SettlementBatchId},
	)

	require.NoError(t, err)
	require.Equal(t, msg.CanonicalRoot, resp.Anchor.CanonicalRoot)
	require.Equal(t, msg.AnchorPayloadHash, resp.Anchor.AnchorPayloadHash)
}
