package app

import (
	"context"
	"database/sql"
	"os"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/config"
)

func TestNewConfiguresBoundedDBPool(t *testing.T) {
	db := openArenaInternalTestDB(t)
	resetArenaInternalSchema(t, db)
	require.NoError(t, db.Close())

	application, err := New(config.Config{
		DatabaseURL:     arenaInternalTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	stats := application.db.Stats()
	require.Equal(t, defaultArenaDBMaxOpenConns, stats.MaxOpenConnections)
}

func arenaInternalTestDatabaseURL() string {
	if value := os.Getenv("ARENA_TEST_DATABASE_URL"); value != "" {
		return value
	}
	return "postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable"
}

func openArenaInternalTestDB(t *testing.T) *sql.DB {
	t.Helper()

	db, err := sql.Open("postgres", arenaInternalTestDatabaseURL())
	require.NoError(t, err)
	require.NoError(t, db.Ping())
	return db
}

func resetArenaInternalSchema(t *testing.T, db *sql.DB) {
	t.Helper()

	for _, stmt := range []string{
		"DROP SCHEMA IF EXISTS public CASCADE",
		"CREATE SCHEMA IF NOT EXISTS public",
		"GRANT ALL ON SCHEMA public TO public",
	} {
		_, err := db.Exec(stmt)
		require.NoError(t, err)
	}
}
