package types

type SettlementAnchor struct {
	SettlementBatchID   string `json:"settlement_batch_id"`
	AnchorJobID         string `json:"anchor_job_id"`
	Submitter           string `json:"submitter"`
	Lane                string `json:"lane"`
	SchemaVersion       string `json:"schema_version"`
	PolicyBundleVersion string `json:"policy_bundle_version"`
	CanonicalRoot       string `json:"canonical_root"`
	AnchorPayloadHash   string `json:"anchor_payload_hash"`
	RewardWindowIdsRoot string `json:"reward_window_ids_root"`
	TaskRunIdsRoot      string `json:"task_run_ids_root"`
	MinerRewardRowsRoot string `json:"miner_reward_rows_root"`
	WindowEndAt         string `json:"window_end_at"`
	TotalRewardAmount   uint64 `json:"total_reward_amount"`
	AnchoredAtHeight    int64  `json:"anchored_at_height"`
	AnchoredAtTime      int64  `json:"anchored_at_time"`
}

func NewSettlementAnchor(msg *MsgAnchorSettlementBatch, blockHeight int64, blockTimeUnix int64) SettlementAnchor {
	return SettlementAnchor{
		SettlementBatchID:   msg.SettlementBatchId,
		AnchorJobID:         msg.AnchorJobId,
		Submitter:           msg.Submitter,
		Lane:                msg.Lane,
		SchemaVersion:       msg.SchemaVersion,
		PolicyBundleVersion: msg.PolicyBundleVersion,
		CanonicalRoot:       msg.CanonicalRoot,
		AnchorPayloadHash:   msg.AnchorPayloadHash,
		RewardWindowIdsRoot: msg.RewardWindowIdsRoot,
		TaskRunIdsRoot:      msg.TaskRunIdsRoot,
		MinerRewardRowsRoot: msg.MinerRewardRowsRoot,
		WindowEndAt:         msg.WindowEndAt,
		TotalRewardAmount:   msg.TotalRewardAmount,
		AnchoredAtHeight:    blockHeight,
		AnchoredAtTime:      blockTimeUnix,
	}
}
