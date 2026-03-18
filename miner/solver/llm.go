// Package solver 提供 AI 任务求解功能。
// llm.go 实现 OpenAI 兼容 API 的客户端，支持任意 LLM 端点。
package solver

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"time"
)

// LLMClient OpenAI 兼容 API 客户端
type LLMClient struct {
	endpoint   string       // API 端点，如 http://localhost:8080/v1
	apiKey     string       // API 密钥
	model      string       // 模型名称
	httpClient *http.Client // HTTP 客户端（带超时）
	logger     *slog.Logger
}

// NewLLMClient 创建 LLM 客户端
func NewLLMClient(endpoint, apiKey, model string, logger *slog.Logger) *LLMClient {
	return &LLMClient{
		endpoint: endpoint,
		apiKey:   apiKey,
		model:    model,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		logger: logger,
	}
}

// chatRequest OpenAI Chat Completions 请求体
type chatRequest struct {
	Model    string        `json:"model"`
	Messages []chatMessage `json:"messages"`
}

// chatMessage 聊天消息
type chatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// chatResponse OpenAI Chat Completions 响应体
type chatResponse struct {
	Choices []struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error,omitempty"`
}

// Complete 调用 LLM 完成任务，支持 1 次自动重试
func (c *LLMClient) Complete(ctx context.Context, systemPrompt, userPrompt string) (string, error) {
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		if attempt > 0 {
			c.logger.Warn("LLM 调用重试", "attempt", attempt+1)
			time.Sleep(2 * time.Second)
		}

		result, err := c.doComplete(ctx, systemPrompt, userPrompt)
		if err != nil {
			lastErr = err
			c.logger.Error("LLM 调用失败", "attempt", attempt+1, "error", err)
			continue
		}
		return result, nil
	}
	return "", fmt.Errorf("LLM 调用失败（已重试）: %w", lastErr)
}

// doComplete 执行单次 LLM 调用
func (c *LLMClient) doComplete(ctx context.Context, systemPrompt, userPrompt string) (string, error) {
	reqBody := chatRequest{
		Model: c.model,
		Messages: []chatMessage{
			{Role: "system", Content: systemPrompt},
			{Role: "user", Content: userPrompt},
		},
	}

	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("序列化请求失败: %w", err)
	}

	url := c.endpoint + "/chat/completions"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(bodyBytes))
	if err != nil {
		return "", fmt.Errorf("创建请求失败: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if c.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.apiKey)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("HTTP 请求失败: %w", err)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("读取响应失败: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("LLM API 返回错误状态 %d: %s", resp.StatusCode, string(respBytes))
	}

	var chatResp chatResponse
	if err := json.Unmarshal(respBytes, &chatResp); err != nil {
		return "", fmt.Errorf("解析响应失败: %w", err)
	}

	if chatResp.Error != nil {
		return "", fmt.Errorf("LLM API 错误: %s", chatResp.Error.Message)
	}

	if len(chatResp.Choices) == 0 {
		return "", fmt.Errorf("LLM 返回空结果")
	}

	return chatResp.Choices[0].Message.Content, nil
}
