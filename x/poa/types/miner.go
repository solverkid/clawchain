package types

import "time"

// MinerStatus 矿工状态
type MinerStatus int32

const (
	MinerStatusInactive  MinerStatus = 0 // 未激活
	MinerStatusActive    MinerStatus = 1 // 活跃
	MinerStatusUnstaking MinerStatus = 2 // 解质押中
	MinerStatusSuspended MinerStatus = 3 // 被暂停
)

// Miner 矿工信息
type Miner struct {
	Address             string      `json:"address"`
	StakeAmount         uint64      `json:"stake_amount"`
	Status              MinerStatus `json:"status"`
	RegisteredAt        time.Time   `json:"registered_at"`
	ReputationScore     int32       `json:"reputation_score"`
	TotalRewards        uint64      `json:"total_rewards"`
	ChallengesCompleted uint64      `json:"challenges_completed"`
	ChallengesFailed    uint64      `json:"challenges_failed"`
	LastActiveEpoch     uint64      `json:"last_active_epoch"`
	RegistrationIndex   uint64      `json:"registration_index"`   // 全局注册序号（用于早鸟倍率）
	ConsecutiveDays     uint64      `json:"consecutive_days"`     // 连续在线天数
	LastCheckinEpoch    uint64      `json:"last_checkin_epoch"`   // 最后签到 epoch
}

// ──────────────────────────────────────────────
// 早鸟奖励倍率
// ──────────────────────────────────────────────

// GetEarlyBirdMultiplier 根据注册序号返回早鸟倍率（百分比形式，300=3x）
func GetEarlyBirdMultiplier(registrationIndex uint64) uint64 {
	switch {
	case registrationIndex <= 1000:
		return 300 // 3x
	case registrationIndex <= 5000:
		return 200 // 2x
	case registrationIndex <= 10000:
		return 150 // 1.5x
	default:
		return 100 // 1x
	}
}

// ──────────────────────────────────────────────
// 连续在线签到奖励
// ──────────────────────────────────────────────

// GetStreakBonus 根据连续天数返回签到奖励百分比（110=+10%）
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

// UnstakeEntry 解质押队列条目
type UnstakeEntry struct {
	MinerAddress   string    `json:"miner_address"`
	Amount         uint64    `json:"amount"`
	CompletionTime time.Time `json:"completion_time"`
}

// EpochInfo Epoch 信息
type EpochInfo struct {
	EpochNumber         uint64 `json:"epoch_number"`
	StartHeight         int64  `json:"start_height"`
	EndHeight           int64  `json:"end_height"`
	RewardPerEpoch      uint64 `json:"reward_per_epoch"`
	ActiveMiners        uint32 `json:"active_miners"`
	ChallengesIssued    uint32 `json:"challenges_issued"`
	ChallengesCompleted uint32 `json:"challenges_completed"`
}
