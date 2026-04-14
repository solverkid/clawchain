package httpapi

import (
	"encoding/json"
	"net/http"
)

func (s *Server) registerSessionRoutes() {
}

func (s *Server) handleTournamentSessionRoutes(w http.ResponseWriter, r *http.Request) bool {
	parts := splitPath(r.URL.Path)
	if len(parts) != 5 || parts[0] != "v1" || parts[1] != "tournaments" || parts[3] != "sessions" || parts[4] != "reconnect" || r.Method != http.MethodPost {
		return false
	}

	tournamentID := parts[2]
	var payload struct {
		MinerID   string `json:"miner_id"`
		SessionID string `json:"session_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
		return true
	}

	s.deps.Sessions.Attach(tournamentID, payload.MinerID, payload.SessionID)
	if s.deps.Arena != nil {
		if assignment, ok := s.deps.Arena.Reconnect(r.Context(), tournamentID, payload.MinerID, payload.SessionID); ok {
			writeJSON(w, http.StatusOK, assignment)
			return true
		}
		http.NotFound(w, r)
		return true
	}
	assignment := s.deps.SeatAssignments[tournamentID][payload.MinerID]
	assignment.SessionID = payload.SessionID
	s.deps.SeatAssignments[tournamentID][payload.MinerID] = assignment

	writeJSON(w, http.StatusOK, assignment)
	return true
}
