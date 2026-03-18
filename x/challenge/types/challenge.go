package types

// ChallengeType 挑战类型
type ChallengeType string

const (
	ChallengeTextSummary      ChallengeType = "text_summary"
	ChallengeSentiment        ChallengeType = "sentiment"
	ChallengeEntityExtraction ChallengeType = "entity_extraction"
	ChallengeFormatConvert    ChallengeType = "format_convert"
	ChallengeMath             ChallengeType = "math"
	ChallengeLogic            ChallengeType = "logic"
	ChallengeTextTransform    ChallengeType = "text_transform"  // 文本转换（大写等）
	ChallengeJSONExtract      ChallengeType = "json_extract"    // JSON 提取
	ChallengeHash             ChallengeType = "hash"            // 哈希计算
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
	ID            string          `json:"id"`
	Epoch         uint64          `json:"epoch"`
	Type          ChallengeType   `json:"type"`
	Prompt        string          `json:"prompt"`
	ExpectedAnswer string         `json:"expected_answer,omitempty"` // 精确匹配类有此字段
	Assignees     []string        `json:"assignees"`
	Status        ChallengeStatus `json:"status"`
	CreatedHeight int64           `json:"created_height"`
	Commits       map[string]string `json:"commits"`  // addr → hash
	Reveals       map[string]string `json:"reveals"`   // addr → answer
	Winner        string          `json:"winner,omitempty"`
}

// ChallengeResult 挑战结果
type ChallengeResult struct {
	ChallengeID     string   `json:"challenge_id"`
	CompletedMiners []string `json:"completed_miners"`
	FailedMiners    []string `json:"failed_miners"`
	ConsensusAnswer string   `json:"consensus_answer"`
}
