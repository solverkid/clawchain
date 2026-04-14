package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

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

	assignment, ok := s.lookupSeatAssignment(r, request.TournamentID, request.MinerID)
	if !ok {
		http.NotFound(w, r)
		return true
	}
	if assignment.ReadOnly {
		writeJSON(w, http.StatusConflict, map[string]string{"error": "read_only_assignment"})
		return true
	}
	if strings.TrimSpace(request.SessionID) == "" {
		writeJSON(w, http.StatusConflict, map[string]string{"error": "session_required"})
		return true
	}
	if !s.deps.Sessions.Owns(request.TournamentID, request.MinerID, request.SessionID) {
		writeJSON(w, http.StatusConflict, map[string]string{"error": "session_mismatch"})
		return true
	}
	if request.TableID != "" && request.TableID != assignment.TableID {
		writeJSON(w, http.StatusConflict, map[string]string{"error": "stale_table_assignment"})
		return true
	}
	if request.SeatNo != 0 && request.SeatNo != assignment.SeatNo {
		writeJSON(w, http.StatusConflict, map[string]string{"error": "stale_seat_assignment"})
		return true
	}
	request.TableID = assignment.TableID
	request.SeatNo = assignment.SeatNo

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

func (s *Server) lookupSeatAssignment(r *http.Request, tournamentID, minerID string) (SeatAssignment, bool) {
	if s.deps.Arena != nil {
		return s.deps.Arena.SeatAssignment(r.Context(), tournamentID, minerID)
	}
	assignments, ok := s.deps.SeatAssignments[tournamentID]
	if !ok {
		return SeatAssignment{}, false
	}
	assignment, ok := assignments[minerID]
	return assignment, ok
}
