package recovery

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

func TestRecoverySynthesizesExpiredDeadlineTimeout(t *testing.T) {
	service := newRecoverableServiceForTest()

	require.NoError(t, service.RecoverTournament(context.Background(), "tour_1"))
	require.True(t, service.SawSyntheticTimeout("deadline-1"))
}

func newRecoverableServiceForTest() *Service {
	now := time.Date(2026, time.April, 10, 16, 0, 0, 0, time.UTC)

	return NewService(Store{
		Snapshots: map[string]model.TableSnapshot{
			"tour_1": {
				ID:           "tblsnap:tour_1:1",
				TournamentID: "tour_1",
				TableID:      "tbl:tour_1:01",
			},
		},
		Deadlines: []model.ActionDeadline{{
			DeadlineID:   "deadline-1",
			TournamentID: "tour_1",
			TableID:      "tbl:tour_1:01",
			HandID:       "hand:tour_1:01:0001",
			PhaseID:      "phase-signal-1",
			SeatID:       "seat:tbl:tour_1:01:07",
			DeadlineAt:   now.Add(-time.Second),
			Status:       "open",
		}},
	}, func() time.Time { return now })
}

func TestRecoveryLoadsExpiredDeadlinesFromRepository(t *testing.T) {
	db := openRecoveryTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	now := time.Date(2026, time.April, 10, 16, 0, 0, 0, time.UTC)
	require.NoError(t, repo.UpsertWave(context.Background(), model.Wave{
		ID:                  "wave_db",
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
		ID:     "tour_db",
		WaveID: "wave_db",
		Mode:   model.RatedMode,
		State:  model.TournamentStateReady,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "v1",
			StateHash:           "t-state",
			PayloadHash:         "t-payload",
		},
		CreatedAt: now,
		UpdatedAt: now,
	}))
	require.NoError(t, repo.UpsertTable(context.Background(), model.Table{
		ID:           "tbl:tour_db:01",
		TournamentID: "tour_db",
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
	require.NoError(t, repo.SaveTableSnapshot(context.Background(), model.TableSnapshot{
		ID:           "tblsnap:tour_db:1",
		TournamentID: "tour_db",
		TableID:      "tbl:tour_db:01",
		StreamKey:    "table:tbl:tour_db:01",
		StreamSeq:    1,
		StateSeq:     1,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "v1",
			StateHash:           "snapshot-state",
			PayloadHash:         "snapshot-payload",
		},
		Payload:   []byte(`{"acting_seat_no":7}`),
		CreatedAt: now,
	}))
	require.NoError(t, repo.UpsertActionDeadline(context.Background(), model.ActionDeadline{
		DeadlineID:   "deadline-db-1",
		TournamentID: "tour_db",
		TableID:      "tbl:tour_db:01",
		HandID:       "hand:tour_db:01:0001",
		PhaseID:      "phase-signal-1",
		SeatID:       "seat:tbl:tour_db:01:07",
		DeadlineAt:   now.Add(-time.Second),
		Status:       "open",
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "v1",
			StateHash:           "deadline-state",
			PayloadHash:         "deadline-payload",
		},
		CreatedAt: now,
		UpdatedAt: now,
	}))

	service := NewRepositoryService(repo, func() time.Time { return now })
	require.NoError(t, service.RecoverTournament(context.Background(), "tour_db"))
	require.True(t, service.SawSyntheticTimeout("deadline-db-1"))
}

func openRecoveryTestDB(t *testing.T) *sql.DB {
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
