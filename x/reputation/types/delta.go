package types

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"regexp"

	sdk "github.com/cosmos/cosmos-sdk/types"
)

var sha256RefPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

// ReputationDelta 是窗口级声誉增量行。它来自 reward/settlement 已锚定的窗口输出，而不是单场结果。
type ReputationDelta struct {
	DeltaID               string  `json:"delta_id"`
	MinerAddress          string  `json:"miner_address"`
	SettlementBatchID     string  `json:"settlement_batch_id"`
	RewardWindowID        string  `json:"reward_window_id"`
	Lane                  string  `json:"lane"`
	PolicyVersion         string  `json:"policy_version"`
	PriorScoreRef         string  `json:"prior_score_ref"`
	Reason                string  `json:"reason"`
	Delta                 int32   `json:"delta"`
	DeltaCap              int32   `json:"delta_cap"`
	ScoreWeight           float64 `json:"score_weight"`
	GrossRewardAmount     float64 `json:"gross_reward_amount"`
	SubmissionCount       uint32  `json:"submission_count"`
	SourceResultRoot      string  `json:"source_result_root"`
	CorrectionLineageRoot string  `json:"correction_lineage_root"`
}

func (d ReputationDelta) Validate() error {
	if d.DeltaID == "" || d.MinerAddress == "" || d.SettlementBatchID == "" || d.RewardWindowID == "" {
		return ErrInvalidReputationDelta
	}
	if d.Lane == "" || d.PolicyVersion == "" || d.Reason == "" {
		return ErrInvalidReputationDelta
	}
	if d.Delta == 0 || d.DeltaCap <= 0 {
		return ErrInvalidReputationDelta
	}
	if d.Delta > d.DeltaCap || d.Delta < -d.DeltaCap {
		return ErrInvalidReputationDelta.Wrapf("delta %d exceeds cap %d", d.Delta, d.DeltaCap)
	}
	if d.SubmissionCount == 0 {
		return ErrInvalidReputationDelta
	}
	if d.ScoreWeight < 0 {
		return ErrInvalidReputationDelta
	}
	if !sha256RefPattern.MatchString(d.SourceResultRoot) || !sha256RefPattern.MatchString(d.CorrectionLineageRoot) {
		return ErrInvalidReputationDelta
	}
	return nil
}

func (d ReputationDelta) PayloadHash() (string, error) {
	bz, err := json.Marshal(d)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(bz)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

// AppliedReputationDelta 是 append-only 应用回执。
type AppliedReputationDelta struct {
	Delta           ReputationDelta `json:"delta"`
	Controller      string          `json:"controller"`
	PayloadHash     string          `json:"payload_hash"`
	OldScore        int32           `json:"old_score"`
	NewScore        int32           `json:"new_score"`
	AppliedAtHeight int64           `json:"applied_at_height"`
	AppliedAtUnix   int64           `json:"applied_at_unix"`
}

func (r AppliedReputationDelta) Validate() error {
	if err := r.Delta.Validate(); err != nil {
		return err
	}
	if _, err := sdk.AccAddressFromBech32(r.Controller); err != nil {
		return err
	}
	expectedHash, err := r.Delta.PayloadHash()
	if err != nil {
		return err
	}
	if r.PayloadHash != expectedHash || !sha256RefPattern.MatchString(r.PayloadHash) {
		return ErrInvalidReputationDelta
	}
	if r.NewScore < MinScore || r.NewScore > MaxScore || r.OldScore < MinScore || r.OldScore > MaxScore {
		return ErrInvalidReputationDelta
	}
	return nil
}
