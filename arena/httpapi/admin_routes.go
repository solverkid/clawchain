package httpapi

import (
	"encoding/json"
	"net/http"
)

func (s *Server) registerAdminRoutes() {
	s.mux.HandleFunc("/v1/admin/arena/", s.handleAdminRoutes)
}

func (s *Server) handleAdminRoutes(w http.ResponseWriter, r *http.Request) {
	if s.deps.Arena == nil {
		if r.Method != http.MethodPost {
			http.NotFound(w, r)
			return
		}
		writeJSON(w, http.StatusAccepted, map[string]string{"status": "accepted"})
		return
	}

	parts := splitPath(r.URL.Path)
	switch {
	case r.Method == http.MethodPost && len(parts) == 4 && parts[0] == "v1" && parts[1] == "admin" && parts[2] == "arena" && parts[3] == "waves":
		var payload CreateWaveRequest
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
			return
		}
		response, err := s.deps.Arena.CreateWave(r.Context(), payload)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusCreated, response)
	case r.Method == http.MethodPost && len(parts) == 6 && parts[0] == "v1" && parts[1] == "admin" && parts[2] == "arena" && parts[3] == "waves" && parts[5] == "lock":
		response, err := s.deps.Arena.LockWave(r.Context(), parts[4])
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, response)
	case r.Method == http.MethodPost && len(parts) == 6 && parts[0] == "v1" && parts[1] == "admin" && parts[2] == "arena" && parts[3] == "waves" && parts[5] == "publish-seats":
		response, err := s.deps.Arena.PublishSeats(r.Context(), parts[4])
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, response)
	case r.Method == http.MethodPost && len(parts) == 6 && parts[0] == "v1" && parts[1] == "admin" && parts[2] == "arena" && parts[3] == "waves" && parts[5] == "force-remove":
		var payload struct {
			MinerID string `json:"miner_id"`
		}
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
			return
		}
		response, err := s.deps.Arena.ForceRemoveBeforeStart(r.Context(), parts[4], payload.MinerID)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, response)
	case r.Method == http.MethodPost && len(parts) == 6 && parts[0] == "v1" && parts[1] == "admin" && parts[2] == "arena" && parts[3] == "tournaments" && parts[5] == "time-cap":
		response, err := s.deps.Arena.ArmTimeCap(r.Context(), parts[4])
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, response)
	case r.Method == http.MethodPost && len(parts) == 6 && parts[0] == "v1" && parts[1] == "admin" && parts[2] == "arena" && parts[3] == "tournaments" && parts[5] == "void":
		var payload struct {
			Reason string `json:"reason"`
		}
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
			return
		}
		response, err := s.deps.Arena.VoidTournament(r.Context(), parts[4], payload.Reason)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, response)
	default:
		http.NotFound(w, r)
	}
}
