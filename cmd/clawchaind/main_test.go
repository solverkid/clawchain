package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/cosmos/cosmos-sdk/server"
	"github.com/spf13/cobra"
)

func TestAuthTxCommandsExist(t *testing.T) {
	repoRoot, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("resolve repo root: %v", err)
	}

	run := func(args ...string) string {
		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd := exec.Command("go", append([]string{"run", "./cmd/clawchaind"}, args...)...)
		cmd.Dir = repoRoot
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr
		if err := cmd.Run(); err != nil {
			t.Fatalf("command failed: %v\nstdout=%s\nstderr=%s", err, stdout.String(), stderr.String())
		}
		return stdout.String() + "\n" + stderr.String()
	}

	signHelp := run("tx", "sign", "--help")
	if !strings.Contains(signHelp, "Sign a transaction created with the --generate-only flag.") {
		t.Fatalf("missing tx sign command help: %s", signHelp)
	}

	broadcastHelp := run("tx", "broadcast", "--help")
	if !strings.Contains(broadcastHelp, "Broadcast transactions created with the --generate-only") {
		t.Fatalf("missing tx broadcast command help: %s", broadcastHelp)
	}
}

func TestBankSendCommandDoesNotPanic(t *testing.T) {
	keyringDir, err := filepath.Abs("../../deploy/testnet-artifacts/val1")
	if err != nil {
		t.Fatalf("resolve keyring dir: %v", err)
	}

	repoRoot, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("resolve repo root: %v", err)
	}

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd := exec.Command("go", "run", "./cmd/clawchaind",
		"tx",
		"bank",
		"send",
		"val1",
		"claw1q4akpa27mg6zv5zj4njmtvv0fhxyrtgega3564",
		"1uclaw",
		"--keyring-backend",
		"test",
		"--keyring-dir",
		keyringDir,
		"--chain-id",
		"clawchain-testnet-1",
		"--generate-only",
		"--note",
		"test-smoke",
		"--output",
		"json",
	)
	cmd.Dir = repoRoot
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		t.Fatalf("bank send subprocess failed: %v\nstdout=%s\nstderr=%s", err, stdout.String(), stderr.String())
	}

	combined := stdout.String() + "\n" + stderr.String()
	if strings.Contains(strings.ToLower(combined), "panic") {
		t.Fatalf("bank send emitted panic output: %s", combined)
	}
}

func TestSettlementAnchorBatchGenerateOnlyDoesNotPanic(t *testing.T) {
	keyringDir, err := filepath.Abs("../../deploy/testnet-artifacts/val1")
	if err != nil {
		t.Fatalf("resolve keyring dir: %v", err)
	}

	repoRoot, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("resolve repo root: %v", err)
	}

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd := exec.Command("go", "run", "./cmd/clawchaind",
		"tx",
		"settlement",
		"anchor-batch",
		"val1",
		"sb_test_01",
		"aj_test_01",
		"sha256:canonical",
		"sha256:payload",
		"--lane",
		"fast",
		"--schema-version",
		"settlement.v1",
		"--policy-bundle-version",
		"policy.v1",
		"--reward-window-ids-root",
		"sha256:windows",
		"--task-run-ids-root",
		"sha256:tasks",
		"--miner-reward-rows-root",
		"sha256:miners",
		"--window-end-at",
		"2026-04-10T03:15:00Z",
		"--total-reward-amount",
		"12345",
		"--keyring-backend",
		"test",
		"--keyring-dir",
		keyringDir,
		"--fees",
		"10uclaw",
		"--gas",
		"200000",
		"--offline",
		"--account-number",
		"0",
		"--sequence",
		"0",
		"--generate-only",
		"--output",
		"json",
	)
	cmd.Dir = repoRoot
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		t.Fatalf("settlement anchor-batch subprocess failed: %v\nstdout=%s\nstderr=%s", err, stdout.String(), stderr.String())
	}

	combined := stdout.String() + "\n" + stderr.String()
	if strings.Contains(strings.ToLower(combined), "panic") {
		t.Fatalf("settlement anchor-batch emitted panic output: %s", combined)
	}
	if !strings.Contains(combined, "/clawchain.settlement.v1.MsgAnchorSettlementBatch") {
		t.Fatalf("expected settlement msg type in output: %s", combined)
	}
}

