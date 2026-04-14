package harness

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"hash/fnv"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"sync"
	"time"

	"github.com/clawchain/clawchain/arena/bot"
	"github.com/clawchain/clawchain/arena/httpapi"
	"github.com/clawchain/clawchain/arena/swarm"
)

type PolicyMode string

const (
	PolicyModeHeuristic PolicyMode = "heuristic"
	PolicyModeRandom    PolicyMode = "random"
	PolicyModeCodex     PolicyMode = "codex"
)

type Config struct {
	BaseURL       string
	MinerCount    int
	PolicyMode    PolicyMode
	WaveID        string
	LogPath       string
	MaxSteps      int
	MaxIdleCycles int
	HTTPClient    *http.Client
	Now           func() time.Time

	CodexBinary  string
	CodexModel   string
	CodexWorkdir string
}

type Result struct {
	WaveID       string
	TournamentID string
	Standing     bot.Standing
	Steps        int
	LogPath      string
}

type Service struct {
	cfg    Config
	client *runtimeClient
}

type runtimeClient struct {
	baseURL    string
	httpClient *http.Client
}

type logEvent struct {
	At              time.Time `json:"at"`
	Event           string    `json:"event"`
	WaveID          string    `json:"wave_id,omitempty"`
	TournamentID    string    `json:"tournament_id,omitempty"`
	MinerID         string    `json:"miner_id,omitempty"`
	PolicyMode      string    `json:"policy_mode,omitempty"`
	Provider        string    `json:"provider,omitempty"`
	Model           string    `json:"model,omitempty"`
	RequestHash     string    `json:"request_hash,omitempty"`
	ResponseHash    string    `json:"response_hash,omitempty"`
	TableID         string    `json:"table_id,omitempty"`
	SeatNo          int       `json:"seat_no,omitempty"`
	StateSeq        int64     `json:"state_seq,omitempty"`
	CurrentPhase    string    `json:"current_phase,omitempty"`
	ActingSeatNo    int       `json:"acting_seat_no,omitempty"`
	Status          string    `json:"status,omitempty"`
	ActionType      string    `json:"action_type,omitempty"`
	Amount          int64     `json:"amount,omitempty"`
	CompletedReason string    `json:"completed_reason,omitempty"`
	WinnerMinerID   string    `json:"winner_miner_id,omitempty"`
	Steps           int       `json:"steps,omitempty"`
	Error           string    `json:"error,omitempty"`
}

type jsonlWriter struct {
	mu     sync.Mutex
	file   *os.File
	encode *json.Encoder
}

type tracedModelClient struct {
	inner        bot.ChatClient
	minerID      string
	waveID       string
	tournamentID string
	policyMode   PolicyMode
	provider     string
	model        string
	logs         *jsonlWriter
	now          func() time.Time
}

const (
	defaultHarnessHTTPTimeout         = 15 * time.Second
	minHarnessIdleConnsPerHost        = 64
	maxHarnessIdleConnsPerHost        = 256
	defaultHarnessTotalIdleConnFactor = 2
)

func New(cfg Config) (*Service, error) {
	cfg.BaseURL = strings.TrimRight(strings.TrimSpace(cfg.BaseURL), "/")
	if cfg.BaseURL == "" {
		return nil, fmt.Errorf("base url is required")
	}
	if cfg.MinerCount <= 0 {
		return nil, fmt.Errorf("miner count must be positive")
	}
	if cfg.PolicyMode == "" {
		cfg.PolicyMode = PolicyModeHeuristic
	}
	if cfg.Now == nil {
		cfg.Now = func() time.Time {
			return time.Now().UTC()
		}
	}
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = newHarnessHTTPClient(cfg.MinerCount)
	}
	switch cfg.PolicyMode {
	case PolicyModeHeuristic:
	case PolicyModeRandom:
	case PolicyModeCodex:
		binary := cfg.CodexBinary
		if strings.TrimSpace(binary) == "" {
			binary = "codex"
		}
		if _, err := exec.LookPath(binary); err != nil {
			return nil, fmt.Errorf("codex binary not available: %w", err)
		}
		cfg.CodexBinary = binary
		if strings.TrimSpace(cfg.CodexModel) == "" {
			cfg.CodexModel = "gpt-5.4-mini"
		}
	default:
		return nil, fmt.Errorf("unsupported policy mode %q", cfg.PolicyMode)
	}

	return &Service{
		cfg: cfg,
		client: &runtimeClient{
			baseURL:    cfg.BaseURL,
			httpClient: cfg.HTTPClient,
		},
	}, nil
}

