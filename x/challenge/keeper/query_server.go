package keeper

import (
	"context"
	"encoding/json"
	"fmt"

	storetypes "cosmossdk.io/store/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/challenge/types"
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

// GetPendingChallenges 查询指定矿工的待处理挑战
func (q queryServer) GetPendingChallenges(goCtx context.Context, req *types.QueryPendingChallengesRequest) (*types.QueryPendingChallengesResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if req == nil || req.MinerAddress == "" {
		return nil, fmt.Errorf("invalid request: miner address required")
	}

	// 获取当前 epoch
	currentEpoch := uint64(ctx.BlockHeight()) / 10 // epoch 长度 = 10 blocks

	store := ctx.KVStore(q.storeKey)
	var challenges []types.Challenge

	// 遍历当前 epoch 的挑战
	prefix := []byte(fmt.Sprintf("challenge:ch-%d-", currentEpoch))
	iter := storetypes.KVStorePrefixIterator(store, prefix)
	defer iter.Close()

	for ; iter.Valid(); iter.Next() {
		var ch types.Challenge
		if err := json.Unmarshal(iter.Value(), &ch); err != nil {
			continue
		}

		// 检查是否分配给该矿工
		assigned := false
		for _, assignee := range ch.Assignees {
			if assignee == req.MinerAddress {
				assigned = true
				break
			}
		}

		if !assigned {
			continue
		}

		// 检查是否已经 revealed
		if _, revealed := ch.Reveals[req.MinerAddress]; revealed {
			continue
		}

		// 挑战状态为 pending 或 commit
		if ch.Status == types.ChallengeStatusPending || ch.Status == types.ChallengeStatusCommit {
			challenges = append(challenges, ch)
		}
	}

	return &types.QueryPendingChallengesResponse{
		Challenges: challenges,
	}, nil
}

// GetChallenge 查询单个挑战详情
func (q queryServer) GetChallenge(goCtx context.Context, req *types.QueryChallengeRequest) (*types.QueryChallengeResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if req == nil || req.ChallengeId == "" {
		return nil, fmt.Errorf("invalid request: challenge ID required")
	}

	store := ctx.KVStore(q.storeKey)
	key := []byte(fmt.Sprintf("challenge:%s", req.ChallengeId))
	bz := store.Get(key)
	if bz == nil {
		return nil, types.ErrChallengeNotFound
	}

	var ch types.Challenge
	if err := json.Unmarshal(bz, &ch); err != nil {
		return nil, fmt.Errorf("failed to unmarshal challenge: %w", err)
	}

	return &types.QueryChallengeResponse{
		Challenge: ch,
	}, nil
}
