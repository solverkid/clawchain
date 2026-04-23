package main

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestRunMainRequiresBaseURL(t *testing.T) {
	var stdout bytes.Buffer
	var stderr bytes.Buffer

	err := runMain([]string{"--miners", "2"}, &stdout, &stderr)
	require.Error(t, err)
	require.Contains(t, err.Error(), "base-url")
}

func TestRunMainShowsHelp(t *testing.T) {
	var stdout bytes.Buffer
	var stderr bytes.Buffer

	err := runMain([]string{"--help"}, &stdout, &stderr)
	require.NoError(t, err)
	require.Contains(t, stdout.String(), "arena-swarm")
}

func TestLoadMinerIDsFromFileSupportsManifestObjects(t *testing.T) {
	path := filepath.Join(t.TempDir(), "miners.json")
	require.NoError(t, os.WriteFile(path, []byte(`{"miners":[{"address":"claw1alpha"},{"miner_id":"claw1beta"}]}`), 0o600))

	ids, err := loadMinerIDsFromFile(path)
	require.NoError(t, err)
	require.Equal(t, []string{"claw1alpha", "claw1beta"}, ids)
}