func newHarnessHTTPClient(minerCount int) *http.Client {
	connBudget := minerCount * 2
	if connBudget < minHarnessIdleConnsPerHost {
		connBudget = minHarnessIdleConnsPerHost
	}
	if connBudget > maxHarnessIdleConnsPerHost {
		connBudget = maxHarnessIdleConnsPerHost
	}

	baseTransport, _ := http.DefaultTransport.(*http.Transport)
	transport := &http.Transport{}
	if baseTransport != nil {
		transport = baseTransport.Clone()
	}
	transport.MaxIdleConnsPerHost = connBudget
	transport.MaxIdleConns = connBudget * defaultHarnessTotalIdleConnFactor
	transport.MaxConnsPerHost = connBudget

	return &http.Client{
		Timeout:   defaultHarnessHTTPTimeout,
		Transport: transport,
	}
}

func (s *Service) Run(ctx context.Context) (Result, error) {
	var result Result

	logs, err := newJSONLWriter(s.cfg.LogPath)
	if err != nil {
		return result, err
	}
	defer logs.Close()
	result.LogPath = logs.file.Name()

	waveID := s.cfg.WaveID
	if waveID == "" {
		waveID = fmt.Sprintf("wave_harness_%d", s.cfg.Now().Unix())
	}
	result.WaveID = waveID

	createReq := httpapi.CreateWaveRequest{
		WaveID:              waveID,
		Mode:                "rated",
		RegistrationOpenAt:  s.cfg.Now().Add(-2 * time.Minute).UTC(),
		RegistrationCloseAt: s.cfg.Now().Add(-1 * time.Minute).UTC(),
		ScheduledStartAt:    s.cfg.Now().UTC(),
	}
	createResp, err := s.client.CreateWave(ctx, createReq)
	if err != nil {
		return result, err
	}
	if err := logs.Write(logEvent{
		At:         s.cfg.Now(),
		Event:      "wave_created",
		WaveID:     waveID,
		PolicyMode: string(s.cfg.PolicyMode),
	}); err != nil {
		return result, err
	}
	_ = createResp

	for idx := 1; idx <= s.cfg.MinerCount; idx++ {
		minerID := formatMinerID(idx)
		if err := s.client.RegisterMiner(ctx, waveID, minerID); err != nil {
			return result, err
		}
		if err := logs.Write(logEvent{
			At:         s.cfg.Now(),
			Event:      "miner_registered",
			WaveID:     waveID,
			MinerID:    minerID,
			PolicyMode: string(s.cfg.PolicyMode),
		}); err != nil {
			return result, err
		}
	}

	lockResp, err := s.client.LockWave(ctx, waveID)
	if err != nil {
		return result, err
	}
	result.TournamentID = lockResp.TournamentID
	if err := logs.Write(logEvent{
		At:           s.cfg.Now(),
		Event:        "wave_locked",
		WaveID:       waveID,
		TournamentID: lockResp.TournamentID,
		PolicyMode:   string(s.cfg.PolicyMode),
	}); err != nil {
		return result, err
	}

	publishResp, err := s.client.PublishSeats(ctx, waveID)
	if err != nil {
		return result, err
	}
	if publishResp.TournamentID != "" {
		result.TournamentID = publishResp.TournamentID
	}
	if err := logs.Write(logEvent{
		At:           s.cfg.Now(),
		Event:        "seats_published",
		WaveID:       waveID,
		TournamentID: result.TournamentID,
		PolicyMode:   string(s.cfg.PolicyMode),
	}); err != nil {
		return result, err
	}

	runners, err := s.buildRunners(result.TournamentID, waveID, logs)
	if err != nil {
		return result, err
	}

	observer := bot.NewClient(s.cfg.BaseURL, result.TournamentID, formatMinerID(1))
	coordResult, err := swarm.NewCoordinator(swarm.CoordinatorConfig{
		Observer:      observer,
		Runners:       runners,
		MaxSteps:      s.cfg.MaxSteps,
		MaxIdleCycles: s.cfg.MaxIdleCycles,
		OnLog: func(item swarm.ActionLog) {
			_ = logs.Write(logEvent{
				At:           s.cfg.Now(),
				Event:        "runner_step",
				WaveID:       waveID,
				TournamentID: result.TournamentID,
				MinerID:      item.MinerID,
				PolicyMode:   string(s.cfg.PolicyMode),
				TableID:      item.TableID,
				SeatNo:       item.SeatNo,
				StateSeq:     item.StateSeq,
				CurrentPhase: item.CurrentPhase,
				ActingSeatNo: item.ActingSeatNo,
				Status:       item.Status,
				ActionType:   item.Decision.ActionType,
				Amount:       item.Decision.Amount,
			})
		},
	}).Run(ctx)
	if err != nil {
		_ = logs.Write(logEvent{
			At:           s.cfg.Now(),
			Event:        "run_failed",
			WaveID:       waveID,
			TournamentID: result.TournamentID,
			PolicyMode:   string(s.cfg.PolicyMode),
			Error:        err.Error(),
		})
		return result, err
	}

	result.Standing = coordResult.Standing
	result.Steps = coordResult.Steps
	finalEvent := "completed"
	if coordResult.Standing.Status != "completed" {
		finalEvent = "finished"
	}
	if err := logs.Write(logEvent{
		At:              s.cfg.Now(),
		Event:           finalEvent,
		WaveID:          waveID,
		TournamentID:    result.TournamentID,
		PolicyMode:      string(s.cfg.PolicyMode),
		CompletedReason: coordResult.Standing.CompletedReason,
		WinnerMinerID:   coordResult.Standing.WinnerMinerID,
		Steps:           coordResult.Steps,
	}); err != nil {
		return result, err
	}

	return result, nil
}

