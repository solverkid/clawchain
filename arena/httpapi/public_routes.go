package httpapi

import "net/http"

func (s *Server) registerPublicRoutes() {
	s.mux.HandleFunc("/v1/tournaments/", s.handleTournamentRoutes)
}

func (s *Server) handleTournamentRoutes(w http.ResponseWriter, r *http.Request) {
	if handled := s.handleTournamentActionRoutes(w, r); handled {
		return
	}
	if handled := s.handleTournamentSessionRoutes(w, r); handled {
		return
	}
	s.handleTournamentReadRoutes(w, r)
}

func (s *Server) handleTournamentReadRoutes(w http.ResponseWriter, r *http.Request) {
	parts := splitPath(r.URL.Path)
	if len(parts) < 4 || parts[0] != "v1" || parts[1] != "tournaments" {
		http.NotFound(w, r)
		return
	}

	tournamentID := parts[2]
	switch {
	case r.Method == http.MethodGet && len(parts) == 4 && parts[3] == "standing":
		if s.deps.Arena != nil {
			if view, ok := s.deps.Arena.Standing(r.Context(), tournamentID); ok {
				writeJSON(w, http.StatusOK, view)
				return
			}
			http.NotFound(w, r)
			return
		}
		writeJSON(w, http.StatusOK, s.deps.StandingView[tournamentID])
	case r.Method == http.MethodGet && len(parts) == 5 && parts[3] == "live-table":
		if s.deps.Arena != nil {
			if view, ok := s.deps.Arena.LiveTable(r.Context(), tournamentID, parts[4]); ok {
				writeJSON(w, http.StatusOK, view)
				return
			}
			http.NotFound(w, r)
			return
		}
		writeJSON(w, http.StatusOK, s.deps.LiveTableView[tournamentID][parts[4]])
	case r.Method == http.MethodGet && len(parts) == 5 && parts[3] == "seat-assignment":
		if s.deps.Arena != nil {
			if assignment, ok := s.deps.Arena.SeatAssignment(r.Context(), tournamentID, parts[4]); ok {
				writeJSON(w, http.StatusOK, assignment)
				return
			}
			http.NotFound(w, r)
			return
		}
		writeJSON(w, http.StatusOK, s.deps.SeatAssignments[tournamentID][parts[4]])
	default:
		http.NotFound(w, r)
	}
}
