package keeper

import (
	"context"
	"fmt"

	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/poa/types"
)

// queryServer 查询服务器
type queryServer struct {
	Keeper
}

// NewQueryServerImpl 创建查询服务器
func NewQueryServerImpl(keeper Keeper) types.QueryServer {
	return &queryServer{Keeper: keeper}
}

var _ types.QueryServer = queryServer{}

// GetMiner 查询矿工信息
func (q queryServer) GetMiner(goCtx context.Context, req *types.QueryMinerRequest) (*types.QueryMinerResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if req == nil || req.MinerAddress == "" {
		return nil, fmt.Errorf("invalid request: miner address required")
	}

	miner, err := q.Keeper.GetMiner(ctx, req.MinerAddress)
	if err != nil {
		return nil, err
	}

	return &types.QueryMinerResponse{
		Miner: *miner,
	}, nil
}

// GetActiveMiners 查询所有活跃矿工
func (q queryServer) GetActiveMiners(goCtx context.Context, req *types.QueryActiveMinersRequest) (*types.QueryActiveMinersResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	miners := q.Keeper.GetActiveMiners(ctx)

	return &types.QueryActiveMinersResponse{
		Miners: miners,
	}, nil
}
