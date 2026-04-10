package httpapi

import "net/http"

func (s *Server) registerAdminRoutes() {
	s.mux.HandleFunc("/v1/admin/arena/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.NotFound(w, r)
			return
		}
		writeJSON(w, http.StatusAccepted, map[string]string{"status": "accepted"})
	})
}
