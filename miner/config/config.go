// Package config 定义矿工客户端的配置结构和默认值。
// 支持从命令行参数和环境变量加载配置。
package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Config 矿工客户端配置
type Config struct {
	NodeRPC     string `json:"node_rpc"`      // CometBFT RPC 地址，如 tcp://localhost:26657
	ChainID     string `json:"chain_id"`      // 链 ID，如 clawchain-testnet-1
	KeyName     string `json:"key_name"`      // 矿工密钥名
	KeyringDir  string `json:"keyring_dir"`   // 密钥存储目录
	ChainBinary string `json:"chain_binary"`  // clawchaind binary path

	LLMEndpoint string `json:"llm_endpoint"` // LLM API 端点，如 http://localhost:8080/v1
	LLMAPIKey   string `json:"llm_api_key"`  // LLM API 密钥
	LLMModel    string `json:"llm_model"`    // 模型名称，如 gpt-4

	StakeAmount uint64 `json:"stake_amount"` // 质押金额（uclaw）
	LogLevel    string `json:"log_level"`    // 日志级别：debug/info/warn/error
}

// DefaultConfig 返回默认配置
func DefaultConfig() *Config {
	home, _ := os.UserHomeDir()
	return &Config{
		NodeRPC:     "tcp://localhost:26657",
		ChainID:     "clawchain-testnet-1",
		KeyName:     "miner1",
		KeyringDir:  filepath.Join(home, ".clawchain-testnet"),
		ChainBinary: "clawchaind",
		LLMEndpoint: "http://localhost:8080/v1",
		LLMAPIKey:   "",
		LLMModel:    "gpt-4",
		StakeAmount: 100000000, // 100 CLAW
		LogLevel:    "info",
	}
}

// NodeHTTPURL 将 tcp:// 格式的 RPC 地址转换为 http:// 格式
func (c *Config) NodeHTTPURL() string {
	// CometBFT RPC 实际是 HTTP，将 tcp:// 替换为 http://
	addr := c.NodeRPC
	if len(addr) > 6 && addr[:6] == "tcp://" {
		addr = "http://" + addr[6:]
	}
	return addr
}

// NodeWSURL 将 RPC 地址转换为 WebSocket 格式
func (c *Config) NodeWSURL() string {
	addr := c.NodeRPC
	if len(addr) > 6 && addr[:6] == "tcp://" {
		addr = "ws://" + addr[6:]
	}
	return addr + "/websocket"
}

// Validate 验证配置是否完整
func (c *Config) Validate() error {
	if c.NodeRPC == "" {
		return fmt.Errorf("node_rpc 不能为空")
	}
	if c.ChainID == "" {
		return fmt.Errorf("chain_id 不能为空")
	}
	if c.KeyName == "" {
		return fmt.Errorf("key_name 不能为空")
	}
	return nil
}

// SaveToFile 将配置保存到 JSON 文件
func (c *Config) SaveToFile(path string) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("创建配置目录失败: %w", err)
	}
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return fmt.Errorf("序列化配置失败: %w", err)
	}
	return os.WriteFile(path, data, 0o644)
}

// LoadFromFile 从 JSON 文件加载配置
func LoadFromFile(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("读取配置文件失败: %w", err)
	}
	cfg := DefaultConfig()
	if err := json.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("解析配置文件失败: %w", err)
	}
	return cfg, nil
}
