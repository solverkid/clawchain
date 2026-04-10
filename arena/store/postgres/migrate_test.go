package postgres_test

import (
	"database/sql"
	"os"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/store/postgres"
)

func TestMigrateCreatesCoreArenaTables(t *testing.T) {
	db := openTestDB(t)

	require.NoError(t, postgres.Migrate(db))

	for _, table := range []string{
		"arena_wave",
		"arena_entrant",
		"arena_waitlist",
		"arena_prestart_check",
		"arena_shard_assignment",
		"arena_tournament",
		"arena_level",
		"arena_table",
		"arena_hand",
		"arena_phase",
		"arena_seat",
		"arena_alias_map",
		"arena_event_log",
		"outbox_event",
		"outbox_dispatch",
		"projector_cursor",
		"dead_letter_event",
		"submission_ledger",
		"arena_action",
		"arena_action_deadline",
		"arena_round_barrier",
		"arena_operator_intervention",
		"arena_reseat_event",
		"arena_elimination_event",
		"arena_rating_input",
		"arena_tournament_snapshot",
		"arena_table_snapshot",
		"arena_hand_snapshot",
		"arena_standing_snapshot",
		"miners",
		"arena_result_entries",
	} {
		require.True(t, tableExists(t, db, table), table)
	}
}

func TestMigrateIsSafeToRerun(t *testing.T) {
	db := openTestDB(t)

	require.NoError(t, postgres.Migrate(db))
	require.NoError(t, postgres.Migrate(db))
}

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()

	databaseURL := os.Getenv("ARENA_TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Fatal("ARENA_TEST_DATABASE_URL is required")
	}

	db, err := sql.Open("postgres", databaseURL)
	require.NoError(t, err)

	t.Cleanup(func() {
		require.NoError(t, db.Close())
	})

	require.NoError(t, db.Ping())
	resetArenaSchema(t, db)

	return db
}

func resetArenaSchema(t *testing.T, db *sql.DB) {
	t.Helper()

	for _, stmt := range []string{
		"DROP SCHEMA IF EXISTS public CASCADE",
		"CREATE SCHEMA public",
		"GRANT ALL ON SCHEMA public TO public",
	} {
		_, err := db.Exec(stmt)
		require.NoError(t, err)
	}
}

func tableExists(t *testing.T, db *sql.DB, table string) bool {
	t.Helper()

	var exists bool
	err := db.QueryRow(`
		SELECT EXISTS (
			SELECT 1
			FROM information_schema.tables
			WHERE table_schema = 'public'
			  AND table_name = $1
		)
	`, table).Scan(&exists)
	require.NoError(t, err)

	return exists
}
