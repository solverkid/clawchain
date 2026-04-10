package httpapi

import (
	"encoding/json"
	"net/http"
)

func (s *Server) registerLobbyRoutes() {
	s.mux.HandleFunc("/v1/arena/waves/active", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{"waves": keys(s.deps.WaveRegistrations)})
	})

	s.mux.HandleFunc("/v1/arena/waves/", s.handleWaveRoutes)
}

func (s *Server) handleWaveRoutes(w http.ResponseWriter, r *http.Request) {
	parts := splitPath(r.URL.Path)
	if len(parts) < 5 {
		http.NotFound(w, r)
		return
	}

	waveID := parts[3]
	switch {
	case r.Method == http.MethodPost && len(parts) == 5 && parts[4] == "register":
		var payload struct {
			MinerID string `json:"miner_id"`
		}
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
			return
		}
		if s.deps.WaveRegistrations[waveID] == nil {
			s.deps.WaveRegistrations[waveID] = map[string]bool{}
		}
		s.deps.WaveRegistrations[waveID][payload.MinerID] = true
		writeJSON(w, http.StatusOK, map[string]any{"wave_id": waveID, "miner_id": payload.MinerID, "registered": true})
	case r.Method == http.MethodDelete && len(parts) == 6 && parts[4] == "registration":
		minerID := parts[5]
		if registrations, ok := s.deps.WaveRegistrations[waveID]; ok {
			delete(registrations, minerID)
		}
		writeJSON(w, http.StatusOK, map[string]any{"wave_id": waveID, "miner_id": minerID, "registered": false})
	default:
		http.NotFound(w, r)
	}
}

func keys(values map[string]map[string]bool) []string {
	result := make([]string, 0, len(values))
	for key := range values {
		result = append(result, key)
	}
	return result
}
