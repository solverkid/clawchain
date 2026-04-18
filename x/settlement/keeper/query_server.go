package keeper

import (
	"context"
	"fmt"

	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/settlement/types"
)

type queryServer struct {
	Keeper
}

func NewQueryServerImpl(keeper Keeper) types.QueryServer {
	return &queryServer{Keeper: keeper}
}

var _ types.QueryServer = queryServer{}

func (q queryServer) SettlementAnchor(
	goCtx context.Context,
	req *types.QuerySettlementAnchorRequest,
) (*types.QuerySettlementAnchorResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)
	if req == nil || req.SettlementBatchID == "" {
		return nil, fmt.Errorf("invalid request: settlement_batch_id required")
	}
	anchor, found := q.Keeper.GetSettlementAnchor(ctx, req.SettlementBatchID)
	if !found {
		return nil, fmt.Errorf("settlement anchor not found: %s", req.SettlementBatchID)
	}
	return &types.QuerySettlementAnchorResponse{Anchor: anchor}, nil
}