func (s *Service) buildRunners(tournamentID, waveID string, logs *jsonlWriter) ([]swarm.Runner, error) {
	runners := make([]swarm.Runner, 0, s.cfg.MinerCount)
	for idx := 1; idx <= s.cfg.MinerCount; idx++ {
		minerID := formatMinerID(idx)
		policy, err := s.buildPolicy(minerID, waveID, tournamentID, logs)
		if err != nil {
			return nil, err
		}
		runners = append(runners, bot.NewRunner(bot.RunnerConfig{
			BaseURL:      s.cfg.BaseURL,
			TournamentID: tournamentID,
			MinerID:      minerID,
			HTTPClient:   s.cfg.HTTPClient,
			Policy:       policy,
		}))
	}
	return runners, nil
}

func (s *Service) buildPolicy(minerID, waveID, tournamentID string, logs *jsonlWriter) (bot.Policy, error) {
	fallback := bot.HeuristicPolicy{}
	switch s.cfg.PolicyMode {
	case PolicyModeHeuristic:
		return fallback, nil
	case PolicyModeRandom:
		return bot.NewRandomPolicy(randomSeedForMiner(waveID, tournamentID, minerID)), nil
	case PolicyModeCodex:
		client := bot.NewCodexExecClient(bot.CodexExecClientConfig{
			BinaryPath: s.cfg.CodexBinary,
			Model:      s.cfg.CodexModel,
			WorkingDir: s.cfg.CodexWorkdir,
		})
		return bot.NewLLMPolicy(&tracedModelClient{
			inner:        client,
			minerID:      minerID,
			waveID:       waveID,
			tournamentID: tournamentID,
			policyMode:   s.cfg.PolicyMode,
			provider:     "codex_cli",
			model:        s.cfg.CodexModel,
			logs:         logs,
			now:          s.cfg.Now,
		}, fallback), nil
	default:
		return nil, fmt.Errorf("unsupported policy mode %q", s.cfg.PolicyMode)
	}
}

func randomSeedForMiner(waveID, tournamentID, minerID string) int64 {
	hasher := fnv.New64a()
	_, _ = hasher.Write([]byte(waveID))
	_, _ = hasher.Write([]byte{0})
	_, _ = hasher.Write([]byte(tournamentID))
	_, _ = hasher.Write([]byte{0})
	_, _ = hasher.Write([]byte(minerID))
	return int64(hasher.Sum64())
}

