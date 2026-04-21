package types

// 事件类型
const (
	EventTypeScoreUpdate            = "score_update"
	EventTypeSuspend                = "miner_suspended"
	EventTypeReputationDeltaApplied = "reputation_delta_applied"
	AttributeKeyMiner               = "miner"
	AttributeKeyOldScore            = "old_score"
	AttributeKeyNewScore            = "new_score"
	AttributeKeyReason              = "reason"
	AttributeKeyDeltaID             = "delta_id"
	AttributeKeyController          = "controller"
	AttributeKeySettlementBatchID   = "settlement_batch_id"
	AttributeKeyRewardWindowID      = "reward_window_id"
	AttributeKeyPayloadHash         = "payload_hash"
)
