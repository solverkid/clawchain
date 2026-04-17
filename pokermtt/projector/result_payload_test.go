package projector

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/clawchain/clawchain/pokermtt/ranking"
	"github.com/stretchr/testify/require"
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
	if payload.Rows[0].AnchorableAt != "2026-04-10T12:00:00Z" {
		t.Fatalf("anchorable_at not normalized: %s", payload.Rows[0].AnchorableAt)
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

func TestFinalRankingApplyClientClassifiesRetryableAndPermanentErrors(t *testing.T) {
	for _, tc := range []struct {
		name      string
		status    int
		retryable bool
	}{
		{name: "service unavailable", status: http.StatusServiceUnavailable, retryable: true},
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
