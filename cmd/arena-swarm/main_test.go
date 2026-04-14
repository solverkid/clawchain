package main

import (
	"bytes"
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
