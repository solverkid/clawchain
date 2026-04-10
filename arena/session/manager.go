package session

import "sync"

type Session struct {
	MinerID   string `json:"miner_id"`
	SessionID string `json:"session_id"`
}

type Manager struct {
	mu     sync.Mutex
	active map[string]Session
}

func NewManager() *Manager {
	return &Manager{
		active: make(map[string]Session),
	}
}

func (m *Manager) Attach(minerID, sessionID string) Session {
	m.mu.Lock()
	defer m.mu.Unlock()

	session := Session{
		MinerID:   minerID,
		SessionID: sessionID,
	}
	m.active[minerID] = session
	return session
}

func (m *Manager) Active(minerID string) Session {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.active[minerID]
}
