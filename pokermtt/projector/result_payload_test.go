package projector

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/clawchain/clawchain/pokermtt/ranking"
	"github.com/stretchr/testify/require"
)

func TestBuildFinalRankingApplyPayloadUsesCanonicalRows(t *testing.T) {
	rank := 1
	displayRank := 1
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
				DisplayRank:          &displayRank,
				RankState:            ranking.RankStateRanked,
				RankBasis:            "alive_zset_score",
				RankTiebreaker:       "zset_score_desc_member_id",
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
	if payload.Rows[0].AnchorableAt != "2026-04-10T12:00:00Z" {
		t.Fatalf("anchorable_at not normalized: %s", payload.Rows[0].AnchorableAt)
	}
	if _, err := json.Marshal(payload); err != nil {
		t.Fatalf("payload must be json serializable: %v", err)
	}
}

func TestBuildFinalRankingApplyPayloadMatchesCrossLanguageFixture(t *testing.T) {
	finalization := phase3ContractFinalization()
	payload, err := BuildFinalRankingApplyPayload(finalization, ApplyOptions{
		RatedOrPractice: "rated",
		HumanOnly:       true,
		FieldSize:       30,
		LockedAt:        time.Date(2026, 4, 10, 12, 0, 0, 0, time.UTC),
	})
	require.NoError(t, err)

	actual, err := json.Marshal(payload)
	require.NoError(t, err)
	expected, err := os.ReadFile("../../tests/fixtures/poker_mtt/final_ranking_projection_from_go.json")
	require.NoError(t, err)
	require.JSONEq(t, string(expected), string(actual))
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

func TestBuildFinalRankingApplyPayloadRejectsMissingLockedAt(t *testing.T) {
	_, err := BuildFinalRankingApplyPayload(phase3ContractFinalization(), ApplyOptions{
		RatedOrPractice: "rated",
		HumanOnly:       true,
		FieldSize:       30,
	})

	require.ErrorContains(t, err, "missing locked_at")
}

func phase3ContractFinalization() ranking.Finalization {
	firstRank := 1
	secondRank := 2
	firstDisplayRank := 1
	secondDisplayRank := 2
	firstScore := 90000.0
	return ranking.Finalization{
		TournamentID:        "mtt-phase3-contract",
		SourceMTTID:         "donor-mtt-phase3-contract",
		SnapshotID:          "poker_mtt_standing_snapshot:mtt-phase3-contract:abc",
		SnapshotHash:        "sha256:snapshot",
		Root:                "sha256:final-root",
		PolicyBundleVersion: "poker_mtt_policy_v1",
		Rows: []ranking.FinalRankingRow{
			{
				ID:                   "poker_mtt_final_ranking:mtt-phase3-contract:8:1",
				TournamentID:         "mtt-phase3-contract",
				SourceMTTID:          "donor-mtt-phase3-contract",
				SourceUserID:         "8",
				MinerAddress:         "claw18phase3",
				EconomicUnitID:       "eu:8",
				MemberID:             "8:1",
				EntryNumber:          1,
				ReentryCount:         1,
				Rank:                 &firstRank,
				DisplayRank:          &firstDisplayRank,
				RankState:            ranking.RankStateRanked,
				RankBasis:            "alive_zset_score",
				RankTiebreaker:       "zset_score_desc_member_id",
				Chip:                 90000,
				ChipDelta:            87000,
				Bounty:               0,
				DefeatNum:            4,
				FieldSizePolicy:      "exclude_waiting_no_show_from_reward_field_size",
				StandingSnapshotID:   "poker_mtt_standing_snapshot:mtt-phase3-contract:abc",
				StandingSnapshotHash: "sha256:snapshot",
				EvidenceRoot:         "sha256:evidence:8",
				EvidenceState:        "complete",
				PolicyBundleVersion:  "poker_mtt_policy_v1",
				SnapshotFound:        true,
				Status:               ranking.StandingStatusAlive,
				PlayerName:           "miner 8",
				StartChip:            3000,
				SourceRank:           "1",
				SourceRankNumeric:    true,
				ZSetScore:            &firstScore,
			},
			{
				ID:                   "poker_mtt_final_ranking:mtt-phase3-contract:19:1",
				TournamentID:         "mtt-phase3-contract",
				SourceMTTID:          "donor-mtt-phase3-contract",
				SourceUserID:         "19",
				MinerAddress:         "claw119phase3",
				EconomicUnitID:       "eu:19",
				MemberID:             "19:1",
				EntryNumber:          1,
				ReentryCount:         1,
				Rank:                 &secondRank,
				DisplayRank:          &secondDisplayRank,
				RankState:            ranking.RankStateRanked,
				RankBasis:            "donor_died_rank",
				RankTiebreaker:       "source_rank_display",
				Chip:                 0,
				ChipDelta:            -3000,
				DiedTime:             "2026-04-10T11:59:30Z",
				Bounty:               0,
				DefeatNum:            1,
				FieldSizePolicy:      "exclude_waiting_no_show_from_reward_field_size",
				StandingSnapshotID:   "poker_mtt_standing_snapshot:mtt-phase3-contract:abc",
				StandingSnapshotHash: "sha256:snapshot",
				EvidenceRoot:         "sha256:evidence:19",
				EvidenceState:        "complete",
				PolicyBundleVersion:  "poker_mtt_policy_v1",
				SnapshotFound:        true,
				Status:               ranking.StandingStatusDied,
				PlayerName:           "miner 19",
				StartChip:            3000,
				SourceRank:           "2",
				SourceRankNumeric:    true,
			},
			{
				ID:                   "poker_mtt_final_ranking:mtt-phase3-contract:27:1",
				TournamentID:         "mtt-phase3-contract",
				SourceMTTID:          "donor-mtt-phase3-contract",
				SourceUserID:         "27",
				MinerAddress:         "claw127phase3",
				EconomicUnitID:       "eu:27",
				MemberID:             "27:1",
				EntryNumber:          1,
				ReentryCount:         1,
				Rank:                 nil,
				RankState:            ranking.RankStateWaitingNoShow,
				Chip:                 3000,
				ChipDelta:            0,
				WaitingOrNoShow:      true,
				Bounty:               0,
				DefeatNum:            0,
				FieldSizePolicy:      "exclude_waiting_no_show_from_reward_field_size",
				StandingSnapshotID:   "poker_mtt_standing_snapshot:mtt-phase3-contract:abc",
				StandingSnapshotHash: "sha256:snapshot",
				EvidenceRoot:         "sha256:evidence:27",
				EvidenceState:        "accepted_degraded",
				PolicyBundleVersion:  "poker_mtt_policy_v1",
				SnapshotFound:        false,
				Status:               ranking.StandingStatusPending,
				PlayerName:           "miner 27",
				StartChip:            3000,
				StandUpStatus:        "WAITING",
				SourceRank:           "",
				SourceRankNumeric:    false,
			},
		},
	}
}

func TestFinalRankingApplyClientPostsPayload(t *testing.T) {
	payload := FinalRankingApplyPayload{
		SchemaVersion:       FinalRankingApplySchemaVersion,
		TournamentID:        "mtt-client-1",
		RatedOrPractice:     "rated",
		HumanOnly:           true,
		FieldSize:           30,
		PolicyBundleVersion: "poker_mtt_v1",
		Rows:                []FinalRankingRowDTO{{ID: "row-1", TournamentID: "mtt-client-1", MemberID: "7:1"}},
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/admin/poker-mtt/final-rankings/project", r.URL.Path)
		require.Equal(t, http.MethodPost, r.Method)
		var decoded FinalRankingApplyPayload
		require.NoError(t, json.NewDecoder(r.Body).Decode(&decoded))
		require.Equal(t, payload.TournamentID, decoded.TournamentID)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"tournament_id":"mtt-client-1"}`))
	}))
	defer server.Close()

	client := NewFinalRankingApplyClient(server.URL, server.Client())
	resp, err := client.Apply(context.Background(), payload)

	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	require.Contains(t, string(resp.Body), "mtt-client-1")
}

func TestFinalRankingApplyClientAddsAuthAndRetriesRetryableStatus(t *testing.T) {
	payload := FinalRankingApplyPayload{
		SchemaVersion:       FinalRankingApplySchemaVersion,
		TournamentID:        "mtt-client-retry",
		RatedOrPractice:     "rated",
		HumanOnly:           true,
		FieldSize:           30,
		PolicyBundleVersion: "poker_mtt_v1",
		Rows:                []FinalRankingRowDTO{{ID: "row-1", TournamentID: "mtt-client-retry", MemberID: "7:1"}},
	}
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		require.Equal(t, "Bearer internal-secret", r.Header.Get("Authorization"))
		if attempts == 1 {
			http.Error(w, "temporarily unavailable", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"tournament_id":"mtt-client-retry"}`))
	}))
	defer server.Close()

	client := NewFinalRankingApplyClientWithOptions(server.URL, server.Client(), FinalRankingApplyClientOptions{
		BearerToken:  "internal-secret",
		MaxAttempts:  2,
		RetryBackoff: 0,
	})
	resp, err := client.Apply(context.Background(), payload)

	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	require.Equal(t, 2, attempts)
}

func TestFinalRankingApplyClientClassifiesRetryableAndPermanentErrors(t *testing.T) {
	for _, tc := range []struct {
		name      string
		status    int
		retryable bool
	}{
		{name: "service unavailable", status: http.StatusServiceUnavailable, retryable: true},
		{name: "unauthorized", status: http.StatusUnauthorized, retryable: false},
		{name: "forbidden", status: http.StatusForbidden, retryable: false},
		{name: "bad request", status: http.StatusBadRequest, retryable: false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				http.Error(w, tc.name, tc.status)
			}))
			defer server.Close()

			client := NewFinalRankingApplyClient(server.URL, server.Client())
			_, err := client.Apply(context.Background(), FinalRankingApplyPayload{TournamentID: "mtt-error"})

			var applyErr *ApplyError
			require.ErrorAs(t, err, &applyErr)
			require.Equal(t, tc.status, applyErr.StatusCode)
			require.Equal(t, tc.retryable, applyErr.Retryable)
		})
	}
}
