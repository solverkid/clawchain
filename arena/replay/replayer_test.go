package replay

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/store/postgres"
)

func TestReplayParityMismatchMarksIntegrityFailure(t *testing.T) {
	rep := newReplayerForTest()

	result := rep.ReplayCorrupted("tour_1")
	require.NoError(t, result.Err)
	require.False(t, result.ParityOK)
	require.Equal(t, "integrity_failure", result.FinalDisposition)
}

func newReplayerForTest() *Replayer {
	return NewReplayer(map[string]string{
		"tour_1": "expected-final-hash",
	}, map[string]string{
		"tour_1": "corrupted-final-hash",
	})
}

func TestRepositoryReplayerComputesStableFinalHash(t *testing.T) {
	db := openReplayTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	now := time.Date(2026, time.April, 10, 16, 0, 0, 0, time.UTC)
	require.NoError(t, repo.UpsertWave(context.Background(), model.Wave{
		ID:                  "wave_hash",
		Mode:                model.RatedMode,
		State:               model.WaveStateSeatsPublished,
		RegistrationOpenAt:  now.Add(-time.Hour),
		RegistrationCloseAt: now.Add(-30 * time.Minute),
		ScheduledStartAt:    now,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "v1",
			StateHash:           "wave-state",
			PayloadHash:         "wave-payload",
		},
		CreatedAt: now,
		UpdatedAt: now,
	}))
	require.NoError(t, repo.UpsertTournament(context.Background(), model.Tournament{
		ID:     "tour_hash",
		WaveID: "wave_hash",
		Mode:   model.RatedMode,
		State:  model.TournamentStateReady,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "v1",
			StateHash:           "tour-state",
			PayloadHash:         "tour-payload",
		},
		CreatedAt: now,
		UpdatedAt: now,
	}))
	require.NoError(t, repo.UpsertTable(context.Background(), model.Table{
		ID:           "tbl:tour_hash:01",
		TournamentID: "tour_hash",
		State:        model.TableStateOpen,
		TableNo:      1,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "v1",
			StateHash:           "table-state",
			PayloadHash:         "table-payload",
		},
		CreatedAt: now,
		UpdatedAt: now,
	}))
	require.NoError(t, repo.SaveTournamentSnapshot(context.Background(), model.TournamentSnapshot{
		ID:           "snap:tour_hash:seating_published",
		TournamentID: "tour_hash",
		StreamKey:    "tournament:tour_hash",
		StreamSeq:    1,
		StateSeq:     1,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "v1",
			StateHash:           "expected-parity-hash",
			PayloadHash:         "expected-parity-hash",
		},
		Payload:   []byte(`{"stage":"seating_published"}`),
		CreatedAt: now,
	}))
	require.NoError(t, repo.SaveTableSnapshot(context.Background(), model.TableSnapshot{
		ID:           "tblsnap:tour_hash:01",
		TournamentID: "tour_hash",
		TableID:      "tbl:tour_hash:01",
		StreamKey:    "table:tbl:tour_hash:01",
		StreamSeq:    1,
		StateSeq:     1,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "v1",
			StateHash:           "expected-parity-hash",
			PayloadHash:         "expected-parity-hash",
		},
		Payload:   []byte(`{"current_phase":"signal"}`),
		CreatedAt: now,
	}))

	replayer := NewRepositoryReplayer(repo)
	firstHash, err := replayer.ComputeFinalHash(context.Background(), "tour_hash")
	require.NoError(t, err)
	secondHash, err := replayer.ComputeFinalHash(context.Background(), "tour_hash")
	require.NoError(t, err)
	require.Equal(t, firstHash, secondHash)

	result := replayer.ReplayTournament(context.Background(), "tour_hash", firstHash)
	require.NoError(t, result.Err)
	require.True(t, result.ParityOK)
}

func openReplayTestDB(t *testing.T) *sql.DB {
	t.Helper()

	databaseURL := "postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable"
	if value := getenv("ARENA_TEST_DATABASE_URL"); value != "" {
		databaseURL = value
	}

	db, err := sql.Open("postgres", databaseURL)
	require.NoError(t, err)
	require.NoError(t, db.Ping())
	t.Cleanup(func() {
		require.NoError(t, db.Close())
	})
	for _, stmt := range []string{
		"DROP SCHEMA IF EXISTS public CASCADE",
		"CREATE SCHEMA IF NOT EXISTS public",
		"GRANT ALL ON SCHEMA public TO public",
	} {
		_, err := db.Exec(stmt)
		require.NoError(t, err)
	}
	return db
}

func getenv(key string) string {
	return strings.TrimSpace(os.Getenv(key))
}
