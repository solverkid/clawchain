package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/clawchain/clawchain/arena/gateway"
	"github.com/clawchain/clawchain/arena/session"
)

type ActionGateway interface {
	Submit(ctx context.Context, req gateway.SubmitRequest) (gateway.SubmitResponse, error)
}

type SeatAssignment struct {
	TableID   string `json:"table_id"`
	SeatNo    int    `json:"seat_no,omitempty"`
	StateSeq  int64  `json:"state_seq"`
	ReadOnly  bool   `json:"read_only"`
	SessionID string `json:"session_id,omitempty"`
}

type CreateWaveRequest struct {
	WaveID              string    `json:"wave_id"`
	Mode                string    `json:"mode"`
	RegistrationOpenAt  time.Time `json:"registration_open_at"`
	RegistrationCloseAt time.Time `json:"registration_close_at"`
	ScheduledStartAt    time.Time `json:"scheduled_start_at"`
}

type WaveMutationResponse struct {
	WaveID          string `json:"wave_id"`
	TournamentID    string `json:"tournament_id,omitempty"`
	RatedOrPractice string `json:"rated_or_practice,omitempty"`
	NoMultiplier    bool   `json:"no_multiplier,omitempty"`
	SeatsPublished  bool   `json:"seats_published,omitempty"`
	RegisteredCount int    `json:"registered_count,omitempty"`
}

type ArenaService interface {
	ActiveWaves(ctx context.Context) []string
	CreateWave(ctx context.Context, req CreateWaveRequest) (WaveMutationResponse, error)
	RegisterMiner(ctx context.Context, waveID, minerID string) error
	UnregisterMiner(ctx context.Context, waveID, minerID string) error
	LockWave(ctx context.Context, waveID string) (WaveMutationResponse, error)
	PublishSeats(ctx context.Context, waveID string) (WaveMutationResponse, error)
	ForceRemoveBeforeStart(ctx context.Context, waveID, minerID string) (map[string]any, error)
	Disqualify(ctx context.Context, tournamentID, minerID, reason string) (map[string]any, error)
	ArmTimeCap(ctx context.Context, tournamentID string) (map[string]any, error)
	VoidTournament(ctx context.Context, tournamentID, reason string) (map[string]any, error)
	Standing(ctx context.Context, tournamentID string) (map[string]any, bool)
	LiveTable(ctx context.Context, tournamentID, tableID string) (map[string]any, bool)
	SeatAssignment(ctx context.Context, tournamentID, minerID string) (SeatAssignment, bool)
	Reconnect(ctx context.Context, tournamentID, minerID, sessionID string) (SeatAssignment, bool)
}

type Dependencies struct {
	Gateway           ActionGateway
	Arena             ArenaService
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

func sortedKeys(values map[string]map[string]bool) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
