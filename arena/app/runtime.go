package app

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"sync"
	"time"

	"github.com/clawchain/clawchain/arena/httpapi"
	"github.com/clawchain/clawchain/arena/hub"
	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/store/postgres"
)

type runtimeService struct {
	mu          sync.Mutex
	repo        *postgres.Repository
	now         func() time.Time
	waves       map[string]*waveRuntime
	tournaments map[string]*tournamentRuntime
}

type waveRuntime struct {
	wave         model.Wave
	entrants     map[string]model.Entrant
	hub          *hub.Service
	pack         hub.PackResult
	tournamentID string
}

type tournamentRuntime struct {
	id              string
	waveID          string
	standing        map[string]any
	liveTables      map[string]map[string]any
	seatAssignments map[string]httpapi.SeatAssignment
}

func newRuntimeService(repo *postgres.Repository, now func() time.Time) *runtimeService {
	if now == nil {
		now = time.Now().UTC
	}

	return &runtimeService{
		repo:        repo,
		now:         now,
		waves:       make(map[string]*waveRuntime),
		tournaments: make(map[string]*tournamentRuntime),
	}
}

func (s *runtimeService) ActiveWaves(context.Context) []string {
	s.mu.Lock()
	defer s.mu.Unlock()

	keys := make([]string, 0, len(s.waves))
	for waveID := range s.waves {
		keys = append(keys, waveID)
	}
	sort.Strings(keys)
	return keys
}

func (s *runtimeService) CreateWave(ctx context.Context, req httpapi.CreateWaveRequest) (httpapi.WaveMutationResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if req.WaveID == "" {
		return httpapi.WaveMutationResponse{}, errors.New("wave_id is required")
	}
	mode := model.ArenaMode(req.Mode)
	if err := mode.Validate(); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}
	if _, exists := s.waves[req.WaveID]; exists {
		return httpapi.WaveMutationResponse{}, errors.New("wave already exists")
	}

	now := s.now()
	wave := model.Wave{
		ID:                  req.WaveID,
		Mode:                mode,
		State:               model.WaveStateRegistrationOpen,
		RegistrationOpenAt:  req.RegistrationOpenAt.UTC(),
		RegistrationCloseAt: req.RegistrationCloseAt.UTC(),
		ScheduledStartAt:    req.ScheduledStartAt.UTC(),
		TargetShardSize:     64,
		SoftMinEntrants:     56,
		SoftMaxEntrants:     64,
		HardMaxEntrants:     64,
		TruthMetadata:       truthMetadata(req.WaveID),
		Payload:             json.RawMessage(`{"source":"admin"}`),
		CreatedAt:           now,
		UpdatedAt:           now,
	}
	if err := s.repo.UpsertWave(ctx, wave); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}

	s.waves[req.WaveID] = &waveRuntime{
		wave:     wave,
		entrants: make(map[string]model.Entrant),
	}

	return httpapi.WaveMutationResponse{
		WaveID: req.WaveID,
	}, nil
}

func (s *runtimeService) RegisterMiner(ctx context.Context, waveID, minerID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	waveRuntime, ok := s.waves[waveID]
	if !ok {
		return errors.New("wave not found")
	}

	now := s.now()
	entrant := model.Entrant{
		ID:                fmt.Sprintf("ent:%s:%s", waveID, minerID),
		WaveID:            waveID,
		MinerID:           minerID,
		SeatAlias:         fmt.Sprintf("alias:%s", minerID),
		RegistrationState: model.RegistrationStateConfirmed,
		TruthMetadata:     truthMetadata(fmt.Sprintf("entrant:%s:%s", waveID, minerID)),
		Payload:           json.RawMessage(`{"source":"public_registration"}`),
		CreatedAt:         now,
		UpdatedAt:         now,
	}
	if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
		return err
	}

	waveRuntime.entrants[minerID] = entrant
	return nil
}

func (s *runtimeService) UnregisterMiner(ctx context.Context, waveID, minerID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	waveRuntime, ok := s.waves[waveID]
	if !ok {
		return errors.New("wave not found")
	}

	entrant, ok := waveRuntime.entrants[minerID]
	if !ok {
		return errors.New("miner not registered")
	}
	entrant.RegistrationState = model.RegistrationStateNotRegistered
	entrant.UpdatedAt = s.now()
	if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
		return err
	}
	delete(waveRuntime.entrants, minerID)
	return nil
}

