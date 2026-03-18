package keeper

import (
	"context"
	"fmt"

	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/challenge/types"
)

// msgServer 消息服务器
type msgServer struct {
	Keeper
}

// NewMsgServerImpl 创建消息服务器
func NewMsgServerImpl(keeper Keeper) types.MsgServer {
	return &msgServer{Keeper: keeper}
}

var _ types.MsgServer = msgServer{}

// SubmitCommit 处理提交 commit 消息
func (s msgServer) SubmitCommit(goCtx context.Context, msg *types.MsgSubmitCommit) (*types.MsgSubmitCommitResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if err := msg.ValidateBasic(); err != nil {
		return nil, err
	}

	// 提交 commit
	if err := s.Keeper.SubmitCommit(ctx, msg.ChallengeId, msg.MinerAddress, msg.CommitHash); err != nil {
		return nil, err
	}

	// 发出事件
	ctx.EventManager().EmitEvent(sdk.NewEvent(
		types.EventTypeCommitSubmitted,
		sdk.NewAttribute(types.AttributeKeyChallengeID, msg.ChallengeId),
		sdk.NewAttribute(types.AttributeKeyMiner, msg.MinerAddress),
		sdk.NewAttribute(types.AttributeKeyCommitHash, msg.CommitHash),
	))

	s.Logger(ctx).Info("Commit submitted",
		"challenge_id", msg.ChallengeId,
		"miner", msg.MinerAddress,
	)

	return &types.MsgSubmitCommitResponse{}, nil
}

// SubmitReveal 处理提交 reveal 消息
func (s msgServer) SubmitReveal(goCtx context.Context, msg *types.MsgSubmitReveal) (*types.MsgSubmitRevealResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if err := msg.ValidateBasic(); err != nil {
		return nil, err
	}

	// 提交 reveal
	if err := s.Keeper.SubmitReveal(ctx, msg.ChallengeId, msg.MinerAddress, msg.Answer, msg.Salt); err != nil {
		return nil, err
	}

	// 发出事件
	ctx.EventManager().EmitEvent(sdk.NewEvent(
		types.EventTypeRevealSubmitted,
		sdk.NewAttribute(types.AttributeKeyChallengeID, msg.ChallengeId),
		sdk.NewAttribute(types.AttributeKeyMiner, msg.MinerAddress),
		sdk.NewAttribute(types.AttributeKeyAnswer, fmt.Sprintf("%d bytes", len(msg.Answer))),
	))

	s.Logger(ctx).Info("Reveal submitted",
		"challenge_id", msg.ChallengeId,
		"miner", msg.MinerAddress,
	)

	return &types.MsgSubmitRevealResponse{}, nil
}
