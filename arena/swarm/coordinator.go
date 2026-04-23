package swarm

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/clawchain/clawchain/arena/bot"
)

type Runner interface {
	StepDetailed(ctx context.Context) (bot.StepResult, error)
}

type StandingSource interface {
	Standing(ctx context.Context) (bot.Standing, error)
}

type CoordinatorConfig struct {
	Observer       StandingSource
	Runners        []Runner
	MaxSteps       int
	MaxIdleCycles  int
	MaxConcurrency int
	CycleDelay     time.Duration
	OnLog          func(ActionLog)
}

type ActionLog struct {
	Cycle        int
	MinerID      string
	TableID      string
	SeatNo       int
	StateSeq     int64
	CurrentPhase string
	ActingSeatNo int
	Status       string
	Acted        bool
	Decision     bot.Decision
}

type Result struct {
	Completed bool
	Standing  bot.Standing
	Steps     int
	Logs      []ActionLog
}

type Coordinator struct {
	observer       StandingSource
	runners        []Runner
	maxSteps       int
	maxIdleCycles  int
	maxConcurrency int
	cycleDelay     time.Duration
	onLog          func(ActionLog)
}

func NewCoordinator(cfg CoordinatorConfig) *Coordinator {
	maxSteps := cfg.MaxSteps
	if maxSteps <= 0 {
		maxSteps = 10000
	}
	maxIdleCycles := cfg.MaxIdleCycles
	if maxIdleCycles <= 0 {
		maxIdleCycles = 25
	}
	maxConcurrency := cfg.MaxConcurrency
	if maxConcurrency <= 0 || maxConcurrency > len(cfg.Runners) {
		maxConcurrency = len(cfg.Runners)
	}

	return &Coordinator{
		observer:       cfg.Observer,
		runners:        cfg.Runners,
		maxSteps:       maxSteps,
		maxIdleCycles:  maxIdleCycles,
		maxConcurrency: maxConcurrency,
		cycleDelay:     cfg.CycleDelay,
		onLog:          cfg.OnLog,
	}
}

func (c *Coordinator) Run(ctx context.Context) (Result, error) {
	var result Result
	if c.observer == nil {
		return result, fmt.Errorf("swarm coordinator requires observer")
	}
	if len(c.runners) == 0 {
		return result, fmt.Errorf("swarm coordinator requires at least one runner")
	}

	idleCycles := 0
	for cycle := 0; cycle < c.maxSteps; cycle++ {
		standing, err := c.observer.Standing(ctx)
		if err != nil {
			return result, err
		}
		result.Standing = standing
		result.Steps = cycle
		if standing.Status == "completed" || standing.Status == "voided" {
			result.Completed = standing.Status == "completed"
			return result, nil
		}

		progressed := false
		steps := make([]bot.StepResult, len(c.runners))
		errs := make([]error, len(c.runners))
		sema := make(chan struct{}, c.maxConcurrency)
		var wg sync.WaitGroup
		wg.Add(len(c.runners))
		for idx, runner := range c.runners {
			go func(idx int, runner Runner) {
				defer wg.Done()
				sema <- struct{}{}
				defer func() {
					<-sema
				}()
				steps[idx], errs[idx] = runner.StepDetailed(ctx)
			}(idx, runner)
		}
		wg.Wait()

		for idx := range c.runners {
			if errs[idx] != nil {
				return result, errs[idx]
			}
			step := steps[idx]
			actionLog := ActionLog{
				Cycle:        cycle,
				MinerID:      step.MinerID,
				TableID:      step.TableID,
				SeatNo:       step.SeatNo,
				StateSeq:     step.StateSeq,
				CurrentPhase: step.CurrentPhase,
				ActingSeatNo: step.ActingSeatNo,
				Status:       step.Status,
				Acted:        step.Acted,
				Decision:     step.Decision,
			}
			result.Logs = append(result.Logs, actionLog)
			if c.onLog != nil {
				c.onLog(actionLog)
			}
			progressed = progressed || step.Acted
		}

		if progressed {
			idleCycles = 0
		} else {
			idleCycles++
			if idleCycles > c.maxIdleCycles {
				return result, fmt.Errorf("swarm idle for %d cycles before tournament completion", idleCycles)
			}
		}
		if c.cycleDelay > 0 {
			timer := time.NewTimer(c.cycleDelay)
			select {
			case <-ctx.Done():
				timer.Stop()
				return result, ctx.Err()
			case <-timer.C:
			}
		}
	}

	return result, fmt.Errorf("swarm exceeded max steps %d without tournament completion", c.maxSteps)
}
