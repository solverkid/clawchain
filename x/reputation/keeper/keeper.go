package keeper

import (
	"encoding/json"
	"fmt"

	"cosmossdk.io/log"
	storetypes "cosmossdk.io/store/types"
	"github.com/cosmos/cosmos-sdk/codec"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/reputation/types"
)

// Keeper 声誉模块 keeper
type Keeper struct {
	cdc      codec.BinaryCodec
	storeKey storetypes.StoreKey
}

// NewKeeper 创建 keeper
func NewKeeper(cdc codec.BinaryCodec, storeKey storetypes.StoreKey) Keeper {
	return Keeper{cdc: cdc, storeKey: storeKey}
}

// Logger 日志
func (k Keeper) Logger(ctx sdk.Context) log.Logger {
	return ctx.Logger().With("module", "x/"+types.ModuleName)
}

// InitGenesis 初始化创世
func (k Keeper) InitGenesis(ctx sdk.Context, gs types.GenesisState) {
	store := ctx.KVStore(k.storeKey)
	for _, score := range gs.Scores {
		bz, _ := json.Marshal(score)
		store.Set(types.GetScoreKey(score.MinerAddress), bz)
	}
}

// ExportGenesis 导出创世
func (k Keeper) ExportGenesis(ctx sdk.Context) *types.GenesisState {
	scores := k.GetAllScores(ctx)
	return &types.GenesisState{Scores: scores}
}

// GetScore 获取矿工声誉分
func (k Keeper) GetScore(ctx sdk.Context, addr string) (types.ReputationScore, bool) {
	store := ctx.KVStore(k.storeKey)
	bz := store.Get(types.GetScoreKey(addr))
	if bz == nil {
		return types.ReputationScore{}, false
	}
	var score types.ReputationScore
	json.Unmarshal(bz, &score)
	return score, true
}

// SetScore 设置矿工声誉分
func (k Keeper) SetScore(ctx sdk.Context, score types.ReputationScore) {
	store := ctx.KVStore(k.storeKey)
	score.Level = types.GetLevel(score.Score)
	score.UpdatedAt = ctx.BlockHeight()
	bz, _ := json.Marshal(score)
	store.Set(types.GetScoreKey(score.MinerAddress), bz)
}

// InitMiner 初始化矿工声誉
func (k Keeper) InitMiner(ctx sdk.Context, addr string) {
	score := types.ReputationScore{
		MinerAddress: addr,
		Score:        types.InitialScore,
		Level:        types.GetLevel(types.InitialScore),
		UpdatedAt:    ctx.BlockHeight(),
	}
	k.SetScore(ctx, score)
}

// UpdateScore 更新声誉分（加/减）
func (k Keeper) UpdateScore(ctx sdk.Context, addr string, delta int32, reason string) {
	score, found := k.GetScore(ctx, addr)
	if !found {
		k.InitMiner(ctx, addr)
		score, _ = k.GetScore(ctx, addr)
	}

	oldScore := score.Score
	score.Score += delta

	// 限制范围 0-1000
	if score.Score > types.MaxScore {
		score.Score = types.MaxScore
	}
	if score.Score < types.MinScore {
		score.Score = types.MinScore
	}

	score.Level = types.GetLevel(score.Score)
	k.SetScore(ctx, score)

	// 发出事件
	ctx.EventManager().EmitEvent(sdk.NewEvent(
		types.EventTypeScoreUpdate,
		sdk.NewAttribute(types.AttributeKeyMiner, addr),
		sdk.NewAttribute(types.AttributeKeyOldScore, fmt.Sprintf("%d", oldScore)),
		sdk.NewAttribute(types.AttributeKeyNewScore, fmt.Sprintf("%d", score.Score)),
		sdk.NewAttribute(types.AttributeKeyReason, reason),
	))

	if score.Score < types.SuspendedThreshold {
		ctx.EventManager().EmitEvent(sdk.NewEvent(
			types.EventTypeSuspend,
			sdk.NewAttribute(types.AttributeKeyMiner, addr),
		))
		k.Logger(ctx).Warn("矿工被暂停", "address", addr, "score", score.Score)
	}
}

// UpdateStreak 更新矿工连续签到天数（每次完成挑战时调用）
// blockTime 是当前区块的 Unix 秒时间戳
func (k Keeper) UpdateStreak(ctx sdk.Context, addr string, blockTime int64) {
	score, found := k.GetScore(ctx, addr)
	if !found {
		k.InitMiner(ctx, addr)
		score, _ = k.GetScore(ctx, addr)
	}

	currentDay := blockTime / 86400 // Unix 天数

	if score.LastActiveDay == 0 {
		// 首次活跃
		score.ConsecutiveDays = 1
	} else if currentDay == score.LastActiveDay {
		// 同一天，不更新
		return
	} else if currentDay == score.LastActiveDay+1 {
		// 连续天
		score.ConsecutiveDays++
	} else {
		// 中断，重置
		score.ConsecutiveDays = 1
	}
	score.LastActiveDay = currentDay

	k.SetScore(ctx, score)

	k.Logger(ctx).Info("连续签到更新",
		"address", addr,
		"consecutive_days", score.ConsecutiveDays,
		"streak_bonus", types.GetStreakBonus(score.ConsecutiveDays),
	)
}

// GetStreakInfo 获取矿工连续签到信息
func (k Keeper) GetStreakInfo(ctx sdk.Context, addr string) (consecutiveDays uint64, streakBonus uint64, found bool) {
	score, f := k.GetScore(ctx, addr)
	if !f {
		return 0, 100, false
	}
	return score.ConsecutiveDays, types.GetStreakBonus(score.ConsecutiveDays), true
}

// GetAllScores 获取所有声誉
func (k Keeper) GetAllScores(ctx sdk.Context) []types.ReputationScore {
	store := ctx.KVStore(k.storeKey)
	iter := storetypes.KVStorePrefixIterator(store, types.ScoreKeyPrefix)
	defer iter.Close()

	var scores []types.ReputationScore
	for ; iter.Valid(); iter.Next() {
		var s types.ReputationScore
		json.Unmarshal(iter.Value(), &s)
		scores = append(scores, s)
	}
	return scores
}
