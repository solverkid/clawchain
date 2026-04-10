package recovery

import (
	"context"
	"time"

	"github.com/clawchain/clawchain/arena/model"
)

type Store struct {
	Snapshots map[string]model.TableSnapshot
	Deadlines []model.ActionDeadline
}

type deadlineLoader interface {
	LoadLatestTableSnapshots(ctx context.Context, tournamentID string) ([]model.TableSnapshot, error)
	ListActionDeadlinesByTournament(ctx context.Context, tournamentID string) ([]model.ActionDeadline, error)
}

type staticLoader struct {
	store Store
}

func (l staticLoader) LoadLatestTableSnapshots(_ context.Context, tournamentID string) ([]model.TableSnapshot, error) {
	snapshot, ok := l.store.Snapshots[tournamentID]
	if !ok {
		return nil, nil
	}
	return []model.TableSnapshot{snapshot}, nil
}

func (l staticLoader) ListActionDeadlinesByTournament(_ context.Context, tournamentID string) ([]model.ActionDeadline, error) {
	deadlines := make([]model.ActionDeadline, 0, len(l.store.Deadlines))
	for _, deadline := range l.store.Deadlines {
		if deadline.TournamentID != tournamentID {
			continue
		}
		deadlines = append(deadlines, deadline)
	}
	return deadlines, nil
}

type Service struct {
	loader            deadlineLoader
	now               func() time.Time
	syntheticTimeouts map[string]struct{}
}

func NewService(store Store, now func() time.Time) *Service {
	return NewRepositoryService(staticLoader{store: store}, now)
}

func NewRepositoryService(loader deadlineLoader, now func() time.Time) *Service {
	if now == nil {
		now = time.Now().UTC
	}

	return &Service{
		loader:            loader,
		now:               now,
		syntheticTimeouts: make(map[string]struct{}),
	}
}

func (s *Service) RecoverTournament(ctx context.Context, tournamentID string) error {
	if ctx == nil {
		ctx = context.Background()
	}

	if _, err := s.loader.LoadLatestTableSnapshots(ctx, tournamentID); err != nil {
		return err
	}

	deadlines, err := s.loader.ListActionDeadlinesByTournament(ctx, tournamentID)
	if err != nil {
		return err
	}

	for _, deadline := range deadlines {
		if deadline.Status != "open" {
			continue
		}
		if deadline.DeadlineAt.After(s.now()) {
			continue
		}
		s.syntheticTimeouts[deadline.DeadlineID] = struct{}{}
	}

	return nil
}

func (s *Service) SawSyntheticTimeout(deadlineID string) bool {
	_, ok := s.syntheticTimeouts[deadlineID]
	return ok
}
