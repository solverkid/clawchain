package keeper

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/rand"

	"cosmossdk.io/log"
	storetypes "cosmossdk.io/store/types"
	"github.com/cosmos/cosmos-sdk/codec"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/challenge/types"
)

// Keeper 挑战模块 keeper
type Keeper struct {
	cdc        codec.BinaryCodec
	storeKey   storetypes.StoreKey
	params     types.Params
	bankKeeper BankKeeper // 新增：用于转账奖励
}

// BankKeeper 银行模块接口
type BankKeeper interface {
	SendCoinsFromModuleToAccount(ctx context.Context, senderModule string, recipientAddr sdk.AccAddress, amt sdk.Coins) error
	GetBalance(ctx context.Context, addr sdk.AccAddress, denom string) sdk.Coin
	MintCoins(ctx context.Context, moduleName string, amounts sdk.Coins) error
}

// NewKeeper 创建新 keeper
func NewKeeper(cdc codec.BinaryCodec, storeKey storetypes.StoreKey, bankKeeper BankKeeper) Keeper {
	return Keeper{
		cdc:        cdc,
		storeKey:   storeKey,
		params:     types.DefaultChallengeParams(),
		bankKeeper: bankKeeper,
	}
}

// Logger 日志
func (k Keeper) Logger(ctx sdk.Context) log.Logger {
	return ctx.Logger().With("module", "x/"+types.ModuleName)
}

// InitGenesis 初始化创世
func (k Keeper) InitGenesis(ctx sdk.Context, gs types.GenesisState) {
	k.params = gs.Params
	
	// Mint 10亿 uclaw 到 challenge 模块账户作为挖矿奖励池
	rewardPool := sdk.NewCoins(sdk.NewInt64Coin("uclaw", 1_000_000_000))
	if err := k.bankKeeper.MintCoins(ctx, types.ModuleName, rewardPool); err != nil {
		// InitGenesis 阶段如果 mint 失败，记录日志但不 panic（模块账户可能还没注册完）
		k.Logger(ctx).Error("初始化奖励池失败", "error", err)
	} else {
		k.Logger(ctx).Info("挖矿奖励池初始化完成", "amount", rewardPool.String())
	}
}

// ExportGenesis 导出创世
func (k Keeper) ExportGenesis(ctx sdk.Context) *types.GenesisState {
	return &types.GenesisState{
		Params: k.params,
	}
}