func (s *runtimeService) LockWave(ctx context.Context, waveID string) (httpapi.WaveMutationResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	waveRuntime, ok := s.waves[waveID]
	if !ok {
		return httpapi.WaveMutationResponse{}, errors.New("wave not found")
	}

	entrants := make([]model.Entrant, 0, len(waveRuntime.entrants))
	for _, entrant := range waveRuntime.entrants {
		entrants = append(entrants, entrant)
	}
	sort.Slice(entrants, func(i, j int) bool {
		return entrants[i].MinerID < entrants[j].MinerID
	})

	service := hub.NewService(hub.State{
		WaveID:    waveID,
		WaveState: model.WaveStateRegistrationOpen,
		StartedAt: waveRuntime.wave.ScheduledStartAt,
		Entrants:  entrants,
	}, nil)
	pack, err := service.LockAndPack(ctx)
	if err != nil {
		return httpapi.WaveMutationResponse{}, err
	}
	if len(pack.Tournaments) == 0 {
		return httpapi.WaveMutationResponse{}, errors.New("no tournament packed")
	}

	plan := pack.Tournaments[0]
	now := s.now()
	waveRuntime.hub = service
	waveRuntime.pack = pack
	waveRuntime.tournamentID = plan.TournamentID
	waveRuntime.wave.State = model.WaveStateSeatingGenerated
	waveRuntime.wave.UpdatedAt = now
	if err := s.repo.UpsertWave(ctx, waveRuntime.wave); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}

	tournament := model.Tournament{
		ID:                plan.TournamentID,
		WaveID:            waveID,
		Mode:              model.ArenaMode(plan.RatedOrPractice),
		State:             model.TournamentStateReady,
		NoMultiplier:      plan.NoMultiplier,
		HumanOnly:         true,
		PlayersRegistered: len(entrants),
		PlayersConfirmed:  len(entrants),
		PlayersRemaining:  len(entrants),
		ActiveTableCount:  len(uniqueTableIDs(plan.SeatAssignments)),
		TruthMetadata:     truthMetadata(plan.TournamentID),
		Payload:           json.RawMessage(`{"source":"admin_lock"}`),
		CreatedAt:         now,
		UpdatedAt:         now,
	}
	if err := s.repo.UpsertTournament(ctx, tournament); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}

	for _, assignment := range plan.SeatAssignments {
		entrant := waveRuntime.entrants[assignment.MinerID]
		entrant.TournamentID = plan.TournamentID
		entrant.UpdatedAt = now
		if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
			return httpapi.WaveMutationResponse{}, err
		}
		waveRuntime.entrants[assignment.MinerID] = entrant

		if err := s.repo.UpsertShardAssignment(ctx, model.ShardAssignment{
			ID:              fmt.Sprintf("shard:%s:%s", waveID, assignment.EntrantID),
			WaveID:          waveID,
			TournamentID:    plan.TournamentID,
			EntrantID:       assignment.EntrantID,
			ShardNo:         1,
			TableNo:         assignment.TableNo,
			SeatDrawToken:   fmt.Sprintf("draw:%s:%02d", plan.TournamentID, assignment.SeatNo),
			AssignmentState: "assigned",
			TruthMetadata:   truthMetadata(fmt.Sprintf("shard:%s:%s", waveID, assignment.EntrantID)),
			Payload:         json.RawMessage(`{"source":"admin_lock"}`),
			CreatedAt:       now,
			UpdatedAt:       now,
		}); err != nil {
			return httpapi.WaveMutationResponse{}, err
		}
	}

	s.tournaments[plan.TournamentID] = &tournamentRuntime{
		id:              plan.TournamentID,
		waveID:          waveID,
		standing:        map[string]any{"players_remaining": len(entrants), "round_no": 1},
		liveTables:      make(map[string]map[string]any),
		seatAssignments: make(map[string]httpapi.SeatAssignment),
	}

	return httpapi.WaveMutationResponse{
		WaveID:          waveID,
		TournamentID:    plan.TournamentID,
		RatedOrPractice: plan.RatedOrPractice,
		NoMultiplier:    plan.NoMultiplier,
		RegisteredCount: len(entrants),
	}, nil
}

