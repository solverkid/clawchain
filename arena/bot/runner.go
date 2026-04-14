package bot

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync/atomic"
)

type RunnerConfig struct {
	BaseURL      string
	TournamentID string
	MinerID      string
	HTTPClient   *http.Client
	Policy       Policy
}

type Runner struct {
	client     *Client
	policy     Policy
	sessionID  string
	requestSeq int64
}

type StepResult struct {
	MinerID      string
	TableID      string
	SeatNo       int
	StateSeq     int64
	CurrentPhase string
	ActingSeatNo int
	Status       string
	Acted        bool
	Decision     Decision
}

func NewRunner(cfg RunnerConfig) *Runner {
	policy := cfg.Policy
	if policy == nil {
		policy = HeuristicPolicy{}
	}

	return &Runner{
		client:    NewClientWithHTTP(cfg.BaseURL, cfg.TournamentID, cfg.MinerID, cfg.HTTPClient),
		policy:    policy,
		sessionID: fmt.Sprintf("arena-bot-session-%s", cfg.MinerID),
	}
}

func (r *Runner) Client() *Client {
	return r.client
}

func (r *Runner) MinerID() string {
	return r.client.minerID
}

func (r *Runner) Step(ctx context.Context) (bool, error) {
	result, err := r.StepDetailed(ctx)
	return result.Acted, err
}

func (r *Runner) StepDetailed(ctx context.Context) (StepResult, error) {
	result := StepResult{
		MinerID: r.client.minerID,
		Status:  "idle",
	}

	assignment, err := r.client.SeatAssignment(ctx)
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			result.Status = "no_assignment"
			return result, nil
		}
		return result, err
	}
	result.TableID = assignment.TableID
	result.SeatNo = assignment.SeatNo
	result.StateSeq = assignment.StateSeq
	if assignment.TableID == "" || assignment.SeatNo == 0 {
		result.Status = "unseated"
		return result, nil
	}
	if assignment.SessionID != r.sessionID {
		assignment, err = r.client.Reconnect(ctx, r.sessionID)
		if err != nil {
			if errors.Is(err, ErrNotFound) {
				result.Status = "no_assignment"
				return result, nil
			}
			return result, err
		}
		result.TableID = assignment.TableID
		result.SeatNo = assignment.SeatNo
		result.StateSeq = assignment.StateSeq
	}

	view, err := r.client.LiveTable(ctx, assignment.TableID)
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			result.Status = "no_table"
			return result, nil
		}
		return result, err
	}
	result.CurrentPhase = view.CurrentPhase
	result.ActingSeatNo = view.ActingSeatNo

	if assignment.SeatNo != view.ActingSeatNo {
		result.Status = "waiting_turn"
		return result, nil
	}

	decision, ok, err := r.policy.Decide(assignment, view)
	if err != nil {
		return result, err
	}
	if !ok {
		result.Status = "decision_skipped"
		return result, nil
	}
	result.Decision = decision

	requestID := fmt.Sprintf(
		"arena-bot-%s-%06d-%d",
		r.client.minerID,
		atomic.AddInt64(&r.requestSeq, 1),
		assignment.StateSeq,
	)
	if err := r.client.SubmitAction(ctx, assignment, decision, requestID); err != nil {
		if errors.Is(err, ErrConflict) || errors.Is(err, ErrNotFound) {
			result.Status = "stale_state"
			return result, nil
		}
		return result, err
	}
	result.Status = "submitted"
	result.Acted = true
	return result, nil
}
