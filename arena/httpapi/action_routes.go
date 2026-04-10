package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/clawchain/clawchain/arena/gateway"
)

func (s *Server) registerActionRoutes() {
}

func (s *Server) handleTournamentActionRoutes(w http.ResponseWriter, r *http.Request) bool {
	parts := splitPath(r.URL.Path)
	if len(parts) != 4 || parts[0] != "v1" || parts[1] != "tournaments" || parts[3] != "actions" || r.Method != http.MethodPost {
		return false
	}

	if s.deps.Gateway == nil {
		writeJSON(w, http.StatusNotImplemented, map[string]string{"error": "gateway unavailable"})
		return true
	}

	var request gateway.SubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
		return true
	}
	request.TournamentID = parts[2]

	response, err := s.deps.Gateway.Submit(r.Context(), request)
	if err != nil {
		switch {
		case errors.Is(err, gateway.ErrInvalidSignature):
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": err.Error()})
		case errors.Is(err, gateway.ErrStateSeqMismatch):
			writeJSON(w, http.StatusConflict, map[string]string{"error": err.Error()})
		default:
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		}
		return true
	}

	writeJSON(w, http.StatusOK, response)
	return true
}
