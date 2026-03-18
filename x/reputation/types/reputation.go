package types

// ReputationScore 声誉分
type ReputationScore struct {
	MinerAddress    string `json:"miner_address"`
	Score           int32  `json:"score"`             // 0-1000
	Level           string `json:"level"`             // elite/normal/low/suspended
	UpdatedAt       int64  `json:"updated_at"`        // 最后更新区块高度
	ConsecutiveDays uint64 `json:"consecutive_days"`  // 连续在线天数
	LastActiveDay   int64  `json:"last_active_day"`   // 最后活跃日（Unix 天数 = blockTime / 86400）
}

// 声誉等级阈值
const (
	EliteThreshold     int32 = 800
	NormalThreshold    int32 = 600
	LowThreshold       int32 = 300
	SuspendedThreshold int32 = 100
	InitialScore       int32 = 500
	MaxScore           int32 = 1000
	MinScore           int32 = 0
)

// 声誉变化值
const (
	RewardChallengeComplete int32 = 5
	RewardOnline24h         int32 = 10
	PenaltyChallengeFail    int32 = -20
	PenaltyTimeout          int32 = -10
	PenaltyCheat            int32 = -500
)

// GetStreakBonus 根据连续在线天数返回奖励倍率（百分比：110=1.1x）
func GetStreakBonus(consecutiveDays uint64) uint64 {
	switch {
	case consecutiveDays >= 90:
		return 150 // +50%
	case consecutiveDays >= 30:
		return 125 // +25%
	case consecutiveDays >= 7:
		return 110 // +10%
	default:
		return 100 // no bonus
	}
}

// GetLevel 根据分数返回等级
func GetLevel(score int32) string {
	switch {
	case score >= EliteThreshold:
		return "elite"
	case score >= NormalThreshold:
		return "normal"
	case score >= SuspendedThreshold:
		return "low"
	default:
		return "suspended"
	}
}