// GeneratePublicChallenge 生成一个公开挑战（任何矿工可参与）
func (k Keeper) GeneratePublicChallenge(ctx sdk.Context, epoch uint64) {
	blockHash := ctx.HeaderHash()
	seed := int64(epoch)
	if len(blockHash) > 0 {
		for i := 0; i < 8 && i < len(blockHash); i++ {
			seed = seed<<8 | int64(blockHash[i])
		}
	}
	rng := rand.New(rand.NewSource(seed))

	// 随机选择挑战类型（4种类型：数学、文本、逻辑、JSON、哈希）
	challengeTypes := []struct {
		ctype  types.ChallengeType
		weight int
	}{
		{types.ChallengeMath, 3},           // 数学题权重高
		{types.ChallengeTextTransform, 2},  // 文本处理
		{types.ChallengeLogic, 2},          // 逻辑推理
		{types.ChallengeJSONExtract, 2},    // JSON 提取
		{types.ChallengeHash, 1},           // 哈希计算
	}

	// 加权随机选择
	totalWeight := 0
	for _, ct := range challengeTypes {
		totalWeight += ct.weight
	}
	roll := rng.Intn(totalWeight)
	var selectedType types.ChallengeType
	cumulative := 0
	for _, ct := range challengeTypes {
		cumulative += ct.weight
		if roll < cumulative {
			selectedType = ct.ctype
			break
		}
	}

	// 根据类型生成挑战
	var prompt, answer string
	switch selectedType {
	case types.ChallengeMath:
		a := rng.Intn(900) + 100
		b := rng.Intn(900) + 100
		ops := []string{"+", "-", "*"}
		op := ops[rng.Intn(len(ops))]
		var result int
		switch op {
		case "+":
			result = a + b
		case "-":
			result = a - b
		case "*":
			result = a * b
		}
		prompt = fmt.Sprintf("计算 %d %s %d 的结果", a, op, b)
		answer = fmt.Sprintf("%d", result)

	case types.ChallengeTextTransform:
		texts := []string{"hello world", "clawchain mining", "distributed ai"}
		text := texts[rng.Intn(len(texts))]
		prompt = fmt.Sprintf("将以下文本转为大写: %s", text)
		answer = fmt.Sprintf("%s", fmt.Sprintf("%s", text))
		// 实际答案需要转大写
		var upper []rune
		for _, r := range answer {
			if r >= 'a' && r <= 'z' {
				upper = append(upper, r-32)
			} else {
				upper = append(upper, r)
			}
		}
		answer = string(upper)

	case types.ChallengeLogic:
		prompt = "如果 A > B 且 B > C，那么 A 和 C 的关系是？"
		answer = "A > C"

	case types.ChallengeJSONExtract:
		names := []string{"Alice", "Bob", "Charlie"}
		ages := []int{25, 30, 35}
		idx := rng.Intn(len(names))
		prompt = fmt.Sprintf(`从 {"name":"%s","age":%d} 中提取 name 的值`, names[idx], ages[idx])
		answer = names[idx]

	case types.ChallengeHash:
		prompt = "计算 'clawchain' 的 SHA256 前 8 位"
		// 预计算固定答案
		h := sha256.Sum256([]byte("clawchain"))
		answer = hex.EncodeToString(h[:])[:8]

	default:
		// fallback 数学题
		a := rng.Intn(100) + 1
		b := rng.Intn(100) + 1
		prompt = fmt.Sprintf("计算 %d + %d 的结果", a, b)
		answer = fmt.Sprintf("%d", a+b)
	}

	challenge := types.Challenge{
		ID:             fmt.Sprintf("ch-%d-0", epoch),
		Epoch:          epoch,
		Type:           selectedType,
		Prompt:         prompt,
		ExpectedAnswer: answer,
		Assignees:      []string{}, // 公开挑战，任何人可提交
		Status:         types.ChallengeStatusPending,
		CreatedHeight:  ctx.BlockHeight(),
		Commits:        make(map[string]string),
		Reveals:        make(map[string]string),
	}

	store := ctx.KVStore(k.storeKey)
	bz, _ := json.Marshal(challenge)
	store.Set([]byte(fmt.Sprintf("challenge:%s", challenge.ID)), bz)

	k.Logger(ctx).Info("生成公开挑战",
		"id", challenge.ID,
		"type", selectedType,
		"prompt", prompt,
		"answer", answer)
}

// GetActiveMiners 获取活跃矿工列表
func (k Keeper) GetActiveMiners(ctx sdk.Context) []string {
	store := ctx.KVStore(k.storeKey)
	var miners []string
	
	iter := storetypes.KVStorePrefixIterator(store, []byte("miner:"))
	defer iter.Close()
	
	for ; iter.Valid(); iter.Next() {
		var minerData map[string]interface{}
		if err := json.Unmarshal(iter.Value(), &minerData); err != nil {
			continue
		}
		if status, ok := minerData["status"].(string); ok && status == "active" {
			if addr, ok := minerData["address"].(string); ok {
				miners = append(miners, addr)
			}
		}
	}
	
	return miners
}

