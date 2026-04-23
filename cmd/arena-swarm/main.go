package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"time"

	"github.com/clawchain/clawchain/arena/harness"
)

func main() {
	if err := runMain(os.Args[1:], os.Stdout, os.Stderr); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func runMain(args []string, stdout, stderr io.Writer) error {
	fs := flag.NewFlagSet("arena-swarm", flag.ContinueOnError)
	fs.SetOutput(stdout)

	baseURL := fs.String("base-url", os.Getenv("ARENA_BASE_URL"), "Arena runtime base URL, e.g. http://127.0.0.1:18117")
	miners := fs.Int("miners", 64, "Number of miners to register and run")
	minerIDsFile := fs.String("miner-ids-file", "", "Optional JSON file providing explicit miner IDs/address list")
	policy := fs.String("policy", "codex", "Miner policy mode: codex, heuristic, or random")
	waveID := fs.String("wave-id", "", "Optional wave ID override")
	logFile := fs.String("log-file", "", "Optional JSONL log path")
	maxSteps := fs.Int("max-steps", 20000, "Maximum coordinator cycles before abort")
	maxIdleCycles := fs.Int("max-idle-cycles", 50, "Maximum idle cycles before abort")
	armTimeCap := fs.Bool("arm-time-cap", false, "Arm tournament time-cap immediately after seats publish")
	runnerConcurrency := fs.Int("runner-concurrency", 0, "Optional max concurrent runner requests per coordinator cycle (0 = all)")
	cycleDelayMS := fs.Int("cycle-delay-ms", 0, "Optional delay between coordinator cycles in milliseconds")
	httpTimeoutSeconds := fs.Int("http-timeout-seconds", 15, "HTTP timeout in seconds for harness requests")
	codexBinary := fs.String("codex-binary", envOrDefault("CODEX_BINARY", "codex"), "Codex CLI binary path")
	codexModel := fs.String("codex-model", envOrDefault("CODEX_MODEL", "gpt-5.4-mini"), "Codex model name")
	codexWorkdir := fs.String("codex-workdir", envOrDefault("CODEX_WORKDIR", ""), "Optional working directory for codex exec")

	fs.Usage = func() {
		fmt.Fprintln(stdout, "arena-swarm: create a wave, register miners, run them to completion, and write JSONL logs")
		fmt.Fprintln(stdout)
		fs.PrintDefaults()
	}

	if err := fs.Parse(args); err != nil {
		if err == flag.ErrHelp {
			return nil
		}
		return err
	}

	if *baseURL == "" {
		return fmt.Errorf("base-url is required")
	}
	if *logFile == "" {
		*logFile = fmt.Sprintf("arena-swarm-%s.jsonl", time.Now().UTC().Format("20060102-150405"))
	}
	var minerIDs []string
	if *minerIDsFile != "" {
		loaded, err := loadMinerIDsFromFile(*minerIDsFile)
		if err != nil {
			return err
		}
		minerIDs = loaded
	}

	service, err := harness.New(harness.Config{
		BaseURL:        *baseURL,
		MinerCount:     *miners,
		MinerIDs:       minerIDs,
		PolicyMode:     harness.PolicyMode(*policy),
		WaveID:         *waveID,
		LogPath:        *logFile,
		MaxSteps:       *maxSteps,
		MaxIdleCycles:  *maxIdleCycles,
		HTTPTimeout:    time.Duration(*httpTimeoutSeconds) * time.Second,
		ArmTimeCap:     *armTimeCap,
		MaxConcurrency: *runnerConcurrency,
		CycleDelay:     time.Duration(*cycleDelayMS) * time.Millisecond,
		CodexBinary:    *codexBinary,
		CodexModel:     *codexModel,
		CodexWorkdir:   *codexWorkdir,
	})
	if err != nil {
		return err
	}

	result, err := service.Run(context.Background())
	if err != nil {
		return err
	}

	fmt.Fprintf(stdout, "wave_id=%s\n", result.WaveID)
	fmt.Fprintf(stdout, "tournament_id=%s\n", result.TournamentID)
	fmt.Fprintf(stdout, "status=%s\n", result.Standing.Status)
	fmt.Fprintf(stdout, "completed_reason=%s\n", result.Standing.CompletedReason)
	fmt.Fprintf(stdout, "winner_miner_id=%s\n", result.Standing.WinnerMinerID)
	fmt.Fprintf(stdout, "steps=%d\n", result.Steps)
	fmt.Fprintf(stdout, "log_path=%s\n", result.LogPath)
	_, _ = stderr.Write([]byte{})
	return nil
}

func envOrDefault(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

type minerIDEntry struct {
	Address string `json:"address"`
	MinerID string `json:"miner_id"`
}

type minerIDManifest struct {
	Miners []minerIDEntry `json:"miners"`
}

func loadMinerIDsFromFile(path string) ([]string, error) {
	payload, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read miner ids file: %w", err)
	}

	var direct []string
	if err := json.Unmarshal(payload, &direct); err == nil && len(direct) > 0 {
		return direct, nil
	}

	var entries []minerIDEntry
	if err := json.Unmarshal(payload, &entries); err == nil && len(entries) > 0 {
		out := make([]string, 0, len(entries))
		for _, entry := range entries {
			value := entry.Address
			if value == "" {
				value = entry.MinerID
			}
			if value != "" {
				out = append(out, value)
			}
		}
		if len(out) > 0 {
			return out, nil
		}
	}

	var manifest minerIDManifest
	if err := json.Unmarshal(payload, &manifest); err == nil && len(manifest.Miners) > 0 {
		out := make([]string, 0, len(manifest.Miners))
		for _, entry := range manifest.Miners {
			value := entry.Address
			if value == "" {
				value = entry.MinerID
			}
			if value != "" {
				out = append(out, value)
			}
		}
		if len(out) > 0 {
			return out, nil
		}
	}

	return nil, fmt.Errorf("miner ids file %s does not contain a supported miner list", path)
}
