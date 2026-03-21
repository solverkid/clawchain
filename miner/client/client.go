// Package client provides chain interaction for ClawMiner.
// Uses CometBFT JSON-RPC for queries and clawchaind CLI for tx signing/broadcasting.
package client

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/clawchain/clawminer/config"
	"github.com/clawchain/clawminer/solver"
)

// Unused import guard
var _ = strconv.Itoa

// ChainClient interacts with the ClawChain node.
type ChainClient struct {
	cfg        *config.Config
	httpClient *http.Client
	logger     *slog.Logger
	sequence   int // tracks tx sequence for offline signing
}

// NewChainClient creates a new chain client.
func NewChainClient(cfg *config.Config, logger *slog.Logger) *ChainClient {
	return &ChainClient{
		cfg: cfg,
		httpClient: &http.Client{
			Timeout: 15 * time.Second,
		},
		logger: logger,
	}
}

// ═══════════════════════════════════════
// Queries (via CometBFT JSON-RPC)
// ═══════════════════════════════════════

type StatusResult struct {
	NodeInfo struct {
		Network string `json:"network"`
		Moniker string `json:"moniker"`
	} `json:"node_info"`
	SyncInfo struct {
		LatestBlockHeight string `json:"latest_block_height"`
		CatchingUp        bool   `json:"catching_up"`
	} `json:"sync_info"`
}

func (c *ChainClient) GetStatus(ctx context.Context) (*StatusResult, error) {
	resp, err := c.rpcCall(ctx, "status", nil)
	if err != nil {
		return nil, err
	}
	var result StatusResult
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, fmt.Errorf("parse status: %w", err)
	}
	return &result, nil
}

func (c *ChainClient) GetLatestBlock(ctx context.Context) (int64, error) {
	status, err := c.GetStatus(ctx)
	if err != nil {
		return 0, err
	}
	var h int64
	fmt.Sscanf(status.SyncInfo.LatestBlockHeight, "%d", &h)
	return h, nil
}

// GetPendingChallenges queries pending challenges from the chain's KV store.
func (c *ChainClient) GetPendingChallenges(ctx context.Context, minerAddr string) ([]solver.Challenge, error) {
	// Query via ABCI for challenges in the current epoch
	height, err := c.GetLatestBlock(ctx)
	if err != nil {
		return nil, err
	}

	// Calculate current epoch (50-block epochs by default, configurable)
	epochBlocks := int64(100) // default
	epoch := height / epochBlocks

	// Try to read the challenge for current epoch from ABCI store
	key := fmt.Sprintf("challenge:ch-%d-0", epoch)
	data, err := c.abciQuery(ctx, "/store/challenge/key", []byte(key))
	if err != nil || len(data) == 0 {
		return nil, nil // no challenges
	}

	// Parse the on-chain challenge format
	var onChainCh struct {
		ID             string            `json:"id"`
		Type           string            `json:"type"`
		Prompt         string            `json:"prompt"`
		Status         string            `json:"status"`
		Commits        map[string]string `json:"commits"`
		Reveals        map[string]string `json:"reveals"`
		ExpectedAnswer string            `json:"expected_answer"`
	}
	if err := json.Unmarshal(data, &onChainCh); err != nil {
		return nil, nil
	}

	// Skip if already committed by this miner or completed
	if _, ok := onChainCh.Commits[minerAddr]; ok {
		return nil, nil
	}
	if onChainCh.Status == "complete" || onChainCh.Status == "expired" {
		return nil, nil
	}

	ch := solver.Challenge{
		ID:     onChainCh.ID,
		Type:   solver.ChallengeType(onChainCh.Type),
		Prompt: onChainCh.Prompt,
	}
	return []solver.Challenge{ch}, nil
}

// ═══════════════════════════════════════
// Transactions (via clawchaind CLI)
// ═══════════════════════════════════════

// RegisterMiner registers a miner on-chain.
func (c *ChainClient) RegisterMiner(ctx context.Context, minerAddr string, stakeAmount uint64) (string, error) {
	return c.execTx(ctx, "poa", "register", minerAddr, strconv.FormatUint(stakeAmount, 10))
}

// SubmitCommit submits a commit hash for a challenge.
func (c *ChainClient) SubmitCommit(ctx context.Context, minerAddr, challengeID, commitHash string) (string, error) {
	return c.execTx(ctx, "challenge", "submit-commit", minerAddr, challengeID, commitHash)
}