// GenerateChallenges 生成 epoch 挑战
func (k Keeper) GenerateChallenges(ctx sdk.Context, epoch uint64, activeMiners []string) []types.Challenge {
	if len(activeMiners) == 0 {
		return nil
	}

	challenges := make([]types.Challenge, 0, k.params.ChallengesPerEpoch)
	blockHash := ctx.HeaderHash()
	
	// 用区块哈希做随机种子
	seed := int64(0)
	if len(blockHash) > 0 {
		for i := 0; i < 8 && i < len(blockHash); i++ {
			seed = seed<<8 | int64(blockHash[i])
		}
	}
	rng := rand.New(rand.NewSource(seed))

	challengeTypes := []types.ChallengeType{
		types.ChallengeTextSummary,
		types.ChallengeSentiment,
		types.ChallengeEntityExtraction,
		types.ChallengeFormatConvert,
		types.ChallengeMath,
		types.ChallengeLogic,
	}

	for i := uint32(0); i < k.params.ChallengesPerEpoch; i++ {
		cType := challengeTypes[rng.Intn(len(challengeTypes))]
		prompt, expected := generateTask(cType, rng)

		// 随机选择 K 个矿工
		assignees := selectMiners(activeMiners, int(k.params.AssigneesPerChallenge), rng)

		challenge := types.Challenge{
			ID:             fmt.Sprintf("ch-%d-%d", epoch, i),
			Epoch:          epoch,
			Type:           cType,
			Prompt:         prompt,
			ExpectedAnswer: expected,
			Assignees:      assignees,
			Status:         types.ChallengeStatusPending,
			CreatedHeight:  ctx.BlockHeight(),
			Commits:        make(map[string]string),
			Reveals:        make(map[string]string),
		}
		challenges = append(challenges, challenge)
	}

	// 存储挑战
	store := ctx.KVStore(k.storeKey)
	for _, ch := range challenges {
		bz, _ := json.Marshal(ch)
		store.Set([]byte(fmt.Sprintf("challenge:%s", ch.ID)), bz)
	}

	k.Logger(ctx).Info("生成挑战", "epoch", epoch, "count", len(challenges))
	return challenges
}

// SubmitCommit 提交承诺
func (k Keeper) SubmitCommit(ctx sdk.Context, challengeID, minerAddr, commitHash string) error {
	store := ctx.KVStore(k.storeKey)
	key := []byte(fmt.Sprintf("challenge:%s", challengeID))
	bz := store.Get(key)
	if bz == nil {
		return types.ErrChallengeNotFound
	}

	var ch types.Challenge
	json.Unmarshal(bz, &ch)

	// 验证矿工是否被分配
	assigned := false
	for _, a := range ch.Assignees {
		if a == minerAddr {
			assigned = true
			break
		}
	}
	if !assigned {
		return types.ErrNotAssigned
	}

	if _, ok := ch.Commits[minerAddr]; ok {
		return types.ErrAlreadyCommitted
	}

	ch.Commits[minerAddr] = commitHash
	ch.Status = types.ChallengeStatusCommit

	bz, _ = json.Marshal(ch)
	store.Set(key, bz)
	return nil
}

// SubmitReveal 提交揭示
func (k Keeper) SubmitReveal(ctx sdk.Context, challengeID, minerAddr, answer, salt string) error {
	store := ctx.KVStore(k.storeKey)
	key := []byte(fmt.Sprintf("challenge:%s", challengeID))
	bz := store.Get(key)
	if bz == nil {
		return types.ErrChallengeNotFound
	}

	var ch types.Challenge
	json.Unmarshal(bz, &ch)

	// 验证 commit hash
	expectedHash := sha256Hash(answer + salt)
	if ch.Commits[minerAddr] != expectedHash {
		return types.ErrCommitHashMismatch
	}

	ch.Reveals[minerAddr] = answer
	ch.Status = types.ChallengeStatusReveal

	bz, _ = json.Marshal(ch)
	store.Set(key, bz)
	return nil
}

