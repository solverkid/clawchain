package harness

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/app"
	"github.com/clawchain/clawchain/arena/config"
	"github.com/clawchain/clawchain/arena/testutil"
)

const harnessTestSchema = "arena_harness_test"

func TestNewUsesDynamicClockByDefault(t *testing.T) {
	service, err := New(Config{
		BaseURL:    "http://127.0.0.1:18117",
		MinerCount: 2,
		PolicyMode: PolicyModeHeuristic,
	})
	require.NoError(t, err)

	first := service.cfg.Now()
	time.Sleep(20 * time.Millisecond)
	second := service.cfg.Now()
	require.True(t, second.After(first), "expected dynamic clock, got %s then %s", first, second)
}

func TestNewRejectsCodexModeWithoutBinary(t *testing.T) {
	_, err := New(Config{
		BaseURL:     "http://127.0.0.1:18117",
		MinerCount:  2,
		PolicyMode:  PolicyModeCodex,
		CodexBinary: "/definitely/missing/codex",
	})
	require.Error(t, err)
	require.Contains(t, err.Error(), "codex binary")
}

func TestNewUsesExplicitMinerIDsWhenProvided(t *testing.T) {
	service, err := New(Config{
		BaseURL:    "http://127.0.0.1:18117",
		MinerCount: 2,
		MinerIDs: []string{
			" claw1miner01 ",
			"claw1miner02",
			"claw1miner01",
		},
		PolicyMode: PolicyModeHeuristic,
	})
	require.NoError(t, err)
	require.Equal(t, []string{"claw1miner01", "claw1miner02"}, service.cfg.MinerIDs)
	require.Equal(t, 2, service.cfg.MinerCount)
	require.Equal(t, "claw1miner01", service.minerID(1))
	require.Equal(t, "claw1miner02", service.minerID(2))
}

func TestServiceRunsTournamentToCompletionAndWritesJSONL(t *testing.T) {
	db := openHarnessTestDB(t)
	resetHarnessSchema(t, db)
	defer func() {
		require.NoError(t, db.Close())
	}()

	application, err := app.New(config.Config{
		DatabaseURL:     harnessTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	server := httptest.NewServer(application.Handler())
	defer server.Close()

	logPath := t.TempDir() + "/arena-harness.jsonl"
	service, err := New(Config{
		BaseURL:       server.URL,
		MinerCount:    2,
		PolicyMode:    PolicyModeHeuristic,
		WaveID:        "wave_harness_e2e_1",
		LogPath:       logPath,
		MaxSteps:      2000,
		MaxIdleCycles: 20,
		Now: func() time.Time {
			return time.Date(2026, time.April, 10, 20, 0, 0, 0, time.UTC)
		},
	})
	require.NoError(t, err)
	seedHarnessSharedMiners(t, db, []string{service.minerID(1), service.minerID(2)}, service.cfg.Now())

	result, err := service.Run(context.Background())
	require.NoError(t, err)
	require.Equal(t, "wave_harness_e2e_1", result.WaveID)
	require.NotEmpty(t, result.TournamentID)
	require.Equal(t, "completed", result.Standing.Status)
	require.Equal(t, "natural_finish", result.Standing.CompletedReason)
	require.Equal(t, logPath, result.LogPath)

	payload, err := os.ReadFile(logPath)
	require.NoError(t, err)

	lines := strings.Split(strings.TrimSpace(string(payload)), "\n")
	require.NotEmpty(t, lines)

	eventTypes := make([]string, 0, len(lines))
	for _, line := range lines {
		var item map[string]any
		require.NoError(t, json.Unmarshal([]byte(line), &item))
		eventTypes = append(eventTypes, item["event"].(string))
	}

	require.Contains(t, eventTypes, "wave_created")
	require.Contains(t, eventTypes, "miner_registered")
	require.Contains(t, eventTypes, "wave_locked")
	require.Contains(t, eventTypes, "seats_published")
	require.Contains(t, eventTypes, "runner_step")
	require.Contains(t, eventTypes, "completed")
}

func seedHarnessSharedMiners(t *testing.T, db *sql.DB, minerIDs []string, at time.Time) {
	t.Helper()
	testutil.SeedSharedMiners(t, db, minerIDs, at)
}

func harnessTestDatabaseURL() string {
	return testutil.DatabaseURLForSchema(harnessTestSchema)
}

func openHarnessTestDB(t *testing.T) *sql.DB {
	t.Helper()
	return testutil.OpenArenaTestDB(t, harnessTestSchema)
}

func resetHarnessSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	testutil.ResetArenaSchema(t, db, harnessTestSchema)
}