func TestSettlementAnchorBatchGeneratedTxCanBeSigned(t *testing.T) {
	keyringDir, err := filepath.Abs("../../deploy/testnet-artifacts/val1")
	if err != nil {
		t.Fatalf("resolve keyring dir: %v", err)
	}

	repoRoot, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("resolve repo root: %v", err)
	}

	tempDir := t.TempDir()
	unsignedPath := filepath.Join(tempDir, "unsigned_tx.json")
	signedPath := filepath.Join(tempDir, "signed_tx.json")

	var generateStdout bytes.Buffer
	var generateStderr bytes.Buffer
	generateCmd := exec.Command("go", "run", "./cmd/clawchaind",
		"tx",
		"settlement",
		"anchor-batch",
		"val1",
		"sb_test_sign_01",
		"aj_test_sign_01",
		"sha256:canonical",
		"sha256:payload",
		"--lane",
		"fast",
		"--schema-version",
		"settlement.v1",
		"--policy-bundle-version",
		"policy.v1",
		"--reward-window-ids-root",
		"sha256:windows",
		"--task-run-ids-root",
		"sha256:tasks",
		"--miner-reward-rows-root",
		"sha256:miners",
		"--window-end-at",
		"2026-04-10T03:15:00Z",
		"--total-reward-amount",
		"12345",
		"--keyring-backend",
		"test",
		"--keyring-dir",
		keyringDir,
		"--fees",
		"10uclaw",
		"--gas",
		"200000",
		"--offline",
		"--account-number",
		"0",
		"--sequence",
		"0",
		"--generate-only",
		"--output",
		"json",
	)
	generateCmd.Dir = repoRoot
	generateCmd.Stdout = &generateStdout
	generateCmd.Stderr = &generateStderr

	if err := generateCmd.Run(); err != nil {
		t.Fatalf("settlement anchor-batch generate-only failed: %v\nstdout=%s\nstderr=%s", err, generateStdout.String(), generateStderr.String())
	}

	if err := os.WriteFile(unsignedPath, generateStdout.Bytes(), 0o600); err != nil {
		t.Fatalf("write unsigned tx: %v", err)
	}

	var signStdout bytes.Buffer
	var signStderr bytes.Buffer
	signCmd := exec.Command("go", "run", "./cmd/clawchaind",
		"tx",
		"sign",
		unsignedPath,
		"--from",
		"val1",
		"--chain-id",
		"clawchain-testnet-1",
		"--keyring-backend",
		"test",
		"--keyring-dir",
		keyringDir,
		"--offline",
		"--account-number",
		"0",
		"--sequence",
		"0",
		"--output",
		"json",
		"--output-document",
		signedPath,
	)
	signCmd.Dir = repoRoot
	signCmd.Stdout = &signStdout
	signCmd.Stderr = &signStderr

	if err := signCmd.Run(); err != nil {
		t.Fatalf("settlement anchor-batch sign failed: %v\nstdout=%s\nstderr=%s", err, signStdout.String(), signStderr.String())
	}

	signedBytes, err := os.ReadFile(signedPath)
	if err != nil {
		t.Fatalf("read signed tx: %v", err)
	}
	if !strings.Contains(string(signedBytes), "/clawchain.settlement.v1.MsgAnchorSettlementBatch") {
		t.Fatalf("expected signed tx to preserve settlement msg type: %s", string(signedBytes))
	}
}

func TestStartCommandPreRunLoadsMinimumGasPrices(t *testing.T) {
	homeDir, err := filepath.Abs("../../deploy/local-single-val1")
	if err != nil {
		t.Fatalf("resolve home dir: %v", err)
	}

	rootCmd := NewRootCmd()
	startCmd := findSubcommand(rootCmd, "start")
	if startCmd == nil {
		t.Fatal("start command not found")
	}

	var minGasPrices string
	startCmd.RunE = func(cmd *cobra.Command, args []string) error {
		minGasPrices = server.GetServerContextFromCmd(cmd).Viper.GetString(server.FlagMinGasPrices)
		return nil
	}

	rootCmd.SetArgs([]string{
		"start",
		"--home", homeDir,
		"--minimum-gas-prices", "0uclaw",
	})

	if err := rootCmd.Execute(); err != nil {
		t.Fatalf("execute start pre-run: %v", err)
	}
	if minGasPrices != "0uclaw" {
		t.Fatalf("expected minimum gas prices from start pre-run, got %q", minGasPrices)
	}
}

func findSubcommand(cmd *cobra.Command, name string) *cobra.Command {
	for _, child := range cmd.Commands() {
		if child.Name() == name {
			return child
		}
		if nested := findSubcommand(child, name); nested != nil {
			return nested
		}
	}
	return nil
}
