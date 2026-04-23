package swarm

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/bot"
)

type stubRunner struct {
	results []bot.StepResult
	err     error
	calls   int
}

func (s *stubRunner) StepDetailed(context.Context) (bot.StepResult, error) {
	s.calls++
	if s.err != nil {
		return bot.StepResult{}, s.err
	}
	if len(s.results) == 0 {
		return bot.StepResult{MinerID: "idle", Status: "idle"}, nil
	}
	result := s.results[0]
	s.results = s.results[1:]
	return result, nil
}

type barrierRunner struct {
	minerID  string
	started  chan<- string
	release  <-chan struct{}
	startedN *atomic.Int32
}

func (r *barrierRunner) StepDetailed(ctx context.Context) (bot.StepResult, error) {
	r.startedN.Add(1)
	r.started <- r.minerID
	select {
	case <-r.release:
		return bot.StepResult{
			MinerID:  r.minerID,
			Status:   "submitted",
			Acted:    true,
			Decision: bot.Decision{ActionType: "signal_none"},
		}, nil
	case <-ctx.Done():
		return bot.StepResult{}, ctx.Err()
	}
}

type stubStandingSource struct {
	standings []bot.Standing
	err       error
	calls     int
}

func (s *stubStandingSource) Standing(context.Context) (bot.Standing, error) {
	s.calls++
	if s.err != nil {
		return bot.Standing{}, s.err
	}
	if len(s.standings) == 0 {
		return bot.Standing{Status: "running"}, nil
	}
	standing := s.standings[0]
	s.standings = s.standings[1:]
	return standing, nil
}

func TestCoordinatorRunsUntilTournamentCompletes(t *testing.T) {
	observer := &stubStandingSource{
		standings: []bot.Standing{
			{Status: "running"},
			{Status: "running"},
			{Status: "completed", CompletedReason: "natural_finish", WinnerMinerID: "miner_02"},
		},
	}
	runnerOne := &stubRunner{
		results: []bot.StepResult{
			{MinerID: "miner_01", Status: "submitted", Acted: true, Decision: bot.Decision{ActionType: "signal_none"}},
			{MinerID: "miner_01", Status: "waiting_turn"},
		},
	}
	runnerTwo := &stubRunner{
		results: []bot.StepResult{
			{MinerID: "miner_02", Status: "submitted", Acted: true, Decision: bot.Decision{ActionType: "signal_none"}},
			{MinerID: "miner_02", Status: "submitted", Acted: true, Decision: bot.Decision{ActionType: "pass_probe"}},
		},
	}

	coordinator := NewCoordinator(CoordinatorConfig{
		Observer:      observer,
		Runners:       []Runner{runnerOne, runnerTwo},
		MaxSteps:      8,
		MaxIdleCycles: 2,
	})

	result, err := coordinator.Run(context.Background())
	require.NoError(t, err)
	require.True(t, result.Completed)
	require.Equal(t, "natural_finish", result.Standing.CompletedReason)
	require.Equal(t, "miner_02", result.Standing.WinnerMinerID)
	require.Len(t, result.Logs, 4)
	require.Equal(t, "submitted", result.Logs[0].Status)
	require.Equal(t, "signal_none", result.Logs[0].Decision.ActionType)
}

func TestCoordinatorFailsAfterIdleCycles(t *testing.T) {
	observer := &stubStandingSource{
		standings: []bot.Standing{
			{Status: "running"},
			{Status: "running"},
			{Status: "running"},
		},
	}
	runner := &stubRunner{
		results: []bot.StepResult{
			{MinerID: "miner_01", Status: "waiting_turn"},
			{MinerID: "miner_01", Status: "waiting_turn"},
			{MinerID: "miner_01", Status: "waiting_turn"},
		},
	}

	coordinator := NewCoordinator(CoordinatorConfig{
		Observer:      observer,
		Runners:       []Runner{runner},
		MaxSteps:      8,
		MaxIdleCycles: 2,
	})

	_, err := coordinator.Run(context.Background())
	require.Error(t, err)
	require.Contains(t, err.Error(), "idle")
}

func TestCoordinatorReturnsRunnerErrors(t *testing.T) {
	observer := &stubStandingSource{
		standings: []bot.Standing{{Status: "running"}},
	}
	runner := &stubRunner{err: errors.New("boom")}

	coordinator := NewCoordinator(CoordinatorConfig{
		Observer:      observer,
		Runners:       []Runner{runner},
		MaxSteps:      2,
		MaxIdleCycles: 1,
	})

	_, err := coordinator.Run(context.Background())
	require.Error(t, err)
	require.Contains(t, err.Error(), "boom")
}

func TestCoordinatorStepsRunnersConcurrently(t *testing.T) {
	started := make(chan string, 2)
	release := make(chan struct{})
	var startedN atomic.Int32

	go func() {
		<-started
		<-started
		close(release)
	}()

	observer := &stubStandingSource{
		standings: []bot.Standing{
			{Status: "running"},
			{Status: "completed", CompletedReason: "natural_finish", WinnerMinerID: "miner_02"},
		},
	}
	runnerOne := &barrierRunner{minerID: "miner_01", started: started, release: release, startedN: &startedN}
	runnerTwo := &barrierRunner{minerID: "miner_02", started: started, release: release, startedN: &startedN}

	coordinator := NewCoordinator(CoordinatorConfig{
		Observer:      observer,
		Runners:       []Runner{runnerOne, runnerTwo},
		MaxSteps:      4,
		MaxIdleCycles: 1,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	result, err := coordinator.Run(ctx)
	require.NoError(t, err)
	require.True(t, result.Completed)
	require.Equal(t, int32(2), startedN.Load())
	require.Len(t, result.Logs, 2)
}

func TestCoordinatorHonorsConfiguredConcurrencyLimit(t *testing.T) {
	started := make(chan string, 3)
	release := make(chan struct{})
	var startedN atomic.Int32

	first := &barrierRunner{
		minerID:  "miner_01",
		started:  started,
		release:  release,
		startedN: &startedN,
	}
	second := &barrierRunner{
		minerID:  "miner_02",
		started:  started,
		release:  release,
		startedN: &startedN,
	}
	third := &barrierRunner{
		minerID:  "miner_03",
		started:  started,
		release:  release,
		startedN: &startedN,
	}

	observer := &stubStandingSource{
		standings: []bot.Standing{
			{Status: "running"},
			{Status: "completed", CompletedReason: "natural_finish", WinnerMinerID: "miner_01"},
		},
	}
	coordinator := NewCoordinator(CoordinatorConfig{
		Observer:       observer,
		Runners:        []Runner{first, second, third},
		MaxSteps:       4,
		MaxIdleCycles:  1,
		MaxConcurrency: 1,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()

	observed := make(chan int32, 1)
	go func() {
		<-started
		time.Sleep(20 * time.Millisecond)
		observed <- startedN.Load()
		close(release)
	}()

	result, err := coordinator.Run(ctx)
	require.NoError(t, err)
	require.True(t, result.Completed)
	require.Equal(t, int32(1), <-observed)
	require.Equal(t, int32(3), startedN.Load())
	require.Len(t, result.Logs, 3)
}
