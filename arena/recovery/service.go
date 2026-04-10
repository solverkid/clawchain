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

type Service struct {
	store             Store
	now               func() time.Time
	syntheticTimeouts map[string]struct{}
}

func NewService(store Store, now func() time.Time) *Service {
	if now == nil {
		now = time.Now().UTC
	}

	return &Service{
		store:             store,
		now:               now,
		syntheticTimeouts: make(map[string]struct{}),
	}
}

func (s *Service) RecoverTournament(_ context.Context, tournamentID string) error {
	_, _ = s.store.Snapshots[tournamentID]

	for _, deadline := range s.store.Deadlines {
		if deadline.TournamentID != tournamentID {
			continue
		}
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