// EvaluateChallenges 评估挑战结果
func (k Keeper) EvaluateChallenges(ctx sdk.Context, epoch uint64) []types.ChallengeResult {
	store := ctx.KVStore(k.storeKey)
	var results []types.ChallengeResult

	// 遍历本 epoch 的挑战
	iter := storetypes.KVStorePrefixIterator(store, []byte(fmt.Sprintf("challenge:ch-%d-", epoch)))
	defer iter.Close()

	for ; iter.Valid(); iter.Next() {
		var ch types.Challenge
		json.Unmarshal(iter.Value(), &ch)

		result := types.ChallengeResult{ChallengeID: ch.ID}

		if len(ch.Reveals) == 0 {
			// 无人响应
			result.FailedMiners = ch.Assignees
		} else if ch.ExpectedAnswer != "" {
			// 精确匹配类
			for addr, answer := range ch.Reveals {
				if answer == ch.ExpectedAnswer {
					result.CompletedMiners = append(result.CompletedMiners, addr)
				} else {
					result.FailedMiners = append(result.FailedMiners, addr)
				}
			}
			result.ConsensusAnswer = ch.ExpectedAnswer
		} else {
			// 多数投票类
			votes := make(map[string][]string)
			for addr, answer := range ch.Reveals {
				votes[answer] = append(votes[answer], addr)
			}
			// 找多数
			var maxVotes int
			var consensus string
			for answer, addrs := range votes {
				if len(addrs) > maxVotes {
					maxVotes = len(addrs)
					consensus = answer
				}
			}
			result.ConsensusAnswer = consensus
			for addr, answer := range ch.Reveals {
				if answer == consensus {
					result.CompletedMiners = append(result.CompletedMiners, addr)
				} else {
					result.FailedMiners = append(result.FailedMiners, addr)
				}
			}
		}

		// 未响应的矿工也记为失败
		responded := make(map[string]bool)
		for addr := range ch.Reveals {
			responded[addr] = true
		}
		for _, addr := range ch.Assignees {
			if !responded[addr] {
				result.FailedMiners = append(result.FailedMiners, addr)
			}
		}

		ch.Status = types.ChallengeStatusComplete
		bz, _ := json.Marshal(ch)
		store.Set(iter.Key(), bz)

		results = append(results, result)
	}

	return results
}

// ──────────────────────────────────────────────
// 辅助函数
// ──────────────────────────────────────────────

