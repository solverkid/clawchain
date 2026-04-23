package app

import (
	"context"
	"database/sql"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/config"
	"github.com/clawchain/clawchain/arena/testutil"
)

const arenaInternalTestSchema = "arena_app_internal_test"

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
	return testutil.DatabaseURLForSchema(arenaInternalTestSchema)
}

func openArenaInternalTestDB(t *testing.T) *sql.DB {
	t.Helper()
	return testutil.OpenArenaTestDB(t, arenaInternalTestSchema)
}

func resetArenaInternalSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	testutil.ResetArenaSchema(t, db, arenaInternalTestSchema)
}
