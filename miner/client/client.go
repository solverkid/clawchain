// Package client 提供与 ClawChain 节点的交互功能。
// 通过 CometBFT RPC（HTTP/WebSocket）连接节点，执行查询和交易提交。
// 矿工客户端是独立程序，不依赖 Cosmos SDK，只使用标准 HTTP 接口。
package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"time"

	"github.com/clawchain/clawminer/config"
	"github.com/clawchain/clawminer/solver"
)

// ChainClient 链上交互客户端
type ChainClient struct {
	cfg        *config.Config
	httpClient *http.Client
	logger     *slog.Logger
}

// NewChainClient 创建链上交互客户端
func NewChainClient(cfg *config.Config, logger *slog.Logger) *ChainClient {
	return &ChainClient{
		cfg: cfg,
		httpClient: &http.Client{
			Timeout: 15 * time.Second,
		},
		logger: logger,
	}
}

// --- RPC 通用结构 ---

// rpcRequest JSON-RPC 请求
type rpcRequest struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      int         `json:"id"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params,omitempty"`
}

// rpcResponse JSON-RPC 响应
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

// --- 区块和状态查询 ---

// BlockResult 区块信息
type BlockResult struct {
	Height int64  `json:"height,string"`
	Time   string `json:"time"`
}

// StatusResult 节点状态
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

// MinerInfo 矿工状态信息
type MinerInfo struct {
	Address    string `json:"address"`
	Status     string `json:"status"`
	Stake      uint64 `json:"stake,string"`
	Reputation uint64 `json:"reputation,string"`
}

// BalanceResult 余额查询结果
type BalanceResult struct {
	Denom  string `json:"denom"`
	Amount string `json:"amount"`
}

// GetStatus 查询节点状态
func (c *ChainClient) GetStatus(ctx context.Context) (*StatusResult, error) {
	resp, err := c.rpcCall(ctx, "status", nil)
	if err != nil {
		return nil, fmt.Errorf("查询节点状态失败: %w", err)
	}

	var result StatusResult
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, fmt.Errorf("解析状态响应失败: %w", err)
	}
	return &result, nil
}

// GetLatestBlock 获取最新区块高度
func (c *ChainClient) GetLatestBlock(ctx context.Context) (int64, error) {
	status, err := c.GetStatus(ctx)
	if err != nil {
		return 0, err
	}
	var height int64
	fmt.Sscanf(status.SyncInfo.LatestBlockHeight, "%d", &height)
	return height, nil
}

// --- 挑战相关查询 ---

// GetPendingChallenges 查询分配给指定矿工的待处理挑战
func (c *ChainClient) GetPendingChallenges(ctx context.Context, minerAddr string) ([]solver.Challenge, error) {
	// 通过 ABCI Query 查询 challenge 模块
	path := fmt.Sprintf("\"custom/challenge/pending/%s\"", minerAddr)
	params := map[string]interface{}{
		"path": path,
	}
	resp, err := c.rpcCall(ctx, "abci_query", params)
	if err != nil {
		return nil, fmt.Errorf("查询待处理挑战失败: %w", err)
	}

	// 解析 ABCI Query 响应
	var queryResult struct {
		Response struct {
			Value []byte `json:"value"`
			Code  uint32 `json:"code"`
			Log   string `json:"log"`
		} `json:"response"`
	}
	if err := json.Unmarshal(resp, &queryResult); err != nil {
		return nil, fmt.Errorf("解析挑战查询响应失败: %w", err)
	}

	if queryResult.Response.Code != 0 {
		return nil, fmt.Errorf("查询挑战失败: %s", queryResult.Response.Log)
	}

	var challenges []solver.Challenge
	if len(queryResult.Response.Value) > 0 {
		if err := json.Unmarshal(queryResult.Response.Value, &challenges); err != nil {
			return nil, fmt.Errorf("解析挑战列表失败: %w", err)
		}
	}
	return challenges, nil
}

// --- 交易提交 ---

// BroadcastTx 广播交易（使用 broadcast_tx_sync）
func (c *ChainClient) BroadcastTx(ctx context.Context, txBytes []byte) (string, error) {
	params := map[string]interface{}{
		"tx": txBytes,
	}
	resp, err := c.rpcCall(ctx, "broadcast_tx_sync", params)
	if err != nil {
		return "", fmt.Errorf("广播交易失败: %w", err)
	}

	var result struct {
		Code uint32 `json:"code"`
		Hash string `json:"hash"`
		Log  string `json:"log"`
	}
	if err := json.Unmarshal(resp, &result); err != nil {
		return "", fmt.Errorf("解析广播响应失败: %w", err)
	}

	if result.Code != 0 {
		return "", fmt.Errorf("交易失败 (code=%d): %s", result.Code, result.Log)
	}

	return result.Hash, nil
}

