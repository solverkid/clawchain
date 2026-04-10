package app

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/clawchain/clawchain/arena/httpapi"
	"github.com/clawchain/clawchain/arena/hub"
	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/store/postgres"
	"github.com/clawchain/clawchain/arena/table"
)

type runtimeService struct {
	mu          sync.Mutex
	repo        *postgres.Repository
	now         func() time.Time
	waves       map[string]*waveRuntime
	tournaments map[string]*tournamentRuntime
	actors      map[string]*table.Actor
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
	tournament      model.Tournament
	standing        map[string]any
	liveTables      map[string]map[string]any
	seatAssignments map[string]httpapi.SeatAssignment
}

type runtimeClock struct {
	now func() time.Time
}

func (c runtimeClock) Now() time.Time {
	if c.now == nil {
		return time.Now().UTC()
	}
	return c.now().UTC()
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
		actors:      make(map[string]*table.Actor),
	}
}

func (s *runtimeService) bootstrapFromStore(ctx context.Context) error {
	if ctx == nil {
		ctx = context.Background()
	}

	waves, err := s.repo.ListWaves(ctx)
	if err != nil {
		return err
	}

	nextWaves := make(map[string]*waveRuntime, len(waves))
	nextTournaments := make(map[string]*tournamentRuntime)
	nextActors := make(map[string]*table.Actor)

	for _, wave := range waves {
		waveRuntime := &waveRuntime{
			wave:     wave,
			entrants: make(map[string]model.Entrant),
		}

		entrants, err := s.repo.ListEntrantsByWave(ctx, wave.ID)
		if err != nil {
			return err
		}
		for _, entrant := range entrants {
			waveRuntime.entrants[entrant.MinerID] = entrant
		}

		tournaments, err := s.repo.ListTournamentsByWave(ctx, wave.ID)
		if err != nil {
			return err
		}

		entrantList := entrantsByMiner(waveRuntime.entrants)
		for _, tournament := range tournaments {
			assignments := assignmentsForTournament(entrants, tournament.ID)
			tournamentRuntime := &tournamentRuntime{
				id:              tournament.ID,
				waveID:          wave.ID,
				tournament:      tournament,
				standing:        standingFromTournament(tournament),
				liveTables:      make(map[string]map[string]any),
				seatAssignments: make(map[string]httpapi.SeatAssignment),
			}

			for _, assignment := range assignments {
				tournamentRuntime.seatAssignments[assignment.MinerID] = httpapi.SeatAssignment{
					TableID:  assignment.TableID,
					StateSeq: 0,
					ReadOnly: true,
				}
			}

			snapshots, err := s.repo.LoadLatestTableSnapshots(ctx, tournament.ID)
			if err != nil {
				return err
			}
			deadlines, err := s.repo.ListActionDeadlinesByTournament(ctx, tournament.ID)
			if err != nil {
				return err
			}
			openDeadlines := latestOpenDeadlinesByTable(deadlines)
			playerCounts := playerCountByTable(assignments)

			for _, snapshot := range snapshots {
				actor, err := newRecoveredActor(snapshot, openDeadlines[snapshot.TableID], s.now, s.repo)
				if err != nil {
					return err
				}
				nextActors[snapshot.TableID] = actor

				actorState := actor.State()
				view := tableViewFromState(actorState.Table)
				view["player_count"] = playerCounts[snapshot.TableID]
				tournamentRuntime.liveTables[snapshot.TableID] = view

				for minerID, assignment := range tournamentRuntime.seatAssignments {
					if assignment.TableID != snapshot.TableID {
						continue
					}
					assignment.StateSeq = snapshot.StateSeq
					tournamentRuntime.seatAssignments[minerID] = assignment
				}
			}

			for tableID, count := range playerCounts {
				if _, ok := tournamentRuntime.liveTables[tableID]; ok {
					continue
				}
				tournamentRuntime.liveTables[tableID] = map[string]any{
					"acting_seat_no": 0,
					"pot_main":       int64(0),
					"player_count":   count,
				}
			}

			nextTournaments[tournament.ID] = tournamentRuntime

			plan := planFromAssignments(tournament, assignments)
			if waveRuntime.hub == nil {
				remaining := tournament.PlayersRemaining
				if remaining == 0 {
					remaining = len(assignments)
				}
				waveRuntime.hub = hub.NewService(hub.State{
					WaveID:           wave.ID,
					WaveState:        wave.State,
					StartedAt:        wave.ScheduledStartAt,
					Entrants:         entrantList,
					Tournaments:      []hub.TournamentPlan{plan},
					PlayersRemaining: remaining,
					LiveTables:       liveTablesForHub(assignments),
				}, nil)
				if tournament.TimeCapAt != nil {
					waveRuntime.hub.ArmTimeCap()
				}
				waveRuntime.pack = hub.PackResult{Tournaments: []hub.TournamentPlan{plan}}
				waveRuntime.tournamentID = tournament.ID
			}
		}

		nextWaves[wave.ID] = waveRuntime
	}

	s.waves = nextWaves
	s.tournaments = nextTournaments
	s.actors = nextActors
	return nil
}