func (c *runtimeClient) CreateWave(ctx context.Context, req httpapi.CreateWaveRequest) (httpapi.WaveMutationResponse, error) {
	var resp httpapi.WaveMutationResponse
	err := c.postJSON(ctx, "/v1/admin/arena/waves", req, &resp)
	return resp, err
}

func (c *runtimeClient) RegisterMiner(ctx context.Context, waveID, minerID string) error {
	return c.postJSON(ctx, fmt.Sprintf("/v1/arena/waves/%s/register", waveID), map[string]string{"miner_id": minerID}, nil)
}

func (c *runtimeClient) LockWave(ctx context.Context, waveID string) (httpapi.WaveMutationResponse, error) {
	var resp httpapi.WaveMutationResponse
	err := c.postJSON(ctx, fmt.Sprintf("/v1/admin/arena/waves/%s/lock", waveID), nil, &resp)
	return resp, err
}

func (c *runtimeClient) PublishSeats(ctx context.Context, waveID string) (httpapi.WaveMutationResponse, error) {
	var resp httpapi.WaveMutationResponse
	err := c.postJSON(ctx, fmt.Sprintf("/v1/admin/arena/waves/%s/publish-seats", waveID), nil, &resp)
	return resp, err
}

func (c *runtimeClient) postJSON(ctx context.Context, path string, payload any, target any) error {
	var body io.Reader
	if payload != nil {
		encoded, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(encoded)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, body)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		if target == nil || len(data) == 0 {
			return nil
		}
		return json.Unmarshal(data, target)
	}

	var errPayload struct {
		Error string `json:"error"`
	}
	if err := json.Unmarshal(data, &errPayload); err == nil && errPayload.Error != "" {
		return fmt.Errorf("arena request failed (%d): %s", resp.StatusCode, errPayload.Error)
	}
	return fmt.Errorf("arena request failed (%d): %s", resp.StatusCode, strings.TrimSpace(string(data)))
}

func (c *tracedModelClient) Complete(ctx context.Context, systemPrompt, userPrompt string) (string, error) {
	requestHash := hashText(systemPrompt + "\n\n" + userPrompt)
	_ = c.logs.Write(logEvent{
		At:           c.now(),
		Event:        "model_request",
		WaveID:       c.waveID,
		TournamentID: c.tournamentID,
		MinerID:      c.minerID,
		PolicyMode:   string(c.policyMode),
		Provider:     c.provider,
		Model:        c.model,
		RequestHash:  requestHash,
	})

	out, err := c.inner.Complete(ctx, systemPrompt, userPrompt)
	if err != nil {
		_ = c.logs.Write(logEvent{
			At:           c.now(),
			Event:        "model_error",
			WaveID:       c.waveID,
			TournamentID: c.tournamentID,
			MinerID:      c.minerID,
			PolicyMode:   string(c.policyMode),
			Provider:     c.provider,
			Model:        c.model,
			RequestHash:  requestHash,
			Error:        err.Error(),
		})
		return "", err
	}

	_ = c.logs.Write(logEvent{
		At:           c.now(),
		Event:        "model_response",
		WaveID:       c.waveID,
		TournamentID: c.tournamentID,
		MinerID:      c.minerID,
		PolicyMode:   string(c.policyMode),
		Provider:     c.provider,
		Model:        c.model,
		RequestHash:  requestHash,
		ResponseHash: hashText(out),
	})
	return out, nil
}

func newJSONLWriter(path string) (*jsonlWriter, error) {
	if strings.TrimSpace(path) == "" {
		file, err := os.CreateTemp("", "arena-harness-*.jsonl")
		if err != nil {
			return nil, err
		}
		return &jsonlWriter{file: file, encode: json.NewEncoder(file)}, nil
	}

	file, err := os.Create(path)
	if err != nil {
		return nil, err
	}
	return &jsonlWriter{file: file, encode: json.NewEncoder(file)}, nil
}

func (w *jsonlWriter) Write(event logEvent) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	if err := w.encode.Encode(event); err != nil {
		return err
	}
	return w.file.Sync()
}

func (w *jsonlWriter) Close() error {
	if w == nil || w.file == nil {
		return nil
	}
	return w.file.Close()
}

func formatMinerID(idx int) string {
	return fmt.Sprintf("miner_%02d", idx)
}

func hashText(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}
