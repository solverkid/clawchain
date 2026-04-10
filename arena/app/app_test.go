package app_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/app"
	"github.com/clawchain/clawchain/arena/config"
)

func TestNewAppRequiresDatabaseURL(t *testing.T) {
	cfg := config.Config{}

	_, err := app.New(cfg)
	if err == nil || !strings.Contains(err.Error(), "database url") {
		t.Fatalf("expected missing database url error, got %v", err)
	}
}

func TestAppWiresAdminLockPublishFlow(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	t.Cleanup(func() {
		require.NoError(t, application.Close(context.Background()))
	})

	handler := application.Handler()

	createWaveResp := httptest.NewRecorder()
	createWaveReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves", strings.NewReader(`{
		"wave_id":"wave_admin_1",
		"mode":"rated",
		"registration_open_at":"2026-04-10T19:00:00Z",
		"registration_close_at":"2026-04-10T19:30:00Z",
		"scheduled_start_at":"2026-04-10T20:00:00Z"
	}`))
	handler.ServeHTTP(createWaveResp, createWaveReq)
	require.Equal(t, http.StatusCreated, createWaveResp.Code)

	for i := 1; i <= 56; i++ {
		resp := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodPost, "/v1/arena/waves/wave_admin_1/register", strings.NewReader(fmt.Sprintf(`{"miner_id":"miner_%02d"}`, i)))
		handler.ServeHTTP(resp, req)
		require.Equal(t, http.StatusOK, resp.Code)
	}

	lockResp := httptest.NewRecorder()
	lockReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves/wave_admin_1/lock", nil)
	handler.ServeHTTP(lockResp, lockReq)
	require.Equal(t, http.StatusOK, lockResp.Code)

	var lockBody map[string]any
	require.NoError(t, json.Unmarshal(lockResp.Body.Bytes(), &lockBody))
	tournamentID := lockBody["tournament_id"].(string)

	publishResp := httptest.NewRecorder()
	publishReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves/wave_admin_1/publish-seats", nil)
	handler.ServeHTTP(publishResp, publishReq)
	require.Equal(t, http.StatusOK, publishResp.Code)

	seatResp := httptest.NewRecorder()
	seatReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/seat-assignment/miner_01", nil)
	handler.ServeHTTP(seatResp, seatReq)
	require.Equal(t, http.StatusOK, seatResp.Code)
	require.Contains(t, seatResp.Body.String(), `"table_id"`)

	verifyDB := openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()
	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_wave WHERE wave_id = $1", "wave_admin_1"))
	require.Equal(t, 56, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_entrant WHERE wave_id = $1", "wave_admin_1"))
	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_tournament WHERE tournament_id = $1", tournamentID))
}

func TestRunServesHealthUntilContextCancel(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	runDone := make(chan error, 1)
	go func() {
		runDone <- application.Run(ctx)
	}()

	require.Eventually(t, func() bool {
		resp, err := http.Get("http://" + application.HTTPAddr() + "/healthz")
		if err != nil {
			return false
		}
		defer resp.Body.Close()
		return resp.StatusCode == http.StatusOK
	}, 2*time.Second, 25*time.Millisecond)

	cancel()
	require.NoError(t, <-runDone)
}

func arenaAppTestDatabaseURL() string {
	if value := os.Getenv("ARENA_TEST_DATABASE_URL"); value != "" {
		return value
	}

	return "postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable"
}

func openArenaAppTestDB(t *testing.T) *sql.DB {
	t.Helper()

	db, err := sql.Open("postgres", arenaAppTestDatabaseURL())
	require.NoError(t, err)
	require.NoError(t, db.Ping())
	return db
}

func resetArenaAppSchema(t *testing.T, db *sql.DB) {
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

func countArenaAppRows(t *testing.T, db *sql.DB, query string, args ...any) int {
	t.Helper()

	var count int
	require.NoError(t, db.QueryRow(query, args...).Scan(&count))
	return count
}
