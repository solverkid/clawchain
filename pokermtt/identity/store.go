package identity

import (
	"context"
	"sync"
	"time"
)

type Store interface {
	Bind(ctx context.Context, binding Binding) (Binding, error)
	ByUserID(ctx context.Context, userID string) (Binding, bool, error)
	ByMinerAddress(ctx context.Context, minerAddress string) (Binding, bool, error)
}

type MemoryStore struct {
	mu      sync.Mutex
	byUser  map[string]Binding
	byMiner map[string]Binding
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		byUser:  make(map[string]Binding),
		byMiner: make(map[string]Binding),
	}
}

func (s *MemoryStore) Bind(ctx context.Context, binding Binding) (Binding, error) {
	if ctx != nil {
		if err := ctx.Err(); err != nil {
			return Binding{}, err
		}
	}

	normalized, err := normalizeBinding(binding)
	if err != nil {
		return Binding{}, err
	}
	if normalized.CreatedAt.IsZero() {
		normalized.CreatedAt = time.Now().UTC()
	}
	if normalized.UpdatedAt.IsZero() {
		normalized.UpdatedAt = normalized.CreatedAt
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if existing, ok := s.byUser[normalized.UserID]; ok {
		if existing.MinerAddress == normalized.MinerAddress {
			return existing, nil
		}
		return Binding{}, ErrBindingConflict
	}
	if existing, ok := s.byMiner[normalized.MinerAddress]; ok {
		if existing.UserID == normalized.UserID {
			return existing, nil
		}
		return Binding{}, ErrBindingConflict
	}

	s.byUser[normalized.UserID] = normalized
	s.byMiner[normalized.MinerAddress] = normalized
	return normalized, nil
}

func (s *MemoryStore) ByUserID(ctx context.Context, userID string) (Binding, bool, error) {
	if ctx != nil {
		if err := ctx.Err(); err != nil {
			return Binding{}, false, err
		}
	}

	normalized, err := NormalizeUserID(userID)
	if err != nil {
		return Binding{}, false, err
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	binding, ok := s.byUser[normalized]
	return binding, ok, nil
}

func (s *MemoryStore) ByMinerAddress(ctx context.Context, minerAddress string) (Binding, bool, error) {
	if ctx != nil {
		if err := ctx.Err(); err != nil {
			return Binding{}, false, err
		}
	}

	normalized, err := NormalizeMinerAddress(minerAddress)
	if err != nil {
		return Binding{}, false, err
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	binding, ok := s.byMiner[normalized]
	return binding, ok, nil
}
