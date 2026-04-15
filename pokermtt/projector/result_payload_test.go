package projector

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/clawchain/clawchain/pokermtt/ranking"
)

func TestBuildFinalRankingApplyPayloadUsesCanonicalRows(t *testing.T) {
	rank := 1
	score := 90000.0
	finalization := ranking.Finalization{
		TournamentID:        "mtt-phase1-1",
		SourceMTTID:         "donor-mtt-1",
		SnapshotID:          "poker_mtt_standing_snapshot:mtt-phase1-1:abc",
		SnapshotHash:        "sha256:snapshot",
		Root:                "sha256:root",
		PolicyBundleVersion: "poker_mtt_policy_v1",
		Rows: []ranking.FinalRankingRow{
			{
				ID:                   "poker_mtt_final_ranking:mtt-phase1-1:8:1",
				TournamentID:         "mtt-phase1-1",
				SourceMTTID:          "donor-mtt-1",
				SourceUserID:         "8",
				MinerAddress:         "claw18",
				EconomicUnitID:       "eu:8",
				MemberID:             "8:1",
				EntryNumber:          1,
				Rank:                 &rank,
				RankState:            ranking.RankStateRanked,
				Chip:                 90000,
				ChipDelta:            87000,
				FieldSizePolicy:      "finished_snapshot_count",
				StandingSnapshotID:   "poker_mtt_standing_snapshot:mtt-phase1-1:abc",
				StandingSnapshotHash: "sha256:snapshot",
				EvidenceRoot:         "sha256:evidence",
				EvidenceState:        "complete",
				PolicyBundleVersion:  "poker_mtt_policy_v1",
				SnapshotFound:        true,
				Status:               ranking.StandingStatusAlive,
				ZSetScore:            &score,
			},
		},
	}

	payload, err := BuildFinalRankingApplyPayload(finalization, ApplyOptions{
		RatedOrPractice: "rated",
		HumanOnly:       true,
		FieldSize:       30,
		LockedAt:        time.Date(2026, 4, 10, 12, 0, 0, 0, time.UTC),
	})

	if err != nil {
		t.Fatalf("BuildFinalRankingApplyPayload() error = %v", err)
	}
	if payload.SchemaVersion != FinalRankingApplySchemaVersion {
		t.Fatalf("unexpected schema version: %s", payload.SchemaVersion)
	}
	if payload.TournamentID != "mtt-phase1-1" {
		t.Fatalf("unexpected tournament id: %s", payload.TournamentID)
	}
	if payload.Rows[0].RoomID != "" {
		t.Fatalf("room id should not cross into projection payload")
	}
	if payload.Rows[0].SessionID != "" {
		t.Fatalf("session id should not cross into projection payload")
	}
	if payload.Rows[0].StandingSnapshotHash != "sha256:snapshot" {
		t.Fatalf("standing snapshot hash missing")
	}
	if payload.Rows[0].LockedAt != "2026-04-10T12:00:00Z" {
		t.Fatalf("locked_at not normalized: %s", payload.Rows[0].LockedAt)
	}
	if _, err := json.Marshal(payload); err != nil {
		t.Fatalf("payload must be json serializable: %v", err)
	}
}

func TestBuildFinalRankingApplyPayloadRejectsUnrootedFinalization(t *testing.T) {
	_, err := BuildFinalRankingApplyPayload(ranking.Finalization{TournamentID: "mtt"}, ApplyOptions{
		RatedOrPractice: "rated",
		HumanOnly:       true,
		FieldSize:       30,
	})

	if err == nil {
		t.Fatalf("expected error for missing finalization root")
	}
}
