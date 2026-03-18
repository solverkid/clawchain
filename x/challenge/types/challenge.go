package types

// ChallengeType 挑战类型
type ChallengeType string

const (
	ChallengeTextSummary      ChallengeType = "text_summary"       // 文本摘要（需要 LLM）
	ChallengeSentiment        ChallengeType = "sentiment"          // 情感分析（需要 LLM）
	ChallengeTranslation      ChallengeType = "translation"        // 翻译（需要 LLM）
	ChallengeClassification   ChallengeType = "classification"     // 文本分类（需要 LLM）
	ChallengeEntityExtraction ChallengeType = "entity_extraction"  // 实体抽取（需要 LLM）
	ChallengeFormatConvert    ChallengeType = "format_convert"     // 格式转换
	ChallengeMath             ChallengeType = "math"               // 数学计算
	ChallengeLogic            ChallengeType = "logic"              // 逻辑推理（需要 LLM）
	ChallengeTextTransform    ChallengeType = "text_transform"     // 文本转换（大写等）
	ChallengeJSONExtract      ChallengeType = "json_extract"       // JSON 提取
	ChallengeHash             ChallengeType = "hash"               // 哈希计算
)

// ChallengeStatus 挑战状态
type ChallengeStatus string

const (
	ChallengeStatusPending   ChallengeStatus = "pending"
	ChallengeStatusCommit    ChallengeStatus = "commit"
	ChallengeStatusReveal    ChallengeStatus = "reveal"
	ChallengeStatusComplete  ChallengeStatus = "complete"
	ChallengeStatusExpired   ChallengeStatus = "expired"
)

// Challenge 挑战
type Challenge struct {
	ID             string            `json:"id"`
	Epoch          uint64            `json:"epoch"`
	Type           ChallengeType     `json:"type"`
	Tier           TaskTier          `json:"tier"`                      // 任务难度等级 (1/2/3)
	Prompt         string            `json:"prompt"`
	ExpectedAnswer string            `json:"expected_answer,omitempty"` // 精确匹配类有此字段
	Assignees      []string          `json:"assignees"`
	Status         ChallengeStatus   `json:"status"`
	CreatedHeight  int64             `json:"created_height"`
	Commits        map[string]string `json:"commits"`                  // addr → hash
	Reveals        map[string]string `json:"reveals"`                  // addr → answer
	Winner         string            `json:"winner,omitempty"`
	IsSpotCheck    bool              `json:"is_spot_check"`            // Spot Check 标记
	KnownAnswer    string            `json:"known_answer,omitempty"`   // Spot Check 预设正确答案
}

// ──────────────────────────────────────────────
// 任务难度分级
// ──────────────────────────────────────────────

// TaskTier 任务难度等级
type TaskTier int

const (
	TierBasic    TaskTier = 1 // 基础：数学、逻辑 → 1x 奖励
	TierMedium   TaskTier = 2 // 中级：情感分析、分类 → 2x 奖励
	TierAdvanced TaskTier = 3 // 高级：摘要、翻译、实体抽取 → 3x 奖励
)

// GetTaskTier 返回挑战类型对应的难度等级
func GetTaskTier(ctype ChallengeType) TaskTier {
	switch ctype {
	case ChallengeMath, ChallengeLogic, ChallengeHash, ChallengeTextTransform:
		return TierBasic
	case ChallengeSentiment, ChallengeClassification, ChallengeFormatConvert, ChallengeJSONExtract:
		return TierMedium
	case ChallengeTextSummary, ChallengeTranslation, ChallengeEntityExtraction:
		return TierAdvanced
	default:
		return TierBasic
	}
}

// GetTierMultiplier 返回难度等级的奖励倍率
func GetTierMultiplier(tier TaskTier) uint64 {
	return uint64(tier) // 1x, 2x, 3x
}

// MinReputationForTier 返回参与该难度所需的最低声誉分
func MinReputationForTier(tier TaskTier) int32 {
	switch tier {
	case TierAdvanced:
		return 800
	case TierMedium:
		return 600
	default:
		return 0
	}
}

// ChallengeResult 挑战结果
type ChallengeResult struct {
	ChallengeID     string   `json:"challenge_id"`
	CompletedMiners []string `json:"completed_miners"`
	FailedMiners    []string `json:"failed_miners"`
	ConsensusAnswer string   `json:"consensus_answer"`
}