// SubmitCommit 提交挑战答案的 commit（哈希承诺）
func (c *ChainClient) SubmitCommit(ctx context.Context, minerAddr, challengeID, commitHash string) (string, error) {
	msg := map[string]interface{}{
		"type": "challenge/MsgSubmitCommit",
		"value": map[string]string{
			"miner_address": minerAddr,
			"challenge_id":  challengeID,
			"commit_hash":   commitHash,
		},
	}
	return c.broadcastMsg(ctx, msg)
}

// SubmitReveal 提交挑战答案的 reveal（明文答案+盐值）
func (c *ChainClient) SubmitReveal(ctx context.Context, minerAddr, challengeID, answer, salt string) (string, error) {
	msg := map[string]interface{}{
		"type": "challenge/MsgSubmitReveal",
		"value": map[string]string{
			"miner_address": minerAddr,
			"challenge_id":  challengeID,
			"answer":        answer,
			"salt":          salt,
		},
	}
	return c.broadcastMsg(ctx, msg)
}

// RegisterMiner 注册矿工并质押
func (c *ChainClient) RegisterMiner(ctx context.Context, minerAddr string, stakeAmount uint64) (string, error) {
	msg := map[string]interface{}{
		"type": "poa/MsgRegisterMiner",
		"value": map[string]interface{}{
			"miner_address": minerAddr,
			"stake": map[string]interface{}{
				"denom":  "uclaw",
				"amount": fmt.Sprintf("%d", stakeAmount),
			},
		},
	}
	return c.broadcastMsg(ctx, msg)
}

// GetMinerInfo 查询矿工状态
func (c *ChainClient) GetMinerInfo(ctx context.Context, minerAddr string) (*MinerInfo, error) {
	path := fmt.Sprintf("\"custom/poa/miner/%s\"", minerAddr)
	params := map[string]interface{}{
		"path": path,
	}
	resp, err := c.rpcCall(ctx, "abci_query", params)
	if err != nil {
		return nil, fmt.Errorf("查询矿工信息失败: %w", err)
	}

	var queryResult struct {
		Response struct {
			Value []byte `json:"value"`
			Code  uint32 `json:"code"`
			Log   string `json:"log"`
		} `json:"response"`
	}
	if err := json.Unmarshal(resp, &queryResult); err != nil {
		return nil, fmt.Errorf("解析矿工查询响应失败: %w", err)
	}

	if queryResult.Response.Code != 0 {
		return nil, fmt.Errorf("查询矿工失败: %s", queryResult.Response.Log)
	}

	var info MinerInfo
	if len(queryResult.Response.Value) > 0 {
		if err := json.Unmarshal(queryResult.Response.Value, &info); err != nil {
			return nil, fmt.Errorf("解析矿工信息失败: %w", err)
		}
	}
	return &info, nil
}

// --- 内部方法 ---

// broadcastMsg 构建并广播消息（简化版，实际需要签名）
func (c *ChainClient) broadcastMsg(ctx context.Context, msg interface{}) (string, error) {
	// 注意：这是简化实现。实际运行时需要：
	// 1. 从 keyring 加载私钥
	// 2. 获取 account number 和 sequence
	// 3. 构建 StdTx 并签名
	// 4. 编码为 amino/protobuf 字节
	// 当前版本直接将 JSON 编码后广播，链跑起来后需要完善签名流程
	txBytes, err := json.Marshal(map[string]interface{}{
		"msg":  []interface{}{msg},
		"fee":  map[string]interface{}{"amount": []interface{}{}, "gas": "200000"},
		"memo": "clawminer",
	})
	if err != nil {
		return "", fmt.Errorf("序列化交易失败: %w", err)
	}

	return c.BroadcastTx(ctx, txBytes)
}

// rpcCall 执行 JSON-RPC 调用
func (c *ChainClient) rpcCall(ctx context.Context, method string, params interface{}) (json.RawMessage, error) {
	reqBody := rpcRequest{
		JSONRPC: "2.0",
		ID:      1,
		Method:  method,
		Params:  params,
	}

	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("序列化 RPC 请求失败: %w", err)
	}

	url := c.cfg.NodeHTTPURL()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, fmt.Errorf("创建 RPC 请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("RPC 调用失败: %w", err)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取 RPC 响应失败: %w", err)
	}

	var rpcResp rpcResponse
	if err := json.Unmarshal(respBytes, &rpcResp); err != nil {
		return nil, fmt.Errorf("解析 RPC 响应失败: %w", err)
	}

	if rpcResp.Error != nil {
		return nil, fmt.Errorf("RPC 错误 (%d): %s", rpcResp.Error.Code, rpcResp.Error.Message)
	}

	return rpcResp.Result, nil
}