func sha256Hash(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

func selectMiners(miners []string, k int, rng *rand.Rand) []string {
	if len(miners) <= k {
		return miners
	}
	perm := rng.Perm(len(miners))
	result := make([]string, k)
	for i := 0; i < k; i++ {
		result[i] = miners[perm[i]]
	}
	return result
}

// GetBlockReward 获取当前区块高度的挑战奖励（带减半逻辑）
func (k Keeper) GetBlockReward(height int64) int64 {
	const (
		initialReward = int64(1000)      // 初始奖励 1000 uclaw
		halvingBlocks = int64(100000)    // 每 100,000 block 减半
		minReward     = int64(10)        // 最低奖励 10 uclaw
	)

	halvings := height / halvingBlocks
	reward := initialReward
	for i := int64(0); i < halvings; i++ {
		reward = reward / 2
		if reward < minReward {
			reward = minReward
			break
		}
	}
	return reward
}

// PendingReward 待结算的奖励记录
type PendingReward struct {
	ChallengeID string `json:"challenge_id"`
	MinerAddr   string `json:"miner_addr"`
	Amount      int64  `json:"amount"`
	Height      int64  `json:"height"`
}

// AddPendingReward 添加待结算奖励
func (k Keeper) AddPendingReward(ctx sdk.Context, challengeID, minerAddr string, amount int64) {
	store := ctx.KVStore(k.storeKey)
	key := []byte(fmt.Sprintf("pending_reward:%d:%s:%s", ctx.BlockHeight(), challengeID, minerAddr))
	
	pr := PendingReward{
		ChallengeID: challengeID,
		MinerAddr:   minerAddr,
		Amount:      amount,
		Height:      ctx.BlockHeight(),
	}
	
	bz, _ := json.Marshal(pr)
	store.Set(key, bz)
}

// ProcessPendingRewards 处理所有待结算奖励（在 EndBlock 调用）
func (k Keeper) ProcessPendingRewards(ctx sdk.Context) error {
	store := ctx.KVStore(k.storeKey)
	
	// 扫描所有待结算奖励
	iter := storetypes.KVStorePrefixIterator(store, []byte("pending_reward:"))
	defer iter.Close()
	
	for ; iter.Valid(); iter.Next() {
		var pr PendingReward
		if err := json.Unmarshal(iter.Value(), &pr); err != nil {
			k.Logger(ctx).Error("解析待结算奖励失败", "error", err)
			continue
		}
		
		// 转账
		recipientAddr, err := sdk.AccAddressFromBech32(pr.MinerAddr)
		if err != nil {
			k.Logger(ctx).Error("矿工地址无效", "addr", pr.MinerAddr, "error", err)
			store.Delete(iter.Key())
			continue
		}
		
		coins := sdk.NewCoins(sdk.NewInt64Coin("uclaw", pr.Amount))
		if err := k.bankKeeper.SendCoinsFromModuleToAccount(
			ctx,
			types.ModuleName,
			recipientAddr,
			coins,
		); err != nil {
			k.Logger(ctx).Error("奖励转账失败",
				"challenge", pr.ChallengeID,
				"miner", pr.MinerAddr,
				"amount", pr.Amount,
				"error", err,
			)
			// 转账失败不删除，下次重试
			continue
		}
		
		k.Logger(ctx).Info("奖励转账成功",
			"challenge", pr.ChallengeID,
			"miner", pr.MinerAddr,
			"amount", pr.Amount,
		)
		
		// 更新矿工统计信息
		minerKey := []byte(fmt.Sprintf("miner:%s", pr.MinerAddr))
		minerBz := store.Get(minerKey)
		if minerBz != nil {
			var minerData map[string]interface{}
			if err := json.Unmarshal(minerBz, &minerData); err == nil {
				// 更新完成挑战数和总奖励
				completed := int64(0)
				totalRewards := int64(0)
				if v, ok := minerData["challenges_completed"].(float64); ok {
					completed = int64(v)
				}
				if v, ok := minerData["total_rewards"].(float64); ok {
					totalRewards = int64(v)
				}
				
				minerData["challenges_completed"] = completed + 1
				minerData["total_rewards"] = totalRewards + pr.Amount
				
				minerBz, _ = json.Marshal(minerData)
				store.Set(minerKey, minerBz)
			}
		}
		
		// 删除已结算记录
		store.Delete(iter.Key())
	}
	
	return nil
}

func generateTask(cType types.ChallengeType, rng *rand.Rand) (prompt, expected string) {
	switch cType {
	case types.ChallengeMath:
		a := rng.Intn(1000)
		b := rng.Intn(1000)
		prompt = fmt.Sprintf("计算: %d + %d = ?", a, b)
		expected = fmt.Sprintf("%d", a+b)
	case types.ChallengeLogic:
		prompt = "如果 A > B 且 B > C，那么 A 和 C 的关系是？(回答: A>C)"
		expected = "A>C"
	case types.ChallengeFormatConvert:
		prompt = `将 JSON 转为 CSV: {"name":"Alice","age":30}`
		expected = "name,age\nAlice,30"
	case types.ChallengeSentiment:
		prompts := []string{
			"分析情感（正面/负面/中性）: Bitcoin突破历史新高",
			"分析情感（正面/负面/中性）: 全球股市暴跌",
			"分析情感（正面/负面/中性）: 天气晴朗",
		}
		prompt = prompts[rng.Intn(len(prompts))]
		// 模糊匹配类无固定答案
	case types.ChallengeTextSummary:
		prompt = "用一句话总结：AI Agent 是一种能够自主执行任务的人工智能系统，它可以理解指令、规划步骤、使用工具并完成目标。"
	case types.ChallengeEntityExtraction:
		prompt = "提取人名和组织：Elon Musk announced that Tesla will invest $10 billion in AI research."
	default:
		prompt = fmt.Sprintf("计算: %d * %d = ?", rng.Intn(100), rng.Intn(100))
		a := rng.Intn(100)
		b := rng.Intn(100)
		expected = fmt.Sprintf("%d", a*b)
	}
	return
}
