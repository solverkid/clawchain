package session

import (
	"errors"
	"sync"
	"time"

	"github.com/clawchain/clawchain/authadapter"
)

var ErrSessionNotFound = errors.New("poker mtt session not found")

type Manager struct {
	mu       sync.Mutex
	sessions map[string]authadapter.SessionAuthState
}

func NewManager() *Manager {
	return &Manager{sessions: make(map[string]authadapter.SessionAuthState)}
}

func (m *Manager) Attach(sessionID string, principal authadapter.Principal) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.sessions[sessionID] = authadapter.NewSessionAuthState(principal)
}

func (m *Manager) AuthorizeManualAction(sessionID string, now time.Time) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	state, ok := m.sessions[sessionID]
	if !ok {
		return ErrSessionNotFound
	}
	return state.AuthorizeManualAction(now)
}

func (m *Manager) Reconnect(sessionID string, fresh authadapter.Principal, now time.Time) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	state, ok := m.sessions[sessionID]
	if !ok {
		return ErrSessionNotFound
	}
	next, err := state.Reconnect(fresh, now)
	if err != nil {
		return err
	}
	m.sessions[sessionID] = next
	return nil
}

func (m *Manager) Revoke(sessionID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	state, ok := m.sessions[sessionID]
	if !ok {
		return ErrSessionNotFound
	}
	state.Revoked = true
	m.sessions[sessionID] = state
	return nil
}

func (m *Manager) RecordAcceptedAction(sessionID string, actionID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	state, ok := m.sessions[sessionID]
	if !ok {
		return ErrSessionNotFound
	}
	state.RecordAcceptedAction(actionID)
	m.sessions[sessionID] = state
	return nil
}

func (m *Manager) HasAcceptedAction(sessionID string, actionID string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	state, ok := m.sessions[sessionID]
	if !ok {
		return false
	}
	return state.HasAcceptedAction(actionID)
}