func (s *runtimeService) runDeadlineScanner(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 250 * time.Millisecond
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			_ = s.ProcessExpiredDeadlines(ctx)
		}
	}
}

func (s *runtimeService) ProcessExpiredDeadlines(ctx context.Context) error {
	if ctx == nil {
		ctx = context.Background()
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	deadlines, err := s.repo.ListExpiredActionDeadlines(ctx, s.now())
	if err != nil {
		return err
	}

	for _, deadline := range deadlines {
		actor := s.actors[deadline.TableID]
		if actor == nil {
			actor, err = s.recoverActorLocked(ctx, deadline.TournamentID, deadline.TableID)
			if err != nil {
				return err
			}
		}
		if actor == nil {
			continue
		}

		before := actor.State()
		seatNo := seatNoFromSeatID(deadline.SeatID)
		if seatNo == 0 {
			seatNo = before.Table.ActingSeatNo
		}
		if seatNo == 0 {
			continue
		}

		result, err := actor.Handle(ctx, table.CommandEnvelope{
			RequestID:        fmt.Sprintf("timeout:%s", deadline.DeadlineID),
			ExpectedStateSeq: before.StateSeq,
			Command:          table.ApplyPhaseTimeout{SeatNo: seatNo},
		})
		if err != nil {
			return fmt.Errorf("apply timeout for %s: %w", deadline.DeadlineID, err)
		}

		after := actor.State()
		if tournamentRuntime, ok := s.tournaments[deadline.TournamentID]; ok {
			view := tableViewFromState(after.Table)
			if existing, exists := tournamentRuntime.liveTables[deadline.TableID]; exists {
				if playerCount, ok := existing["player_count"]; ok {
					view["player_count"] = playerCount
				}
			}
			tournamentRuntime.liveTables[deadline.TableID] = view
			updateSeatAssignmentSeq(tournamentRuntime, deadline.TableID, result.StateSeq)
		}

		if err := s.repo.UpsertTable(ctx, tableRowFromActor(after, 1, false, s.now)); err != nil {
			return err
		}
	}

	return nil
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

	return httpapi.WaveMutationResponse{WaveID: req.WaveID}, nil
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

	entrants := entrantsByMiner(waveRuntime.entrants)
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
		tournament:      tournament,
		standing:        standingFromTournament(tournament),
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
	tournament := tournamentRuntime.tournament
	tournament.ActiveTableCount = len(uniqueTableIDs(plan.SeatAssignments))
	tournament.PlayersRemaining = len(plan.EntrantIDs)
	tournament.PlayersConfirmed = len(plan.EntrantIDs)
	tournament.SeatingRepublishCount = plan.RepublishCount
	tournament.UpdatedAt = now
	if err := s.repo.UpsertTournament(ctx, tournament); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}
	tournamentRuntime.tournament = tournament

	if err := s.applySeatingPlanLocked(ctx, waveRuntime, tournamentRuntime, plan, now); err != nil {
		return httpapi.WaveMutationResponse{}, err
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

func (s *runtimeService) ForceRemoveBeforeStart(ctx context.Context, waveID, minerID string) (map[string]any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	waveRuntime, ok := s.waves[waveID]
	if !ok {
		return nil, errors.New("wave not found")
	}
	if waveRuntime.hub == nil || waveRuntime.tournamentID == "" {
		return nil, errors.New("wave not ready")
	}

	if err := waveRuntime.hub.ForceRemoveBeforeStart(ctx, minerID); err != nil {
		return nil, err
	}
	if err := waveRuntime.hub.RepublishSeats(ctx); err != nil {
		return nil, err
	}

	now := s.now()
	if entrant, ok := waveRuntime.entrants[minerID]; ok {
		entrant.RegistrationState = model.RegistrationStateRemovedBeforeStart
		entrant.TableID = ""
		entrant.SeatID = ""
		entrant.UpdatedAt = now
		if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
			return nil, err
		}
		waveRuntime.entrants[minerID] = entrant
	}

	plan := waveRuntime.hub.Result().Tournaments[0]
	tournamentRuntime := s.tournaments[waveRuntime.tournamentID]
	tournament := tournamentRuntime.tournament
	tournament.PlayersRemaining = len(plan.EntrantIDs)
	tournament.PlayersConfirmed = len(plan.EntrantIDs)
	tournament.ActiveTableCount = len(uniqueTableIDs(plan.SeatAssignments))
	tournament.SeatingRepublishCount = plan.RepublishCount
	tournament.UpdatedAt = now
	if err := s.repo.UpsertTournament(ctx, tournament); err != nil {
		return nil, err
	}
	tournamentRuntime.tournament = tournament

	if err := s.applySeatingPlanLocked(ctx, waveRuntime, tournamentRuntime, plan, now); err != nil {
		return nil, err
	}

	return map[string]any{
		"wave_id":       waveID,
		"tournament_id": waveRuntime.tournamentID,
		"miner_id":      minerID,
		"republished":   true,
	}, nil
}

func (s *runtimeService) ArmTimeCap(ctx context.Context, tournamentID string) (map[string]any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	tournamentRuntime, ok := s.tournaments[tournamentID]
	if !ok {
		return nil, errors.New("tournament not found")
	}
	if waveRuntime, ok := s.waves[tournamentRuntime.waveID]; ok && waveRuntime.hub != nil {
		waveRuntime.hub.ArmTimeCap()
	}

	now := s.now()
	tournament := tournamentRuntime.tournament
	tournament.TimeCapAt = &now
	tournament.UpdatedAt = now
	if err := s.repo.UpsertTournament(ctx, tournament); err != nil {
		return nil, err
	}
	tournamentRuntime.tournament = tournament
	tournamentRuntime.standing = standingFromTournament(tournament)
	tournamentRuntime.standing["terminate_after_current_round"] = true

	return map[string]any{
		"tournament_id":                 tournamentID,
		"terminate_after_current_round": true,
	}, nil
}

func (s *runtimeService) VoidTournament(ctx context.Context, tournamentID, reason string) (map[string]any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	tournamentRuntime, ok := s.tournaments[tournamentID]
	if !ok {
		return nil, errors.New("tournament not found")
	}

	now := s.now()
	tournament := tournamentRuntime.tournament
	tournament.State = model.TournamentStateVoided
	tournament.Voided = true
	tournament.NoMultiplier = true
	tournament.CompletedAt = &now
	tournament.UpdatedAt = now
	if err := s.repo.UpsertTournament(ctx, tournament); err != nil {
		return nil, err
	}
	tournamentRuntime.tournament = tournament
	tournamentRuntime.standing = standingFromTournament(tournament)
	tournamentRuntime.standing["status"] = "voided"
	tournamentRuntime.standing["no_multiplier"] = true
	tournamentRuntime.standing["no_multiplier_reason"] = reason

	return map[string]any{
		"tournament_id": tournamentID,
		"voided":        true,
		"no_multiplier": true,
		"reason":        reason,
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

func (s *runtimeService) applySeatingPlanLocked(ctx context.Context, waveRuntime *waveRuntime, tournamentRuntime *tournamentRuntime, plan hub.TournamentPlan, now time.Time) error {
	existingSnapshots, err := s.repo.LoadLatestTableSnapshots(ctx, plan.TournamentID)
	if err != nil {
		return err
	}
	snapshotByTable := make(map[string]model.TableSnapshot, len(existingSnapshots))
	for _, snapshot := range existingSnapshots {
		snapshotByTable[snapshot.TableID] = snapshot
	}

	for tableID, actor := range s.actors {
		if actor.State().TournamentID == tournamentRuntime.id {
			delete(s.actors, tableID)
		}
	}

	tournamentRuntime.seatAssignments = make(map[string]httpapi.SeatAssignment)
	tournamentRuntime.liveTables = make(map[string]map[string]any)

	grouped := make(map[string][]hub.SeatAssignment)
	for _, assignment := range plan.SeatAssignments {
		grouped[assignment.TableID] = append(grouped[assignment.TableID], assignment)
	}

	tableIDs := make([]string, 0, len(grouped))
	for tableID := range grouped {
		tableIDs = append(tableIDs, tableID)
	}
	sort.Strings(tableIDs)

	activeMiners := make(map[string]struct{}, len(plan.SeatAssignments))
	for _, tableID := range tableIDs {
		assignments := grouped[tableID]
		sort.Slice(assignments, func(i, j int) bool {
			return assignments[i].SeatNo < assignments[j].SeatNo
		})

		tableNo := assignments[0].TableNo
		if tableNo == 0 {
			tableNo = tableNoFromTableID(tableID)
		}
		handID := model.HandID(plan.TournamentID, tableNo, 1)
		previous := snapshotByTable[tableID]
		if err := s.repo.UpsertTable(ctx, model.Table{
			ID:            tableID,
			TournamentID:  plan.TournamentID,
			State:         model.TableStateOpen,
			TableNo:       tableNo,
			RoundNo:       1,
			CurrentHandID: handID,
			ActingSeatNo:  assignments[0].SeatNo,
			MinRaiseSize:  50,
			StateSeq:      previous.StateSeq,
			LevelNo:       1,
			TruthMetadata: truthMetadata(tableID),
			Payload:       json.RawMessage(`{"source":"hub_publish"}`),
			CreatedAt:     now,
			UpdatedAt:     now,
		}); err != nil {
			return err
		}

		state := table.State{
			CurrentPhase:  table.PhaseSignal,
			ActingSeatNo:  assignments[0].SeatNo,
			CurrentToCall: 0,
			MinRaiseSize:  50,
			PotMain:       0,
			Seats:         make(map[int]table.Seat, len(assignments)),
		}

		for _, assignment := range assignments {
			activeMiners[assignment.MinerID] = struct{}{}
			entrant := waveRuntime.entrants[assignment.MinerID]
			entrant.TournamentID = plan.TournamentID
			entrant.TableID = assignment.TableID
			entrant.SeatID = seatID(assignment.TableID, assignment.SeatNo)
			entrant.RegistrationState = model.RegistrationStateSeated
			entrant.UpdatedAt = now
			if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
				return err
			}
			waveRuntime.entrants[assignment.MinerID] = entrant

			if err := s.repo.UpsertSeat(ctx, model.Seat{
				ID:                      entrant.SeatID,
				TableID:                 assignment.TableID,
				TournamentID:            plan.TournamentID,
				EntrantID:               entrant.ID,
				SeatNo:                  assignment.SeatNo,
				SeatAlias:               entrant.SeatAlias,
				MinerID:                 entrant.MinerID,
				State:                   model.SeatStateActive,
				Stack:                   1000,
				TournamentSeatDrawToken: fmt.Sprintf("draw:%s:%02d", plan.TournamentID, assignment.SeatNo),
				TruthMetadata:           truthMetadata(entrant.SeatID),
				Payload:                 json.RawMessage(`{"source":"hub_publish"}`),
				CreatedAt:               now,
				UpdatedAt:               now,
			}); err != nil {
				return err
			}

			if err := s.repo.UpsertAliasMap(ctx, model.AliasMap{
				ID:            fmt.Sprintf("alias:%s", entrant.ID),
				TournamentID:  plan.TournamentID,
				TableID:       assignment.TableID,
				SeatID:        entrant.SeatID,
				EntrantID:     entrant.ID,
				SeatAlias:     entrant.SeatAlias,
				MinerID:       entrant.MinerID,
				TruthMetadata: truthMetadata(fmt.Sprintf("alias:%s", entrant.ID)),
				Payload:       json.RawMessage(`{"source":"hub_publish"}`),
				CreatedAt:     now,
				UpdatedAt:     now,
			}); err != nil {
				return err
			}

			state.Seats[assignment.SeatNo] = table.Seat{
				SeatNo: assignment.SeatNo,
				State:  table.SeatStateActive,
				Stack:  1000,
			}
		}

		actor := table.NewRecoveredActor(table.ActorState{
			TableID:      tableID,
			TournamentID: plan.TournamentID,
			HandID:       handID,
			StateSeq:     previous.StateSeq,
			Table:        state,
		}, previous.StreamSeq, runtimeClock{now: s.now}, s.repo)

		deadlineAt := now.Add(30 * time.Second)
		if err := actor.OpenPhase(ctx, table.PhaseDefinition{
			ID:         model.PhaseID(handID, model.PhaseTypeSignal),
			HandID:     handID,
			Type:       table.PhaseSignal,
			ActingSeat: assignments[0].SeatNo,
			DeadlineAt: &deadlineAt,
		}); err != nil {
			return err
		}

		actorState := actor.State()
		if err := s.repo.UpsertTable(ctx, tableRowFromActor(actorState, 1, false, s.now)); err != nil {
			return err
		}

		s.actors[tableID] = actor
		view := tableViewFromState(actorState.Table)
		view["player_count"] = len(assignments)
		tournamentRuntime.liveTables[tableID] = view
		for _, assignment := range assignments {
			tournamentRuntime.seatAssignments[assignment.MinerID] = httpapi.SeatAssignment{
				TableID:  tableID,
				StateSeq: actorState.StateSeq,
				ReadOnly: true,
			}
		}
	}

	for minerID, entrant := range waveRuntime.entrants {
		if entrant.TournamentID != plan.TournamentID {
			continue
		}
		if _, ok := activeMiners[minerID]; ok {
			continue
		}
		if entrant.RegistrationState != model.RegistrationStateRemovedBeforeStart {
			continue
		}
		entrant.TableID = ""
		entrant.SeatID = ""
		entrant.UpdatedAt = now
		if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
			return err
		}
		waveRuntime.entrants[minerID] = entrant
	}

	tournamentRuntime.standing = standingFromTournament(tournamentRuntime.tournament)
	return nil
}

func (s *runtimeService) recoverActorLocked(ctx context.Context, tournamentID, tableID string) (*table.Actor, error) {
	snapshots, err := s.repo.LoadLatestTableSnapshots(ctx, tournamentID)
	if err != nil {
		return nil, err
	}
	deadlines, err := s.repo.ListActionDeadlinesByTournament(ctx, tournamentID)
	if err != nil {
		return nil, err
	}
	openDeadlines := latestOpenDeadlinesByTable(deadlines)

	for _, snapshot := range snapshots {
		if snapshot.TableID != tableID {
			continue
		}
		actor, err := newRecoveredActor(snapshot, openDeadlines[tableID], s.now, s.repo)
		if err != nil {
			return nil, err
		}
		s.actors[tableID] = actor

		if tournamentRuntime, ok := s.tournaments[tournamentID]; ok {
			view := tableViewFromState(actor.State().Table)
			if existing, exists := tournamentRuntime.liveTables[tableID]; exists {
				if playerCount, ok := existing["player_count"]; ok {
					view["player_count"] = playerCount
				}
			}
			tournamentRuntime.liveTables[tableID] = view
			updateSeatAssignmentSeq(tournamentRuntime, tableID, snapshot.StateSeq)
		}

		return actor, nil
	}

	return nil, nil
}

func newRecoveredActor(snapshot model.TableSnapshot, deadline model.ActionDeadline, now func() time.Time, repo *postgres.Repository) (*table.Actor, error) {
	var state table.State
	if len(snapshot.Payload) > 0 {
		if err := json.Unmarshal(snapshot.Payload, &state); err != nil {
			return nil, fmt.Errorf("unmarshal snapshot %s: %w", snapshot.ID, err)
		}
	}

	return table.NewRecoveredActor(table.ActorState{
		TableID:      snapshot.TableID,
		TournamentID: snapshot.TournamentID,
		HandID:       deadline.HandID,
		PhaseID:      deadline.PhaseID,
		StateSeq:     snapshot.StateSeq,
		Table:        state,
	}, snapshot.StreamSeq, runtimeClock{now: now}, repo), nil
}

func entrantsByMiner(entrants map[string]model.Entrant) []model.Entrant {
	values := make([]model.Entrant, 0, len(entrants))
	for _, entrant := range entrants {
		values = append(values, entrant)
	}
	sort.Slice(values, func(i, j int) bool {
		return values[i].MinerID < values[j].MinerID
	})
	return values
}

func assignmentsForTournament(entrants []model.Entrant, tournamentID string) []hub.SeatAssignment {
	assignments := make([]hub.SeatAssignment, 0)
	for _, entrant := range entrants {
		if entrant.TournamentID != tournamentID || entrant.TableID == "" || entrant.SeatID == "" {
			continue
		}
		assignments = append(assignments, hub.SeatAssignment{
			EntrantID: entrant.ID,
			MinerID:   entrant.MinerID,
			TableID:   entrant.TableID,
			TableNo:   tableNoFromTableID(entrant.TableID),
			SeatNo:    seatNoFromSeatID(entrant.SeatID),
		})
	}
	sort.Slice(assignments, func(i, j int) bool {
		if assignments[i].TableID != assignments[j].TableID {
			return assignments[i].TableID < assignments[j].TableID
		}
		return assignments[i].SeatNo < assignments[j].SeatNo
	})
	return assignments
}

func planFromAssignments(tournament model.Tournament, assignments []hub.SeatAssignment) hub.TournamentPlan {
	entrantIDs := make([]string, 0, len(assignments))
	for _, assignment := range assignments {
		entrantIDs = append(entrantIDs, assignment.EntrantID)
	}
	return hub.TournamentPlan{
		TournamentID:       tournament.ID,
		RatedOrPractice:    string(tournament.Mode),
		NoMultiplier:       tournament.NoMultiplier,
		EntrantIDs:         entrantIDs,
		SeatAssignments:    assignments,
		RepublishCount:     tournament.SeatingRepublishCount,
		SeatsWerePublished: len(assignments) > 0,
	}
}

func liveTablesForHub(assignments []hub.SeatAssignment) []hub.LiveTable {
	playerCounts := playerCountByTable(assignments)
	tableIDs := make([]string, 0, len(playerCounts))
	for tableID := range playerCounts {
		tableIDs = append(tableIDs, tableID)
	}
	sort.Strings(tableIDs)

	liveTables := make([]hub.LiveTable, 0, len(tableIDs))
	for _, tableID := range tableIDs {
		liveTables = append(liveTables, hub.LiveTable{
			TableID:     tableID,
			PlayerCount: playerCounts[tableID],
		})
	}
	return liveTables
}

func playerCountByTable(assignments []hub.SeatAssignment) map[string]int {
	counts := make(map[string]int)
	for _, assignment := range assignments {
		counts[assignment.TableID]++
	}
	return counts
}

func latestOpenDeadlinesByTable(deadlines []model.ActionDeadline) map[string]model.ActionDeadline {
	latest := make(map[string]model.ActionDeadline)
	for _, deadline := range deadlines {
		if deadline.Status != "open" {
			continue
		}
		current, ok := latest[deadline.TableID]
		if !ok || deadline.DeadlineAt.After(current.DeadlineAt) || deadline.UpdatedAt.After(current.UpdatedAt) {
			latest[deadline.TableID] = deadline
		}
	}
	return latest
}

func tableRowFromActor(state table.ActorState, roundNo int, finalTable bool, now func() time.Time) model.Table {
	timestamp := time.Now().UTC()
	if now != nil {
		timestamp = now().UTC()
	}
	return model.Table{
		ID:            state.TableID,
		TournamentID:  state.TournamentID,
		State:         model.TableStateOpen,
		TableNo:       tableNoFromTableID(state.TableID),
		RoundNo:       roundNo,
		CurrentHandID: state.HandID,
		ActingSeatNo:  state.Table.ActingSeatNo,
		CurrentToCall: state.Table.CurrentToCall,
		MinRaiseSize:  state.Table.MinRaiseSize,
		PotMain:       state.Table.PotMain,
		StateSeq:      state.StateSeq,
		LevelNo:       1,
		IsFinalTable:  finalTable,
		TruthMetadata: truthMetadata(state.TableID),
		Payload:       mustJSON(state.Table),
		CreatedAt:     timestamp,
		UpdatedAt:     timestamp,
	}
}

func standingFromTournament(tournament model.Tournament) map[string]any {
	roundNo := tournament.CurrentRoundNo
	if roundNo == 0 {
		roundNo = 1
	}
	standing := map[string]any{
		"players_remaining": tournament.PlayersRemaining,
		"round_no":          roundNo,
		"state":             string(tournament.State),
		"no_multiplier":     tournament.NoMultiplier,
	}
	if tournament.TimeCapAt != nil {
		standing["terminate_after_current_round"] = true
	}
	if tournament.Voided {
		standing["status"] = "voided"
	}
	return standing
}

func tableViewFromState(state table.State) map[string]any {
	return map[string]any{
		"acting_seat_no": state.ActingSeatNo,
		"pot_main":       state.PotMain,
		"current_phase":  string(state.CurrentPhase),
	}
}

func updateSeatAssignmentSeq(tournamentRuntime *tournamentRuntime, tableID string, stateSeq int64) {
	for minerID, assignment := range tournamentRuntime.seatAssignments {
		if assignment.TableID != tableID {
			continue
		}
		assignment.StateSeq = stateSeq
		tournamentRuntime.seatAssignments[minerID] = assignment
	}
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

func tableNoFromTableID(tableID string) int {
	return trailingInt(tableID)
}

func seatNoFromSeatID(seatID string) int {
	return trailingInt(seatID)
}

func trailingInt(value string) int {
	idx := strings.LastIndex(value, ":")
	if idx == -1 || idx == len(value)-1 {
		return 0
	}
	number, err := strconv.Atoi(value[idx+1:])
	if err != nil {
		return 0
	}
	return number
}

func seatID(tableID string, seatNo int) string {
	return fmt.Sprintf("seat:%s:%02d", tableID, seatNo)
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

func mustJSON(value any) json.RawMessage {
	payload, err := json.Marshal(value)
	if err != nil {
		panic(err)
	}
	return payload
}
