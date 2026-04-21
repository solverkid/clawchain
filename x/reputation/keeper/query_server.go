package keeper

import (
	"context"
	"fmt"

	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/reputation/types"
)

type queryServer struct {
	Keeper
}

// NewQueryServerImpl 创建 reputation 查询服务器。
func NewQueryServerImpl(keeper Keeper) types.QueryServer {
	return &queryServer{Keeper: keeper}
}

var _ types.QueryServer = queryServer{}

// Score 查询单个矿工的当前声誉。
func (q queryServer) Score(goCtx context.Context, req *types.QueryScoreRequest) (*types.QueryScoreResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)
	if req == nil || req.MinerAddress == "" {
		return nil, fmt.Errorf("invalid request: miner address required")
	}
	score, found := q.Keeper.GetScore(ctx, req.MinerAddress)
	if !found {
		return nil, types.ErrMinerNotFound
	}
	return &types.QueryScoreResponse{Score: score}, nil
}

// Leaderboard 查询当前排行榜。
func (q queryServer) Leaderboard(goCtx context.Context, req *types.QueryLeaderboardRequest) (*types.QueryLeaderboardResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)
	if req == nil {
		req = &types.QueryLeaderboardRequest{}
	}
	return &types.QueryLeaderboardResponse{
		Scores: q.Keeper.GetLeaderboard(ctx, int(req.Limit)),
	}, nil
}
