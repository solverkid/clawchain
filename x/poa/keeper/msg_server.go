package keeper

import (
	"context"
	"fmt"

	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/poa/types"
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

// RegisterMiner 处理矿工注册消息
func (s msgServer) RegisterMiner(goCtx context.Context, msg *types.MsgRegisterMiner) (*types.MsgRegisterMinerResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if err := msg.ValidateBasic(); err != nil {
		return nil, err
	}

	// 注册矿工
	if err := s.Keeper.RegisterMiner(ctx, msg.MinerAddress); err != nil {
		return nil, err
	}

	// 如果有初始质押，执行质押
	if msg.StakeAmount > 0 {
		if err := s.Keeper.StakeMiner(ctx, msg.MinerAddress, msg.StakeAmount); err != nil {
			return nil, fmt.Errorf("stake failed: %w", err)
		}
	}

	// 发出事件
	ctx.EventManager().EmitEvent(sdk.NewEvent(
		types.EventTypeMinerRegistered,
		sdk.NewAttribute(types.AttributeKeyMiner, msg.MinerAddress),
		sdk.NewAttribute(types.AttributeKeyStake, fmt.Sprintf("%d", msg.StakeAmount)),
	))

	s.Logger(ctx).Info("Miner registered",
		"address", msg.MinerAddress,
		"stake", msg.StakeAmount,
	)

	return &types.MsgRegisterMinerResponse{}, nil
}

// StakeMiner 处理质押消息
func (s msgServer) StakeMiner(goCtx context.Context, msg *types.MsgStakeMiner) (*types.MsgStakeMinerResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if err := msg.ValidateBasic(); err != nil {
		return nil, err
	}

	// 执行质押
	if err := s.Keeper.StakeMiner(ctx, msg.MinerAddress, msg.Amount); err != nil {
		return nil, err
	}

	// 发出事件
	ctx.EventManager().EmitEvent(sdk.NewEvent(
		types.EventTypeMinerStaked,
		sdk.NewAttribute(types.AttributeKeyMiner, msg.MinerAddress),
		sdk.NewAttribute(types.AttributeKeyAmount, fmt.Sprintf("%d", msg.Amount)),
	))

	s.Logger(ctx).Info("Miner staked",
		"address", msg.MinerAddress,
		"amount", msg.Amount,
	)

	return &types.MsgStakeMinerResponse{}, nil
}

// UnstakeMiner 处理解质押消息
func (s msgServer) UnstakeMiner(goCtx context.Context, msg *types.MsgUnstakeMiner) (*types.MsgUnstakeMinerResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if err := msg.ValidateBasic(); err != nil {
		return nil, err
	}

	// 执行解质押
	if err := s.Keeper.UnstakeMiner(ctx, msg.MinerAddress, msg.Amount); err != nil {
		return nil, err
	}

	// 发出事件
	ctx.EventManager().EmitEvent(sdk.NewEvent(
		types.EventTypeMinerUnstaked,
		sdk.NewAttribute(types.AttributeKeyMiner, msg.MinerAddress),
		sdk.NewAttribute(types.AttributeKeyAmount, fmt.Sprintf("%d", msg.Amount)),
	))

	s.Logger(ctx).Info("Miner unstaked",
		"address", msg.MinerAddress,
		"amount", msg.Amount,
	)

	return &types.MsgUnstakeMinerResponse{}, nil
}