// SubmitReveal submits the reveal (answer + salt) for a challenge.
func (c *ChainClient) SubmitReveal(ctx context.Context, minerAddr, challengeID, answer, salt string) (string, error) {
	return c.execTx(ctx, "challenge", "submit-reveal", minerAddr, challengeID, answer, salt)
}

// ComputeCommitHash computes SHA256(answer + salt) for commit-reveal.
func ComputeCommitHash(answer, salt string) string {
	h := sha256.New()
	h.Write([]byte(answer + salt))
	return hex.EncodeToString(h.Sum(nil))
}

// execTx executes a chain transaction via clawchaind CLI.
func (c *ChainClient) execTx(ctx context.Context, module string, args ...string) (string, error) {
	// Find clawchaind binary
	binary := c.cfg.ChainBinary
	if binary == "" {
		binary = "clawchaind"
	}

	cmdArgs := []string{"tx", module}
	cmdArgs = append(cmdArgs, args...)
	cmdArgs = append(cmdArgs,
		"--from", c.cfg.KeyName,
		"--keyring-backend", "test",
		"--keyring-dir", c.cfg.KeyringDir,
		"--chain-id", c.cfg.ChainID,
		"--node", c.cfg.NodeRPC,
		"--fees", "10uclaw",
		"--gas", "200000",
		"--yes",
		"--output", "json",
	)

	c.logger.Debug("executing tx", "binary", binary, "args", cmdArgs)

	cmd := exec.CommandContext(ctx, binary, cmdArgs...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("tx failed: %s (stderr: %s)", err, stderr.String())
	}

	// Parse response
	var resp struct {
		Code   int    `json:"code"`
		TxHash string `json:"txhash"`
		Log    string `json:"raw_log"`
	}
	if err := json.Unmarshal(stdout.Bytes(), &resp); err != nil {
		return "", fmt.Errorf("parse tx response: %w (output: %s)", err, stdout.String())
	}

	if resp.Code != 0 {
		return "", fmt.Errorf("tx failed with code %d: %s", resp.Code, resp.Log)
	}

	c.logger.Info("tx broadcast",
		"hash", resp.TxHash[:16]+"...",
		"code", resp.Code,
	)

	return resp.TxHash, nil
}

// ═══════════════════════════════════════
// Internal: JSON-RPC + ABCI Query
// ═══════════════════════════════════════

type rpcRequest struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      int         `json:"id"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params,omitempty"`
}

type rpcResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      int             `json:"id"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

func (c *ChainClient) rpcCall(ctx context.Context, method string, params interface{}) (json.RawMessage, error) {
	reqBody := rpcRequest{JSONRPC: "2.0", ID: 1, Method: method, Params: params}
	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		return nil, err
	}

	url := c.cfg.NodeHTTPURL()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var rpcResp rpcResponse
	if err := json.Unmarshal(respBytes, &rpcResp); err != nil {
		return nil, err
	}

	if rpcResp.Error != nil {
		return nil, fmt.Errorf("rpc error (%d): %s", rpcResp.Error.Code, rpcResp.Error.Message)
	}

	return rpcResp.Result, nil
}

func (c *ChainClient) abciQuery(ctx context.Context, path string, data []byte) ([]byte, error) {
	params := map[string]interface{}{
		"path":   fmt.Sprintf("%q", path),
		"data":   fmt.Sprintf("%x", data),
		"height": "0",
	}
	resp, err := c.rpcCall(ctx, "abci_query", params)
	if err != nil {
		return nil, err
	}

	var qr struct {
		Response struct {
			Code  uint32 `json:"code"`
			Value []byte `json:"value"`
			Log   string `json:"log"`
		} `json:"response"`
	}
	if err := json.Unmarshal(resp, &qr); err != nil {
		return nil, err
	}
	if qr.Response.Code != 0 {
		return nil, fmt.Errorf("query failed: %s", qr.Response.Log)
	}
	return qr.Response.Value, nil
}

// GetMinerAddress returns the miner's bech32 address from the keyring.
func (c *ChainClient) GetMinerAddress(ctx context.Context) (string, error) {
	binary := c.cfg.ChainBinary
	if binary == "" {
		binary = "clawchaind"
	}

	cmd := exec.CommandContext(ctx, binary, "keys", "show", c.cfg.KeyName,
		"--keyring-backend", "test",
		"--keyring-dir", c.cfg.KeyringDir,
		"--address",
	)
	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &bytes.Buffer{}

	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("get address: %w", err)
	}

	return strings.TrimSpace(out.String()), nil
}
