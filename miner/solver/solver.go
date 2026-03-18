// solver.go 实现 AI 任务求解器。
// 根据挑战类型选择不同的求解策略：本地计算或 LLM 调用。
package solver

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
)

// ChallengeType 挑战类型（与链上定义一致）
type ChallengeType string

const (
	ChallengeTextSummary      ChallengeType = "text_summary"
	ChallengeSentiment        ChallengeType = "sentiment"
	ChallengeEntityExtraction ChallengeType = "entity_extraction"
	ChallengeFormatConvert    ChallengeType = "format_convert"
	ChallengeMath             ChallengeType = "math"
	ChallengeLogic            ChallengeType = "logic"
)

// Challenge 来自链上的挑战任务
type Challenge struct {
	ID     string        `json:"id"`
	Type   ChallengeType `json:"type"`
	Prompt string        `json:"prompt"`
}

// Solver AI 任务求解器
type Solver struct {
	llm    *LLMClient
	logger *slog.Logger
}

// NewSolver 创建求解器
func NewSolver(llm *LLMClient, logger *slog.Logger) *Solver {
	return &Solver{
		llm:    llm,
		logger: logger,
	}
}

// Solve 根据挑战类型求解，返回答案字符串
func (s *Solver) Solve(ctx context.Context, challenge Challenge) (string, error) {
	s.logger.Info("开始求解挑战",
		"id", challenge.ID,
		"type", challenge.Type,
	)

	var answer string
	var err error

	switch challenge.Type {
	case ChallengeMath:
		answer, err = s.solveMath(ctx, challenge.Prompt)
	case ChallengeLogic:
		answer, err = s.solveLogic(ctx, challenge.Prompt)
	case ChallengeTextSummary:
		answer, err = s.solveWithLLM(ctx, challenge.Prompt, "text_summary")
	case ChallengeSentiment:
		answer, err = s.solveWithLLM(ctx, challenge.Prompt, "sentiment")
	case ChallengeEntityExtraction:
		answer, err = s.solveWithLLM(ctx, challenge.Prompt, "entity_extraction")
	case ChallengeFormatConvert:
		answer, err = s.solveFormatConvert(ctx, challenge.Prompt)
	default:
		// 未知类型 fallback 到 LLM
		s.logger.Warn("未知挑战类型，使用 LLM fallback", "type", challenge.Type)
		answer, err = s.solveWithLLM(ctx, challenge.Prompt, string(challenge.Type))
	}

	if err != nil {
		return "", fmt.Errorf("求解挑战 %s 失败: %w", challenge.ID, err)
	}

	// 清理答案（去除首尾空白）
	answer = strings.TrimSpace(answer)
	s.logger.Info("挑战求解完成",
		"id", challenge.ID,
		"answer_len", len(answer),
	)
	return answer, nil
}

// solveMath 本地数学计算求解
// 对于简单数学题，尝试本地解析；复杂的 fallback 到 LLM
func (s *Solver) solveMath(ctx context.Context, prompt string) (string, error) {
	s.logger.Debug("数学挑战：使用 LLM 求解", "prompt_len", len(prompt))
	// 数学题可能很复杂，统一用 LLM 处理
	// 未来可以加本地表达式解析器优化简单题
	return s.llm.Complete(ctx,
		"你是一个数学计算助手。只输出最终答案（数字或简洁表达式），不要输出解题过程。",
		prompt,
	)
}

// solveLogic 逻辑推理求解
func (s *Solver) solveLogic(ctx context.Context, prompt string) (string, error) {
	s.logger.Debug("逻辑挑战：使用 LLM 求解", "prompt_len", len(prompt))
	return s.llm.Complete(ctx,
		"你是一个逻辑推理助手。分析问题后只输出最终答案，保持简洁。",
		prompt,
	)
}

// solveWithLLM 使用 LLM 求解特定类型的挑战
func (s *Solver) solveWithLLM(ctx context.Context, prompt string, taskType string) (string, error) {
	systemPrompts := map[string]string{
		"text_summary":      "你是一个文本摘要助手。将输入文本总结为简洁的摘要，保留关键信息。只输出摘要内容。",
		"sentiment":         "你是一个情感分析助手。分析输入文本的情感倾向，只输出: positive / negative / neutral",
		"entity_extraction": "你是一个实体提取助手。从输入文本中提取所有命名实体（人名、地名、组织名等），用逗号分隔输出。",
	}

	sysPrompt, ok := systemPrompts[taskType]
	if !ok {
		sysPrompt = "你是一个AI助手。根据输入完成任务，只输出结果。"
	}

	return s.llm.Complete(ctx, sysPrompt, prompt)
}

// solveFormatConvert 格式转换求解（本地处理）
// 简单格式转换尝试本地处理，复杂的 fallback 到 LLM
func (s *Solver) solveFormatConvert(ctx context.Context, prompt string) (string, error) {
	s.logger.Debug("格式转换挑战", "prompt_len", len(prompt))
	// 格式转换类型多样，统一用 LLM 处理
	return s.llm.Complete(ctx,
		"你是一个格式转换助手。将输入内容转换为要求的格式，只输出转换结果。",
		prompt,
	)
}
