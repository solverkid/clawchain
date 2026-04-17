package projector

import (
	"errors"
	"time"

	"github.com/clawchain/clawchain/pokermtt/ranking"
)

const FinalRankingApplySchemaVersion = "poker_mtt.final_ranking_apply.v1"

type ApplyOptions struct {
	RatedOrPractice string
	HumanOnly       bool
	FieldSize       int
	LockedAt        time.Time
}

type FinalRankingApplyPayload struct {
	SchemaVersion        string               `json:"schema_version"`
	TournamentID         string               `json:"tournament_id"`
	SourceMTTID          string               `json:"source_mtt_id"`
	RatedOrPractice      string               `json:"rated_or_practice"`
	HumanOnly            bool                 `json:"human_only"`
	FieldSize            int                  `json:"field_size"`
	PolicyBundleVersion  string               `json:"policy_bundle_version"`
	StandingSnapshotID   string               `json:"standing_snapshot_id"`
	StandingSnapshotHash string               `json:"standing_snapshot_hash"`
	FinalRankingRoot     string               `json:"final_ranking_root"`
	LockedAt             string               `json:"locked_at,omitempty"`
	Rows                 []FinalRankingRowDTO `json:"rows"`
}

type FinalRankingRowDTO struct {
	ID                   string  `json:"id"`
	TournamentID         string  `json:"tournament_id"`
	SourceMTTID          string  `json:"source_mtt_id"`
	SourceUserID         string  `json:"source_user_id"`
	MinerAddress         string  `json:"miner_address"`
	EconomicUnitID       string  `json:"economic_unit_id"`
	MemberID             string  `json:"member_id"`
	EntryNumber          int     `json:"entry_number"`
	ReentryCount         int     `json:"reentry_count"`
	Rank                 *int    `json:"rank"`
	RankState            string  `json:"rank_state"`
	Chip                 float64 `json:"chip"`
	ChipDelta            float64 `json:"chip_delta"`
	DiedTime             string  `json:"died_time"`
	WaitingOrNoShow      bool    `json:"waiting_or_no_show"`
	Bounty               float64 `json:"bounty"`
	DefeatNum            int     `json:"defeat_num"`
	FieldSizePolicy      string  `json:"field_size_policy"`
	StandingSnapshotID   string  `json:"standing_snapshot_id"`
	StandingSnapshotHash string  `json:"standing_snapshot_hash"`
	EvidenceRoot         string  `json:"evidence_root"`
	EvidenceState        string  `json:"evidence_state"`
	PolicyBundleVersion  string  `json:"policy_bundle_version"`
	LockedAt             string  `json:"locked_at,omitempty"`
	AnchorableAt         string  `json:"anchorable_at,omitempty"`
	RoomID               string  `json:"-"`
	SessionID            string  `json:"-"`
}

func BuildFinalRankingApplyPayload(finalization ranking.Finalization, opts ApplyOptions) (FinalRankingApplyPayload, error) {
	if finalization.TournamentID == "" {
		return FinalRankingApplyPayload{}, errors.New("missing tournament id")
	}
	if finalization.Root == "" {
		return FinalRankingApplyPayload{}, errors.New("missing final ranking root")
	}
	if opts.RatedOrPractice == "" {
		return FinalRankingApplyPayload{}, errors.New("missing rated/practice mode")
	}
	if opts.FieldSize <= 0 {
		return FinalRankingApplyPayload{}, errors.New("field size must be positive")
	}

	payload := FinalRankingApplyPayload{
		SchemaVersion:        FinalRankingApplySchemaVersion,
		TournamentID:         finalization.TournamentID,
		SourceMTTID:          finalization.SourceMTTID,
		RatedOrPractice:      opts.RatedOrPractice,
		HumanOnly:            opts.HumanOnly,
		FieldSize:            opts.FieldSize,
		PolicyBundleVersion:  finalization.PolicyBundleVersion,
		StandingSnapshotID:   finalization.SnapshotID,
		StandingSnapshotHash: finalization.SnapshotHash,
		FinalRankingRoot:     finalization.Root,
		Rows:                 make([]FinalRankingRowDTO, 0, len(finalization.Rows)),
	}
	if !opts.LockedAt.IsZero() {
		payload.LockedAt = opts.LockedAt.UTC().Format(time.RFC3339)
	}
	for _, row := range finalization.Rows {
		rowDTO := FinalRankingRowDTO{
			ID:                   row.ID,
			TournamentID:         row.TournamentID,
			SourceMTTID:          row.SourceMTTID,
			SourceUserID:         row.SourceUserID,
			MinerAddress:         row.MinerAddress,
			EconomicUnitID:       row.EconomicUnitID,
			MemberID:             row.MemberID,
			EntryNumber:          row.EntryNumber,
			ReentryCount:         row.ReentryCount,
			Rank:                 row.Rank,
			RankState:            string(row.RankState),
			Chip:                 row.Chip,
			ChipDelta:            row.ChipDelta,
			DiedTime:             row.DiedTime,
			WaitingOrNoShow:      row.WaitingOrNoShow,
			Bounty:               row.Bounty,
			DefeatNum:            row.DefeatNum,
			FieldSizePolicy:      row.FieldSizePolicy,
			StandingSnapshotID:   row.StandingSnapshotID,
			StandingSnapshotHash: row.StandingSnapshotHash,
			EvidenceRoot:         row.EvidenceRoot,
			EvidenceState:        row.EvidenceState,
			PolicyBundleVersion:  row.PolicyBundleVersion,
			LockedAt:             payload.LockedAt,
			AnchorableAt:         payload.LockedAt,
		}
		payload.Rows = append(payload.Rows, rowDTO)
	}
	return payload, nil
}