func (s *runtimeService) PublishSeats(ctx context.Context, waveID string) (httpapi.WaveMutationResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	waveRuntime, ok := s.waves[waveID]
	if !ok {
		return httpapi.WaveMutationResponse{}, errors.New("wave not found")
	}
	if waveRuntime.hub == nil || waveRuntime.tournamentID == "" {
		return httpapi.WaveMutationResponse{}, errors.New("wave not locked")
	}
	if err := waveRuntime.hub.PublishSeats(ctx); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}

	now := s.now()
	waveRuntime.wave.State = model.WaveStateSeatsPublished
	waveRuntime.wave.UpdatedAt = now
	if err := s.repo.UpsertWave(ctx, waveRuntime.wave); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}

	plan := waveRuntime.hub.Result().Tournaments[0]
	tournamentRuntime := s.tournaments[waveRuntime.tournamentID]
	for _, assignment := range plan.SeatAssignments {
		tournamentRuntime.seatAssignments[assignment.MinerID] = httpapi.SeatAssignment{
			TableID:  assignment.TableID,
			StateSeq: 0,
			ReadOnly: true,
		}
		tournamentRuntime.liveTables[assignment.TableID] = map[string]any{
			"acting_seat_no": 0,
			"pot_main":       0,
		}

		entrant := waveRuntime.entrants[assignment.MinerID]
		entrant.TableID = assignment.TableID
		entrant.SeatID = fmt.Sprintf("seat:%s:%02d", assignment.TableID, assignment.SeatNo)
		entrant.RegistrationState = model.RegistrationStateSeated
		entrant.UpdatedAt = now
		if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
			return httpapi.WaveMutationResponse{}, err
		}
		waveRuntime.entrants[assignment.MinerID] = entrant
	}

	tournamentRuntime.standing = map[string]any{
		"players_remaining": len(plan.EntrantIDs),
		"round_no":          1,
	}

	return httpapi.WaveMutationResponse{
		WaveID:          waveID,
		TournamentID:    waveRuntime.tournamentID,
		RatedOrPractice: plan.RatedOrPractice,
		NoMultiplier:    plan.NoMultiplier,
		SeatsPublished:  true,
		RegisteredCount: len(plan.EntrantIDs),
	}, nil
}

func (s *runtimeService) Standing(_ context.Context, tournamentID string) (map[string]any, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	tournamentRuntime, ok := s.tournaments[tournamentID]
	if !ok {
		return nil, false
	}
	return cloneMap(tournamentRuntime.standing), true
}

func (s *runtimeService) LiveTable(_ context.Context, tournamentID, tableID string) (map[string]any, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	tournamentRuntime, ok := s.tournaments[tournamentID]
	if !ok {
		return nil, false
	}
	view, ok := tournamentRuntime.liveTables[tableID]
	if !ok {
		return nil, false
	}
	return cloneMap(view), true
}

func (s *runtimeService) SeatAssignment(_ context.Context, tournamentID, minerID string) (httpapi.SeatAssignment, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	tournamentRuntime, ok := s.tournaments[tournamentID]
	if !ok {
		return httpapi.SeatAssignment{}, false
	}
	assignment, ok := tournamentRuntime.seatAssignments[minerID]
	return assignment, ok
}

func (s *runtimeService) Reconnect(_ context.Context, tournamentID, minerID, sessionID string) (httpapi.SeatAssignment, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	tournamentRuntime, ok := s.tournaments[tournamentID]
	if !ok {
		return httpapi.SeatAssignment{}, false
	}
	assignment, ok := tournamentRuntime.seatAssignments[minerID]
	if !ok {
		return httpapi.SeatAssignment{}, false
	}
	assignment.SessionID = sessionID
	tournamentRuntime.seatAssignments[minerID] = assignment
	return assignment, true
}

func uniqueTableIDs(assignments []hub.SeatAssignment) []string {
	seen := make(map[string]struct{})
	tableIDs := make([]string, 0, len(assignments))
	for _, assignment := range assignments {
		if _, ok := seen[assignment.TableID]; ok {
			continue
		}
		seen[assignment.TableID] = struct{}{}
		tableIDs = append(tableIDs, assignment.TableID)
	}
	sort.Strings(tableIDs)
	return tableIDs
}

func truthMetadata(id string) model.TruthMetadata {
	return model.TruthMetadata{
		SchemaVersion:       1,
		PolicyBundleVersion: "v1",
		StateHash:           id,
		PayloadHash:         id,
	}
}

func cloneMap(input map[string]any) map[string]any {
	output := make(map[string]any, len(input))
	for key, value := range input {
		output[key] = value
	}
	return output
}
