package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	"github.com/clawchain/clawchain/arena/gateway"
	"github.com/clawchain/clawchain/arena/session"
)

type ActionGateway interface {
	Submit(ctx context.Context, req gateway.SubmitRequest) (gateway.SubmitResponse, error)
}

type SeatAssignment struct {
	TableID   string `json:"table_id"`
	StateSeq  int64  `json:"state_seq"`
	ReadOnly  bool   `json:"read_only"`
	SessionID string `json:"session_id,omitempty"`
}

type Dependencies struct {
	Gateway           ActionGateway
	Sessions          *session.Manager
	WaveRegistrations map[string]map[string]bool
	StandingView      map[string]map[string]any
	LiveTableView     map[string]map[string]map[string]any
	SeatAssignments   map[string]map[string]SeatAssignment
}

type Server struct {
	deps Dependencies
	mux  *http.ServeMux
}

func NewServer(deps Dependencies) *Server {
	if deps.Sessions == nil {
		deps.Sessions = session.NewManager()
	}
	if deps.WaveRegistrations == nil {
		deps.WaveRegistrations = map[string]map[string]bool{}
	}
	if deps.StandingView == nil {
		deps.StandingView = map[string]map[string]any{}
	}
	if deps.LiveTableView == nil {
		deps.LiveTableView = map[string]map[string]map[string]any{}
	}
	if deps.SeatAssignments == nil {
		deps.SeatAssignments = map[string]map[string]SeatAssignment{}
	}

	server := &Server{
		deps: deps,
		mux:  http.NewServeMux(),
	}
	server.registerLobbyRoutes()
	server.registerPublicRoutes()
	server.registerActionRoutes()
	server.registerSessionRoutes()
	server.registerAdminRoutes()
	server.mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	server.mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	return server
}

func (s *Server) Handler() http.Handler {
	return s.mux
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func splitPath(path string) []string {
	return strings.Split(strings.Trim(path, "/"), "/")
}
