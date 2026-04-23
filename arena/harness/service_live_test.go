package harness

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/app"
	"github.com/clawchain/clawchain/arena/config"
	"github.com/clawchain/clawchain/arena/httpapi"
)

func TestLiveCodexMinersProduceIsolatedModelLogs(t *testing.T) {
	if os.Getenv("ARENA_LIVE_CODEX") != "1" {
		t.Skip("set ARENA_LIVE_CODEX=1 to run the live Codex GPT-5.4-mini harness smoke test")
	}

	model := os.Getenv("CODEX_MODEL")
	if model == "" {
		model = "gpt-5.4-mini"
	}
	binary := os.Getenv("CODEX_BINARY")
	if binary == "" {
		binary = "codex"
	}

	db := openHarnessTestDB(t)
	resetHarnessSchema(t, db)
	require.NoError(t, db.Close())

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

	logPath := t.TempDir() + "/arena-harness-live.jsonl"
	service, err := New(Config{
		BaseURL:       server.URL,
		MinerCount:    2,
		PolicyMode:    PolicyModeCodex,
		WaveID:        "wave_harness_live_codex_1",
		LogPath:       logPath,
		MaxSteps:      2000,
		MaxIdleCycles: 20,
		CodexBinary:   binary,
		CodexModel:    model,
		CodexWorkdir:  "/Users/yanchengren/Documents/Projects/clawchain",
		Now:           func() time.Time { return time.Date(2026, time.April, 10, 20, 0, 0, 0, time.UTC) },
	})
	require.NoError(t, err)
	db = openHarnessTestDB(t)
	seedHarnessSharedMiners(t, db, []string{formatMinerID(1), formatMinerID(2)}, service.cfg.Now())
	require.NoError(t, db.Close())

	createReq := httpapi.CreateWaveRequest{
		WaveID:              service.cfg.WaveID,
		Mode:                "rated",
		RegistrationOpenAt:  service.cfg.Now().Add(-2 * time.Minute).UTC(),
		RegistrationCloseAt: service.cfg.Now().Add(-1 * time.Minute).UTC(),
		ScheduledStartAt:    service.cfg.Now().UTC(),
	}
	_, err = service.client.CreateWave(context.Background(), createReq)
	require.NoError(t, err)
	for idx := 1; idx <= service.cfg.MinerCount; idx++ {
		require.NoError(t, service.client.RegisterMiner(context.Background(), service.cfg.WaveID, formatMinerID(idx)))
	}
	lockResp, err := service.client.LockWave(context.Background(), service.cfg.WaveID)
	require.NoError(t, err)
	_, err = service.client.PublishSeats(context.Background(), service.cfg.WaveID)
	require.NoError(t, err)

	logs, err := newJSONLWriter(logPath)
	require.NoError(t, err)
	defer func() {
		require.NoError(t, logs.Close())
	}()

	runners, err := service.buildRunners(lockResp.TournamentID, service.cfg.WaveID, logs)
	require.NoError(t, err)

	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	for cycle := 0; cycle < 8; cycle++ {
		for _, runner := range runners {
			_, err := runner.StepDetailed(ctx)
			require.NoError(t, err)
		}

		requestMiners, responseMiners := parseModelLogMiners(t, logPath, model)
		if len(requestMiners) == service.cfg.MinerCount && len(responseMiners) == service.cfg.MinerCount {
			require.Equal(t, requestMiners, responseMiners)
			return
		}
	}

	requestMiners, responseMiners := parseModelLogMiners(t, logPath, model)
	t.Fatalf("expected codex logs for all miners, requests=%v responses=%v", requestMiners, responseMiners)
}

func parseModelLogMiners(t *testing.T, logPath, model string) (map[string]bool, map[string]bool) {
	t.Helper()

	payload, err := os.ReadFile(logPath)
	require.NoError(t, err)

	requestMiners := map[string]bool{}
	responseMiners := map[string]bool{}
	for _, line := range strings.Split(strings.TrimSpace(string(payload)), "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		var item map[string]any
		require.NoError(t, json.Unmarshal([]byte(line), &item))
		switch item["event"] {
		case "model_request":
			requestMiners[item["miner_id"].(string)] = true
			require.NotEmpty(t, item["request_hash"])
			require.Equal(t, model, item["model"])
			require.Equal(t, "codex_cli", item["provider"])
		case "model_response":
			responseMiners[item["miner_id"].(string)] = true
			require.NotEmpty(t, item["response_hash"])
		}
	}
	return requestMiners, responseMiners
}
