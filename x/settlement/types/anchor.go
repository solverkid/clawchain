package types

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
		RewardWindowIDsRoot: msg.RewardWindowIdsRoot,
		TaskRunIDsRoot:      msg.TaskRunIdsRoot,
		MinerRewardRowsRoot: msg.MinerRewardRowsRoot,
		WindowEndAt:         msg.WindowEndAt,
		TotalRewardAmount:   msg.TotalRewardAmount,
		AnchoredAtHeight:    blockHeight,
		AnchoredAtTime:      blockTimeUnix,
	}
}
