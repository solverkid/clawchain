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
	cdc              codec.BinaryCodec
	storeKey         storetypes.StoreKey
	params           types.Params
	bankKeeper       BankKeeper       // 用于转账奖励
	reputationKeeper ReputationKeeper // 用于声誉检查和更新
}

// BankKeeper 银行模块接口
type BankKeeper interface {
	SendCoinsFromModuleToAccount(ctx context.Context, senderModule string, recipientAddr sdk.AccAddress, amt sdk.Coins) error
	GetBalance(ctx context.Context, addr sdk.AccAddress, denom string) sdk.Coin
	MintCoins(ctx context.Context, moduleName string, amounts sdk.Coins) error
}

// ReputationKeeper 声誉模块接口（用于 tier 检查和 spot check 惩罚/奖励）
type ReputationKeeper interface {
	GetMinerScore(ctx sdk.Context, addr string) (int32, bool)
	UpdateScore(ctx sdk.Context, addr string, delta int32, reason string)
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

// SetReputationKeeper 设置声誉 keeper（避免循环依赖，在 app 层设置）
func (k *Keeper) SetReputationKeeper(rk ReputationKeeper) {
	k.reputationKeeper = rk
}

// StoreKey 返回存储 key（供测试使用）
func (k Keeper) StoreKey() storetypes.StoreKey {
	return k.storeKey
}

// Logger 日志
func (k Keeper) Logger(ctx sdk.Context) log.Logger {
	return ctx.Logger().With("module", "x/"+types.ModuleName)
}

// ========================================
// LLM 挑战内容池
// ========================================

// 文本摘要挑战池（200-500字文章）
var textSummaryPool = []string{
	"人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。该领域的研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。AI的核心问题包括建造能够跟人类似甚至超卓的推理、知识、规划、学习、交流、感知、移物、使用工具和操控机械的能力等。当前AI技术已在医疗诊断、金融分析、自动驾驶、智能客服等领域得到广泛应用。",
	"区块链是一种分布式数据存储、点对点传输、共识机制、加密算法等计算机技术的新型应用模式。本质上是一个去中心化的数据库，同时作为比特币的底层技术，是一串使用密码学方法相关联产生的数据块。每个数据块中包含了一批次比特币网络交易的信息，用于验证其信息的有效性和生成下一个区块。区块链技术的特点包括去中心化、开放性、自治性、信息不可篡改、匿名性等。目前在金融、供应链管理、数字版权、物联网等领域都有应用探索。",
	"量子计算是一种遵循量子力学规律调控量子信息单元进行计算的新型计算模式。传统计算机使用比特（0或1）作为信息的基本单位，而量子计算机使用量子比特（可以同时处于0和1的叠加态）。这使得量子计算机在处理某些特定问题时，理论上可以达到指数级的加速。量子计算在密码破解、药物研发、材料科学、优化问题等领域展现出巨大潜力。目前IBM、Google、中国科学技术大学等机构都在积极研发量子计算机，但距离大规模实用化还有很长的路要走。",
	"Web3是下一代互联网的愿景，它基于区块链技术，旨在创建一个去中心化的网络。与Web2（当前互联网）不同，Web3中用户拥有自己的数据和数字资产，不再依赖于中心化的平台。Web3的核心特征包括：去中心化身份（DID）、加密货币钱包、智能合约、去中心化应用（DApp）等。Web3有望改变社交媒体、游戏、金融、内容创作等多个领域，让用户真正成为互联网的主人而不是产品。然而，Web3也面临技术复杂度高、用户体验不佳、监管不明确等挑战。",
	"机器学习是人工智能的一个分支，它使计算机能够在没有明确编程的情况下学习。机器学习算法通过分析大量数据来识别模式，并据此做出预测或决策。主要分为监督学习、无监督学习和强化学习三大类。深度学习是机器学习的一个子集，它使用多层神经网络来处理复杂的数据模式。机器学习已经在图像识别、语音识别、推荐系统、自然语言处理等领域取得了突破性进展。随着算力提升和数据积累，机器学习的应用场景还在不断扩大，但也面临数据隐私、算法偏见等伦理挑战。",
}

// 情感分析挑战池（正面/负面/中性）
var sentimentPool = []struct {
	text     string
	expected string
}{
	{"比特币突破历史新高，加密市场迎来牛市", "正面"},
	{"全球股市暴跌，投资者恐慌性抛售", "负面"},
	{"今天天气晴朗，适合出门散步", "正面"},
	{"项目进度延期，团队压力很大", "负面"},
	{"会议按计划进行，各方达成共识", "中性"},
	{"产品获得用户高度评价，销量大增", "正面"},
	{"系统出现严重漏洞，数据泄露风险高", "负面"},
	{"公司宣布裁员计划，员工士气低落", "负面"},
	{"新技术发布，行业格局可能改变", "中性"},
	{"研究取得重大突破，论文发表在顶级期刊", "正面"},
}

// 翻译挑战池（英译中）
var translationPool = []struct {
	english string
	chinese string
}{
	{"The quick brown fox jumps over the lazy dog", "敏捷的棕色狐狸跳过懒狗"},
	{"Artificial intelligence is transforming the world", "人工智能正在改变世界"},
	{"Blockchain technology enables decentralized applications", "区块链技术使去中心化应用成为可能"},
	{"Machine learning algorithms can predict future trends", "机器学习算法可以预测未来趋势"},
	{"Cryptocurrency adoption is growing rapidly worldwide", "加密货币在全球范围内的采用正在快速增长"},
	{"Quantum computing promises exponential speedup", "量子计算承诺指数级加速"},
	{"Smart contracts automate agreement execution", "智能合约自动化协议执行"},
	{"Data privacy is a fundamental human right", "数据隐私是一项基本人权"},
	{"Cloud computing provides scalable infrastructure", "云计算提供可扩展的基础设施"},
	{"Open source software drives innovation", "开源软件推动创新"},
}

// 文本分类挑战池（科技/金融/体育/娱乐/政治）
var classificationPool = []struct {
	text     string
	expected string
}{
	{"OpenAI发布GPT-5模型，性能大幅提升", "科技"},
	{"美联储宣布加息25个基点，市场反应平淡", "金融"},
	{"世界杯决赛阿根廷夺冠，梅西圆梦", "体育"},
	{"新电影票房破10亿，刷新历史纪录", "娱乐"},
	{"联合国安理会通过新决议，呼吁停火", "政治"},
	{"SpaceX成功发射星际飞船，马斯克庆祝", "科技"},
	{"比特币价格突破10万美元，创历史新高", "金融"},
	{"NBA总决赛进入抢七，悬念丛生", "体育"},
	{"奥斯卡颁奖典礼落幕，最佳影片揭晓", "娱乐"},
	{"欧盟峰会讨论气候变化政策", "政治"},
	{"量子计算机实现新突破，算力提升百倍", "科技"},
	{"全球股市集体大涨，道指创新高", "金融"},
	{"奥运会中国代表团夺得金牌榜第一", "体育"},
	{"顶级歌手演唱会门票秒光", "娱乐"},
	{"G20峰会在京召开，讨论全球经济", "政治"},
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

	// 随机选择挑战类型（优先 LLM 挑战）
	challengeTypes := []struct {
		ctype  types.ChallengeType
		weight int
	}{
		{types.ChallengeTextSummary, 5},      // 文本摘要（需要 LLM）
		{types.ChallengeSentiment, 5},        // 情感分析（需要 LLM）
		{types.ChallengeTranslation, 5},      // 翻译（需要 LLM）
		{types.ChallengeClassification, 5},   // 文本分类（需要 LLM）
		{types.ChallengeMath, 2},             // 数学题（可本地计算）
		{types.ChallengeLogic, 3},            // 逻辑推理（需要 LLM）
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

	// 根据类型从内容池生成挑战
	var prompt, answer string
	switch selectedType {
	case types.ChallengeTextSummary:
		// 文本摘要：从池中随机选择
		text := textSummaryPool[rng.Intn(len(textSummaryPool))]
		prompt = fmt.Sprintf("将以下文章摘要为不超过50字：\n\n%s", text)
		answer = "" // 无固定答案，由多数投票决定

	case types.ChallengeSentiment:
		// 情感分析：从池中随机选择
		item := sentimentPool[rng.Intn(len(sentimentPool))]
		prompt = fmt.Sprintf("判断以下评论的情感倾向（正面/负面/中性）：%s", item.text)
		answer = item.expected

	case types.ChallengeTranslation:
		// 翻译：从池中随机选择
		item := translationPool[rng.Intn(len(translationPool))]
		prompt = fmt.Sprintf("将以下英文翻译为中文：%s", item.english)
		answer = item.chinese

	case types.ChallengeClassification:
		// 文本分类：从池中随机选择
		item := classificationPool[rng.Intn(len(classificationPool))]
		prompt = fmt.Sprintf("将以下文本分类到最合适的类别（科技/金融/体育/娱乐/政治）：%s", item.text)
		answer = item.expected

	case types.ChallengeMath:
		// 数学题：动态生成
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

	case types.ChallengeLogic:
		// 逻辑推理
		prompt = "如果 A > B 且 B > C，那么 A 和 C 的关系是？(回答格式: A>C)"
		answer = "A>C"

	default:
		// fallback 数学题
		a := rng.Intn(100) + 1
		b := rng.Intn(100) + 1
		prompt = fmt.Sprintf("计算 %d + %d 的结果", a, b)
		answer = fmt.Sprintf("%d", a+b)
	}

	tier := types.GetTaskTier(selectedType)

	// Spot Check: 10% 概率
	isSpotCheck := rng.Intn(10) == 0
	knownAnswer := ""
	if isSpotCheck && answer != "" {
		knownAnswer = answer
	} else if isSpotCheck && answer == "" {
		// 无固定答案的题目不适合做 spot check
		isSpotCheck = false
	}

	challenge := types.Challenge{
		ID:             fmt.Sprintf("ch-%d-0", epoch),
		Epoch:          epoch,
		Type:           selectedType,
		Tier:           tier,
		Prompt:         prompt,
		ExpectedAnswer: answer,
		Assignees:      []string{}, // 公开挑战，任何人可提交
		Status:         types.ChallengeStatusPending,
		CreatedHeight:  ctx.BlockHeight(),
		Commits:        make(map[string]string),
		Reveals:        make(map[string]string),
		IsSpotCheck:    isSpotCheck,
		KnownAnswer:    knownAnswer,
	}

	store := ctx.KVStore(k.storeKey)
	bz, _ := json.Marshal(challenge)
	store.Set([]byte(fmt.Sprintf("challenge:%s", challenge.ID)), bz)

	k.Logger(ctx).Info("生成公开挑战",
		"id", challenge.ID,
		"type", selectedType,
		"tier", tier,
		"is_spot_check", isSpotCheck,
		"prompt", prompt[:50]+"...",
		"has_expected_answer", answer != "")
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

		tier := types.GetTaskTier(cType)

		// Spot Check: 10% 概率（仅对有预设答案的题目）
		isSpotCheck := rng.Intn(10) == 0
		knownAnswer := ""
		if isSpotCheck && expected != "" {
			knownAnswer = expected
		} else if isSpotCheck && expected == "" {
			isSpotCheck = false
		}

		challenge := types.Challenge{
			ID:             fmt.Sprintf("ch-%d-%d", epoch, i),
			Epoch:          epoch,
			Type:           cType,
			Tier:           tier,
			Prompt:         prompt,
			ExpectedAnswer: expected,
			Assignees:      assignees,
			Status:         types.ChallengeStatusPending,
			CreatedHeight:  ctx.BlockHeight(),
			Commits:        make(map[string]string),
			Reveals:        make(map[string]string),
			IsSpotCheck:    isSpotCheck,
			KnownAnswer:    knownAnswer,
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

// SubmitAnswerWithChecks 提交答案并检查 Tier 声誉门槛和 Spot Check
func (k Keeper) SubmitAnswerWithChecks(ctx sdk.Context, challengeID, minerAddr, answer string) error {
	store := ctx.KVStore(k.storeKey)
	key := []byte(fmt.Sprintf("challenge:%s", challengeID))
	bz := store.Get(key)
	if bz == nil {
		return types.ErrChallengeNotFound
	}

	var ch types.Challenge
	json.Unmarshal(bz, &ch)

	// 检查 Tier 声誉门槛
	minRep := types.MinReputationForTier(ch.Tier)
	if minRep > 0 && k.reputationKeeper != nil {
		score, found := k.reputationKeeper.GetMinerScore(ctx, minerAddr)
		if !found {
			score = 500 // 默认初始分
		}
		if score < minRep {
			return types.ErrInsufficientReputation
		}
	}

	// 记录答案
	if ch.Reveals == nil {
		ch.Reveals = make(map[string]string)
	}
	ch.Reveals[minerAddr] = answer

	// Spot Check 验证
	if ch.IsSpotCheck && ch.KnownAnswer != "" && k.reputationKeeper != nil {
		if answer != ch.KnownAnswer {
			// 答错：声誉 -50
			k.reputationKeeper.UpdateScore(ctx, minerAddr, -50, "spot_check_failed")
			k.Logger(ctx).Warn("Spot Check 失败",
				"challenge", challengeID,
				"miner", minerAddr,
			)
		} else {
			// 答对：声誉 +10
			k.reputationKeeper.UpdateScore(ctx, minerAddr, 10, "spot_check_passed")
			k.Logger(ctx).Info("Spot Check 通过",
				"challenge", challengeID,
				"miner", minerAddr,
			)
		}
	}

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

// GetBlockReward 获取当前区块高度对应 epoch 的矿工池奖励（带减半逻辑）
// 返回值单位: uclaw。每 epoch 总奖励 50 CLAW = 50,000,000 uclaw，其中矿工池 60% = 30,000,000 uclaw。
// 此函数返回矿工池部分，按活跃矿工数分配给各矿工。
func (k Keeper) GetBlockReward(height int64) int64 {
	const (
		epochBlocks       = int64(100)
		initialMinerPool  = int64(30_000_000) // 30 CLAW in uclaw (60% of 50 CLAW epoch reward)
		halvingEpochs     = int64(210_000)
		minReward         = int64(1)          // 最低奖励 1 uclaw
	)

	epoch := height / epochBlocks
	halvings := epoch / halvingEpochs
	reward := initialMinerPool
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
