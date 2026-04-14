package keeper

import (
	"context"

	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/settlement/types"
)

type msgServer struct {
	Keeper
}

func NewMsgServerImpl(keeper Keeper) types.MsgServer {
	return &msgServer{Keeper: keeper}
}

var _ types.MsgServer = msgServer{}

func (s msgServer) AnchorSettlementBatch(
	goCtx context.Context,
	msg *types.MsgAnchorSettlementBatch,
) (*types.MsgAnchorSettlementBatchResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if err := msg.ValidateBasic(); err != nil {
		return nil, err
	}
	if s.Keeper.HasSettlementAnchor(ctx, msg.SettlementBatchId) {
		ctx.EventManager().EmitEvent(sdk.NewEvent(
			"settlement_anchor_recorded",
			sdk.NewAttribute("settlement_batch_id", msg.SettlementBatchId),
			sdk.NewAttribute("anchor_job_id", msg.AnchorJobId),
			sdk.NewAttribute("submitter", msg.Submitter),
			sdk.NewAttribute("canonical_root", msg.CanonicalRoot),
			sdk.NewAttribute("anchor_status", "already_anchored"),
		))
		return &types.MsgAnchorSettlementBatchResponse{
			SettlementBatchId: msg.SettlementBatchId,
		}, nil
	}

	anchor := types.NewSettlementAnchor(msg, ctx.BlockHeight(), ctx.BlockTime().Unix())
	if err := s.Keeper.SetSettlementAnchor(ctx, anchor); err != nil {
		return nil, err
	}

	ctx.EventManager().EmitEvent(sdk.NewEvent(
		"settlement_anchor_recorded",
		sdk.NewAttribute("settlement_batch_id", msg.SettlementBatchId),
		sdk.NewAttribute("anchor_job_id", msg.AnchorJobId),
		sdk.NewAttribute("submitter", msg.Submitter),
		sdk.NewAttribute("canonical_root", msg.CanonicalRoot),
		sdk.NewAttribute("anchor_status", "anchored"),
	))

	s.Logger(ctx).Info(
		"settlement anchor recorded",
		"settlement_batch_id", msg.SettlementBatchId,
		"anchor_job_id", msg.AnchorJobId,
		"submitter", msg.Submitter,
		"canonical_root", msg.CanonicalRoot,
	)

	return &types.MsgAnchorSettlementBatchResponse{
		SettlementBatchId: msg.SettlementBatchId,
	}, nil
}
