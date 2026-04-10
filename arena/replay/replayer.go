package replay

type Result struct {
	Err              error
	ParityOK         bool
	FinalDisposition string
}

type Replayer struct {
	expectedFinalHashes map[string]string
	computedFinalHashes map[string]string
}

func NewReplayer(expectedFinalHashes, computedFinalHashes map[string]string) *Replayer {
	return &Replayer{
		expectedFinalHashes: expectedFinalHashes,
		computedFinalHashes: computedFinalHashes,
	}
}

func (r *Replayer) ReplayCorrupted(tournamentID string) Result {
	expected := r.expectedFinalHashes[tournamentID]
	computed := r.computedFinalHashes[tournamentID]

	if expected == computed {
		return Result{
			ParityOK:         true,
			FinalDisposition: "ok",
		}
	}

	return Result{
		ParityOK:         false,
		FinalDisposition: "integrity_failure",
	}
}
