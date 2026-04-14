package bot

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const codexDecisionSchema = `{
  "type": "object",
  "additionalProperties": false,
  "required": ["action_type", "amount", "reason"],
  "properties": {
    "action_type": {"type": "string"},
    "amount": {"type": "integer"},
    "reason": {"type": "string"}
  }
}`

type CodexExecClientConfig struct {
	BinaryPath string
	Model      string
	WorkingDir string
}

type CodexExecClient struct {
	binaryPath string
	model      string
	workingDir string
}

func NewCodexExecClient(cfg CodexExecClientConfig) *CodexExecClient {
	binaryPath := strings.TrimSpace(cfg.BinaryPath)
	if binaryPath == "" {
		binaryPath = "codex"
	}
	model := strings.TrimSpace(cfg.Model)
	if model == "" {
		model = "gpt-5.4-mini"
	}
	workingDir := strings.TrimSpace(cfg.WorkingDir)
	if workingDir == "" {
		workingDir, _ = os.Getwd()
	}

	return &CodexExecClient{
		binaryPath: binaryPath,
		model:      model,
		workingDir: workingDir,
	}
}

func (c *CodexExecClient) Complete(ctx context.Context, systemPrompt, userPrompt string) (string, error) {
	schemaPath, err := writeTempCodexSchema()
	if err != nil {
		return "", err
	}
	defer os.Remove(schemaPath)

	outputFile, err := os.CreateTemp("", "arena-codex-output-*.json")
	if err != nil {
		return "", err
	}
	outputPath := outputFile.Name()
	if err := outputFile.Close(); err != nil {
		return "", err
	}
	defer os.Remove(outputPath)

	args := []string{
		"exec",
		"--skip-git-repo-check",
		"--ephemeral",
		"--sandbox", "read-only",
		"-m", c.model,
		"-C", c.workingDir,
		"--output-schema", schemaPath,
		"-o", outputPath,
		"-",
	}
	cmd := exec.CommandContext(ctx, c.binaryPath, args...)
	cmd.Stdin = strings.NewReader(codexPrompt(systemPrompt, userPrompt))

	output, err := cmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("codex exec failed: %w (%s)", err, strings.TrimSpace(string(output)))
	}

	result, err := os.ReadFile(outputPath)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(result)), nil
}

func codexPrompt(systemPrompt, userPrompt string) string {
	return strings.TrimSpace(strings.Join([]string{
		"SYSTEM:",
		systemPrompt,
		"",
		"USER:",
		userPrompt,
		"",
		"Return only JSON that satisfies the provided schema.",
	}, "\n"))
}

func writeTempCodexSchema() (string, error) {
	file, err := os.CreateTemp("", "arena-codex-schema-*.json")
	if err != nil {
		return "", err
	}
	path := filepath.Clean(file.Name())
	if _, err := file.WriteString(codexDecisionSchema); err != nil {
		_ = file.Close()
		return "", err
	}
	if err := file.Close(); err != nil {
		return "", err
	}
	return path, nil
}
