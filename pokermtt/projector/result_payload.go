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
	ProjectionID         string               `json:"projection_id"`
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
	ID                   string   `json:"id"`
	TournamentID         string   `json:"tournament_id"`
	SourceMTTID          string   `json:"source_mtt_id"`
	SourceUserID         string   `json:"source_user_id"`
	MinerAddress         string   `json:"miner_address"`
	EconomicUnitID       string   `json:"economic_unit_id"`
	MemberID             string   `json:"member_id"`
	EntryNumber          int      `json:"entry_number"`
	ReentryCount         int      `json:"reentry_count"`
	Rank                 *int     `json:"rank"`
	DisplayRank          *int     `json:"display_rank,omitempty"`
	RankState            string   `json:"rank_state"`
	RankBasis            string   `json:"rank_basis,omitempty"`
	RankTiebreaker       string   `json:"rank_tiebreaker,omitempty"`
	Chip                 float64  `json:"chip"`
	ChipDelta            float64  `json:"chip_delta"`
	DiedTime             string   `json:"died_time"`
	WaitingOrNoShow      bool     `json:"waiting_or_no_show"`
	Bounty               float64  `json:"bounty"`
	DefeatNum            int      `json:"defeat_num"`
	FieldSizePolicy      string   `json:"field_size_policy"`
	StandingSnapshotID   string   `json:"standing_snapshot_id"`
	StandingSnapshotHash string   `json:"standing_snapshot_hash"`
	EvidenceRoot         string   `json:"evidence_root"`
	EvidenceState        string   `json:"evidence_state"`
	PolicyBundleVersion  string   `json:"policy_bundle_version"`
	SnapshotFound        bool     `json:"snapshot_found"`
	Status               string   `json:"status"`
	PlayerName           string   `json:"player_name"`
	StartChip            float64  `json:"start_chip"`
	StandUpStatus        string   `json:"stand_up_status"`
	SourceRank           string   `json:"source_rank"`
	SourceRankNumeric    bool     `json:"source_rank_numeric"`
	ZSetScore            *float64 `json:"zset_score"`
	LockedAt             string   `json:"locked_at,omitempty"`
	AnchorableAt         string   `json:"anchorable_at,omitempty"`
	CreatedAt            string   `json:"created_at,omitempty"`
	UpdatedAt            string   `json:"updated_at,omitempty"`
	RoomID               string   `json:"-"`
	SessionID            string   `json:"-"`
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
	if opts.LockedAt.IsZero() {
		return FinalRankingApplyPayload{}, errors.New("missing locked_at")
	}

	payload := FinalRankingApplyPayload{
		SchemaVersion:        FinalRankingApplySchemaVersion,
		ProjectionID:         finalRankingProjectionID(finalization.TournamentID, finalization.PolicyBundleVersion, finalization.Root),
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
	payload.LockedAt = opts.LockedAt.UTC().Format(time.RFC3339)
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
			DisplayRank:          row.DisplayRank,
			RankState:            string(row.RankState),
			RankBasis:            row.RankBasis,
			RankTiebreaker:       row.RankTiebreaker,
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
			SnapshotFound:        row.SnapshotFound,
			Status:               string(row.Status),
			PlayerName:           row.PlayerName,
			StartChip:            row.StartChip,
			StandUpStatus:        row.StandUpStatus,
			SourceRank:           row.SourceRank,
			SourceRankNumeric:    row.SourceRankNumeric,
			ZSetScore:            row.ZSetScore,
			LockedAt:             payload.LockedAt,
			AnchorableAt:         payload.LockedAt,
			CreatedAt:            payload.LockedAt,
			UpdatedAt:            payload.LockedAt,
		}
		payload.Rows = append(payload.Rows, rowDTO)
	}
	return payload, nil
}

func finalRankingProjectionID(tournamentID, policyBundleVersion, root string) string {
	return "poker_mtt_projection:" + tournamentID + ":" + policyBundleVersion + ":" + root
}
