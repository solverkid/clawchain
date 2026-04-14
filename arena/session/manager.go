package session

import "sync"

type Session struct {
	TournamentID string `json:"tournament_id,omitempty"`
	MinerID      string `json:"miner_id"`
	SessionID    string `json:"session_id"`
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

func (m *Manager) Attach(tournamentID, minerID, sessionID string) Session {
	m.mu.Lock()
	defer m.mu.Unlock()

	session := Session{
		TournamentID: tournamentID,
		MinerID:      minerID,
		SessionID:    sessionID,
	}
	m.active[key(tournamentID, minerID)] = session
	return session
}

func (m *Manager) Active(tournamentID, minerID string) Session {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.active[key(tournamentID, minerID)]
}

func (m *Manager) Owns(tournamentID, minerID, sessionID string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()

	current, ok := m.active[key(tournamentID, minerID)]
	return ok && current.SessionID != "" && current.SessionID == sessionID
}

func key(tournamentID, minerID string) string {
	return tournamentID + ":" + minerID
}
