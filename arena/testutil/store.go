package testutil

import (
	"context"
	"sync"

	"github.com/clawchain/clawchain/arena/model"
)

type ArenaStore struct {
	mu             sync.Mutex
	events         []model.EventLogEntry
	actionRecords  []model.ActionRecord
	deadlines      map[string]model.ActionDeadline
	tableSnapshots map[string]model.TableSnapshot
	handSnapshots  map[string]model.HandSnapshot
}

func NewArenaStore() *ArenaStore {
	return &ArenaStore{
		deadlines:      make(map[string]model.ActionDeadline),
		tableSnapshots: make(map[string]model.TableSnapshot),
		handSnapshots:  make(map[string]model.HandSnapshot),
	}
}

func (s *ArenaStore) AppendEvents(_ context.Context, events []model.EventLogEntry) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = append(s.events, events...)
	return nil
}

func (s *ArenaStore) AppendActionRecords(_ context.Context, actions []model.ActionRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.actionRecords = append(s.actionRecords, actions...)
	return nil
}

func (s *ArenaStore) SaveTableSnapshot(_ context.Context, snapshot model.TableSnapshot) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.tableSnapshots[snapshot.TableID] = snapshot
	return nil
}

func (s *ArenaStore) SaveHandSnapshot(_ context.Context, snapshot model.HandSnapshot) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.handSnapshots[snapshot.HandID] = snapshot
	return nil
}

func (s *ArenaStore) UpsertActionDeadline(_ context.Context, deadline model.ActionDeadline) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.deadlines[deadline.PhaseID] = deadline
	return nil
}

func (s *ArenaStore) HasOpenDeadline(phaseID string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	deadline, ok := s.deadlines[phaseID]
	return ok && deadline.Status == "open"
}

func (s *ArenaStore) HasTableSnapshot(tableID string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, ok := s.tableSnapshots[tableID]
	return ok
}
