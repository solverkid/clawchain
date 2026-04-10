package replay

import "testing"

import "github.com/stretchr/testify/require"

func TestReplayParityMismatchMarksIntegrityFailure(t *testing.T) {
	rep := newReplayerForTest()

	result := rep.ReplayCorrupted("tour_1")
	require.NoError(t, result.Err)
	require.False(t, result.ParityOK)
	require.Equal(t, "integrity_failure", result.FinalDisposition)
}

func newReplayerForTest() *Replayer {
	return NewReplayer(map[string]string{
		"tour_1": "expected-final-hash",
	}, map[string]string{
		"tour_1": "corrupted-final-hash",
	})
}
