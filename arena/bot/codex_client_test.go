package bot

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestCodexExecClientCallsLocalCodexCLI(t *testing.T) {
	tempDir := t.TempDir()
	argsPath := filepath.Join(tempDir, "args.txt")
	stdinPath := filepath.Join(tempDir, "stdin.txt")
	binaryPath := filepath.Join(tempDir, "codex")

	script := `#!/bin/sh
set -eu
printf '%s\n' "$@" > "` + argsPath + `"
cat > "` + stdinPath + `"
out=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then
    out="$2"
    shift 2
    continue
  fi
  shift
done
printf '%s' '{"action_type":"call","amount":0,"reason":"stub"}' > "$out"
`
	require.NoError(t, os.WriteFile(binaryPath, []byte(script), 0o755))

	client := NewCodexExecClient(CodexExecClientConfig{
		BinaryPath: binaryPath,
		Model:      "gpt-5.4-mini",
		WorkingDir: tempDir,
	})

	out, err := client.Complete(context.Background(), "system prompt", "user prompt")
	require.NoError(t, err)
	require.Equal(t, `{"action_type":"call","amount":0,"reason":"stub"}`, out)

	argsContent, err := os.ReadFile(argsPath)
	require.NoError(t, err)
	args := string(argsContent)
	require.Contains(t, args, "exec")
	require.Contains(t, args, "-m")
	require.Contains(t, args, "gpt-5.4-mini")
	require.Contains(t, args, "--ephemeral")
	require.Contains(t, args, "--skip-git-repo-check")
	require.Contains(t, args, "--output-schema")

	stdinContent, err := os.ReadFile(stdinPath)
	require.NoError(t, err)
	require.Contains(t, string(stdinContent), "system prompt")
	require.Contains(t, string(stdinContent), "user prompt")
	require.True(t, strings.Contains(string(stdinContent), "JSON"))
}
