package app

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/clawchain/clawchain/arena/gateway"
	"github.com/clawchain/clawchain/arena/httpapi"
	"github.com/clawchain/clawchain/arena/hub"
	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/rating"
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
	gateway     *gateway.Gateway
	rating      *rating.Writer
}

const (
	roundsPerBlindLevel         = 4
	interventionTypeDisqualify  = "disqualify"
	interventionStatusRequested = "requested"
	interventionStatusApplied   = "applied"
	noMultiplierReasonLiveDQ    = "live_disqualification"
)

type blindLevelSpec struct {
	LevelNo    int
	SmallBlind int64
	BigBlind   int64
	Ante       int64
}

var blindSchedule = []blindLevelSpec{
	{LevelNo: 1, SmallBlind: 25, BigBlind: 50, Ante: 0},
	{LevelNo: 2, SmallBlind: 50, BigBlind: 100, Ante: 10},
	{LevelNo: 3, SmallBlind: 75, BigBlind: 150, Ante: 15},
	{LevelNo: 4, SmallBlind: 100, BigBlind: 200, Ante: 25},
	{LevelNo: 5, SmallBlind: 150, BigBlind: 300, Ante: 40},
	{LevelNo: 6, SmallBlind: 200, BigBlind: 400, Ante: 50},
	{LevelNo: 7, SmallBlind: 300, BigBlind: 600, Ante: 75},
	{LevelNo: 8, SmallBlind: 400, BigBlind: 800, Ante: 100},
	{LevelNo: 9, SmallBlind: 600, BigBlind: 1200, Ante: 150},
	{LevelNo: 10, SmallBlind: 800, BigBlind: 1600, Ante: 200},
}

type waveRuntime struct {
	wave         model.Wave
	entrants     map[string]model.Entrant
	hub          *hub.Service
	liveHub      *hub.Service
	pack         hub.PackResult
	tournamentID string
}

type tournamentRuntime struct {
	id                       string
	waveID                   string
	tournament               model.Tournament
	standing                 map[string]any
	liveTables               map[string]map[string]any
	seatAssignments          map[string]httpapi.SeatAssignment
	pendingDisqualifications map[string]model.OperatorIntervention
	disqualificationSeen     bool
}

type runtimeClock struct {
	now func() time.Time
}

type roundBarrierPayload struct {
	ClosedTableIDs []string `json:"closed_table_ids,omitempty"`
}

func (c runtimeClock) Now() time.Time {
	if c.now == nil {
		return time.Now().UTC()
	}
	return c.now().UTC()
}

func blindLevelForRound(roundNo int) blindLevelSpec {
	if roundNo <= 0 {
		return blindSchedule[0]
	}

	index := (roundNo - 1) / roundsPerBlindLevel
	if index >= len(blindSchedule) {
		return blindSchedule[len(blindSchedule)-1]
	}
	return blindSchedule[index]
}

func minRaiseToForLevel(level blindLevelSpec) int64 {
	return level.Ante + (2 * level.BigBlind)
}

func roundNoForTournament(tournament model.Tournament) int {
	if tournament.CurrentRoundNo > 0 {
		return tournament.CurrentRoundNo
	}
	return 1
}

func isFinalTableTournamentState(state model.TournamentState) bool {
	return state == model.TournamentStateLiveFinalTable
}

func newRuntimeService(repo *postgres.Repository, now func() time.Time, gw *gateway.Gateway, rw *rating.Writer) *runtimeService {
	if now == nil {
		now = func() time.Time {
			return time.Now().UTC()
		}
	}

	return &runtimeService{
		repo:        repo,
		now:         now,
		waves:       make(map[string]*waveRuntime),
		tournaments: make(map[string]*tournamentRuntime),
		actors:      make(map[string]*table.Actor),
		gateway:     gw,
		rating:      rw,
	}
}

func (s *runtimeService) upsertBlindSchedule(ctx context.Context, tournamentID string, now time.Time, source string) error {
	for idx, level := range blindSchedule {
		roundStart := idx*roundsPerBlindLevel + 1
		roundEnd := (idx + 1) * roundsPerBlindLevel
		startsAt := now.Add(time.Duration(idx*roundsPerBlindLevel) * time.Minute)
		endsAt := now.Add(time.Duration((idx+1)*roundsPerBlindLevel) * time.Minute)
		if err := s.repo.UpsertLevel(ctx, model.Level{
			ID:           fmt.Sprintf("level:%s:%02d", tournamentID, level.LevelNo),
			TournamentID: tournamentID,
			LevelNo:      level.LevelNo,
			SmallBlind:   level.SmallBlind,
			BigBlind:     level.BigBlind,
			Ante:         level.Ante,
			StartsAt:     startsAt,
			EndsAt:       endsAt,
			TruthMetadata: truthMetadata(
				fmt.Sprintf("level:%s:%02d", tournamentID, level.LevelNo),
			),
			Payload: mustJSON(map[string]any{
				"source":      source,
				"round_start": roundStart,
				"round_end":   roundEnd,
			}),
			CreatedAt: now,
			UpdatedAt: now,
		}); err != nil {
			return err
		}
	}
	return nil
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
			seats, err := s.repo.ListSeatsByTournament(ctx, tournament.ID)
			if err != nil {
				return err
			}
			eliminations, err := s.repo.ListEliminationEventsByTournament(ctx, tournament.ID)
			if err != nil {
				return err
			}
			interventions, err := s.repo.ListOperatorInterventionsByTournament(ctx, tournament.ID)
			if err != nil {
				return err
			}
			assignments := assignmentsForTournament(entrants, tournament.ID)
			seatAssignments := seatAssignmentsFromEntrantsAndTruth(entrants, seats, eliminations, tournament)
			pendingDisqualifications, disqualificationSeen := pendingDisqualificationsFromInterventions(interventions)
			for minerID := range pendingDisqualifications {
				assignment, ok := seatAssignments[minerID]
				if !ok {
					continue
				}
				assignment.ReadOnly = true
				seatAssignments[minerID] = assignment
			}
			tournamentRuntime := &tournamentRuntime{
				id:                       tournament.ID,
				waveID:                   wave.ID,
				tournament:               tournament,
				standing:                 standingFromTournament(tournament),
				liveTables:               make(map[string]map[string]any),
				seatAssignments:          seatAssignments,
				pendingDisqualifications: pendingDisqualifications,
				disqualificationSeen:     disqualificationSeen,
			}
			refreshStanding(tournamentRuntime)

			if !tournamentAcceptsPlay(tournament.State) {
				nextTournaments[tournament.ID] = tournamentRuntime
				continue
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
				if s.gateway != nil {
					s.gateway.RegisterActor(snapshot.TableID, actor)
				}

				actorState := actor.State()
				view := tableViewFromActorState(actorState)
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
				view := tableViewFromActorState(table.ActorState{})
				view["player_count"] = count
				tournamentRuntime.liveTables[tableID] = view
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
			barrier, err := s.repo.LoadRoundBarrier(ctx, tournament.ID, roundNoForTournament(tournament))
			if err != nil && !errors.Is(err, sql.ErrNoRows) {
				return err
			}
			s.resetLiveHubWithBarrierLocked(
				waveRuntime,
				tournament.ID,
				tournament.PlayersRemaining,
				liveTablesForHub(assignments),
				assignments,
				closedTablesFromBarrier(barrier),
			)
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

		_, err = actor.Handle(ctx, table.CommandEnvelope{
			RequestID:        fmt.Sprintf("timeout:%s", deadline.DeadlineID),
			ExpectedStateSeq: before.StateSeq,
			Command:          table.ApplyPhaseTimeout{SeatNo: seatNo},
		})
		if err != nil {
			return fmt.Errorf("apply timeout for %s: %w", deadline.DeadlineID, err)
		}

		after := actor.State()
		if tournamentRuntime, ok := s.tournaments[deadline.TournamentID]; ok {
			after, _, completed, err := s.postActorMutationLocked(ctx, tournamentRuntime, deadline.TableID, after)
			if err != nil {
				return err
			}
			if completed {
				continue
			}
			view := tableViewFromActorState(after)
			if existing, exists := tournamentRuntime.liveTables[deadline.TableID]; exists {
				if playerCount, ok := existing["player_count"]; ok {
					view["player_count"] = playerCount
				}
			}
			tournamentRuntime.liveTables[deadline.TableID] = view
			updateSeatAssignmentSeq(tournamentRuntime, deadline.TableID, after.StateSeq)
			if err := s.repo.UpsertTable(ctx, tableRowFromActor(after, roundNoForTournament(tournamentRuntime.tournament), isFinalTableTournamentState(tournamentRuntime.tournament.State), s.now)); err != nil {
				return err
			}
			continue
		}

		if err := s.repo.UpsertTable(ctx, tableRowFromActor(after, 1, false, s.now)); err != nil {
			return err
		}
	}

	return nil
}

func (s *runtimeService) OnSubmitCommitted(ctx context.Context, req gateway.SubmitRequest, state table.ActorState) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	tournamentRuntime, ok := s.tournaments[req.TournamentID]
	if !ok {
		return nil
	}

	if actor := s.actors[req.TableID]; actor != nil {
		var completed bool
		var err error
		state, _, completed, err = s.postActorMutationLocked(ctx, tournamentRuntime, req.TableID, state)
		if err != nil {
			return err
		}
		if completed {
			return nil
		}
	}

	view := tableViewFromActorState(state)
	if existing, exists := tournamentRuntime.liveTables[req.TableID]; exists {
		if playerCount, ok := existing["player_count"]; ok {
			view["player_count"] = playerCount
		}
	}
	tournamentRuntime.liveTables[req.TableID] = view
	updateSeatAssignmentSeq(tournamentRuntime, req.TableID, state.StateSeq)
	return nil
}

func (s *runtimeService) postActorMutationLocked(ctx context.Context, tournamentRuntime *tournamentRuntime, tableID string, state table.ActorState) (table.ActorState, int, bool, error) {
	roundNo := tournamentRuntime.tournament.CurrentRoundNo
	if roundNo == 0 {
		roundNo = 1
	}

	actor := s.actors[tableID]
	if actor == nil {
		return state, roundNo, false, nil
	}

	if state.Table.HandClosed {
		nextState, nextRoundNo, err := s.advanceClosedTableLocked(ctx, tournamentRuntime, tableID)
		if err != nil {
			return table.ActorState{}, 0, false, err
		}
		if nextState.TableID != "" {
			state = nextState
			roundNo = nextRoundNo
		}
		if tournamentRuntime.tournament.State == model.TournamentStateCompleted {
			return state, roundNo, true, nil
		}
	} else if state.Table.ActingSeatNo != 0 {
		deadlineAt := s.now().Add(30 * time.Second)
		if err := actor.OpenPhase(ctx, table.PhaseDefinition{
			ID:         nextTurnPhaseID(state.HandID, state.Table.CurrentPhase, state.StateSeq+1),
			HandID:     state.HandID,
			Type:       state.Table.CurrentPhase,
			ActingSeat: state.Table.ActingSeatNo,
			ToCall:     state.Table.CurrentToCall,
			DeadlineAt: &deadlineAt,
		}); err != nil {
			return table.ActorState{}, 0, false, err
		}
		state = actor.State()
	}

	if err := s.repo.UpsertTable(ctx, tableRowFromActor(state, roundNo, isFinalTableTournamentState(tournamentRuntime.tournament.State), s.now)); err != nil {
		return table.ActorState{}, 0, false, err
	}
	return state, roundNo, false, nil
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
		id:                       plan.TournamentID,
		waveID:                   waveID,
		tournament:               tournament,
		standing:                 standingFromTournament(tournament),
		liveTables:               make(map[string]map[string]any),
		seatAssignments:          make(map[string]httpapi.SeatAssignment),
		pendingDisqualifications: make(map[string]model.OperatorIntervention),
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
	level := blindLevelForRound(1)
	tournament.ActiveTableCount = len(uniqueTableIDs(plan.SeatAssignments))
	tournament.PlayersRemaining = len(plan.EntrantIDs)
	tournament.PlayersConfirmed = len(plan.EntrantIDs)
	tournament.SeatingRepublishCount = plan.RepublishCount
	tournament.CurrentLevelNo = level.LevelNo
	tournament.UpdatedAt = now
	if err := s.repo.UpsertTournament(ctx, tournament); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}
	tournamentRuntime.tournament = tournament
	if err := s.upsertBlindSchedule(ctx, tournament.ID, now, "publish_seats"); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}

	if err := s.applySeatingPlanLocked(ctx, waveRuntime, tournamentRuntime, plan, now); err != nil {
		return httpapi.WaveMutationResponse{}, err
	}
	s.resetLiveHubLocked(waveRuntime, plan.TournamentID, len(plan.EntrantIDs), liveTablesForHub(plan.SeatAssignments), plan.SeatAssignments)
	if err := s.persistRoundBarrierLocked(ctx, waveRuntime, tournamentRuntime); err != nil {
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
	s.resetLiveHubLocked(waveRuntime, plan.TournamentID, len(plan.EntrantIDs), liveTablesForHub(plan.SeatAssignments), plan.SeatAssignments)

	return map[string]any{
		"wave_id":       waveID,
		"tournament_id": waveRuntime.tournamentID,
		"miner_id":      minerID,
		"republished":   true,
	}, nil
}

func (s *runtimeService) Disqualify(ctx context.Context, tournamentID, minerID, reason string) (map[string]any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	tournamentRuntime, ok := s.tournaments[tournamentID]
	if !ok {
		return nil, errors.New("tournament not found")
	}
	if !tournamentAcceptsPlay(tournamentRuntime.tournament.State) {
		return nil, errors.New("tournament not live")
	}
	waveRuntime, ok := s.waves[tournamentRuntime.waveID]
	if !ok {
		return nil, errors.New("wave not found")
	}
	entrant, ok := waveRuntime.entrants[minerID]
	if !ok || entrant.TournamentID != tournamentID {
		return nil, errors.New("entrant not found")
	}
	if entrant.RegistrationState != model.RegistrationStatePlaying && entrant.RegistrationState != model.RegistrationStateSeated {
		return nil, errors.New("entrant not active")
	}

	assignment, ok := tournamentRuntime.seatAssignments[minerID]
	if !ok || assignment.TableID == "" || assignment.SeatNo == 0 {
		return nil, errors.New("seat assignment not found")
	}
	if tournamentRuntime.pendingDisqualifications == nil {
		tournamentRuntime.pendingDisqualifications = make(map[string]model.OperatorIntervention)
	}

	now := s.now()
	intervention := model.OperatorIntervention{
		ID:                   fmt.Sprintf("ops:dq:%s:%s", tournamentID, minerID),
		TournamentID:         tournamentID,
		TableID:              assignment.TableID,
		SeatID:               seatID(assignment.TableID, assignment.SeatNo),
		MinerID:              minerID,
		InterventionType:     interventionTypeDisqualify,
		Status:               interventionStatusRequested,
		RequestedBy:          "admin_api",
		RequestedAt:          now,
		EffectiveAtSafePoint: true,
		ReasonCode:           noMultiplierReasonLiveDQ,
		ReasonDetail:         reason,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			StateHash:           fmt.Sprintf("ops-state:%s:%s", tournamentID, minerID),
			PayloadHash:         fmt.Sprintf("ops-payload:%s:%s", tournamentID, minerID),
		},
		Payload:   mustJSON(map[string]any{"stage": "live", "requested": true}),
		CreatedAt: now,
		UpdatedAt: now,
	}
	if err := s.repo.UpsertOperatorIntervention(ctx, intervention); err != nil {
		return nil, err
	}

	tournamentRuntime.pendingDisqualifications[minerID] = intervention
	tournamentRuntime.disqualificationSeen = true
	assignment.ReadOnly = true
	tournamentRuntime.seatAssignments[minerID] = assignment

	tournament := tournamentRuntime.tournament
	tournament.NoMultiplier = true
	tournament.UpdatedAt = now
	if err := s.repo.UpsertTournament(ctx, tournament); err != nil {
		return nil, err
	}
	tournamentRuntime.tournament = tournament
	refreshStanding(tournamentRuntime)

	return map[string]any{
		"tournament_id":     tournamentID,
		"miner_id":          minerID,
		"intervention_type": interventionTypeDisqualify,
		"effective_at":      "round_barrier",
		"no_multiplier":     true,
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
	refreshStanding(tournamentRuntime)
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
	refreshStanding(tournamentRuntime)
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
	existingSnapshots, err := s.repo.LoadLatestTableSnapshots(ctx, tournamentRuntime.id)
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
			if s.gateway != nil {
				s.gateway.RemoveActor(tableID)
			}
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
	level := blindLevelForRound(1)
	for _, tableID := range tableIDs {
		assignments := grouped[tableID]
		sort.Slice(assignments, func(i, j int) bool {
			return assignments[i].SeatNo < assignments[j].SeatNo
		})

		tableNo := assignments[0].TableNo
		if tableNo == 0 {
			tableNo = tableNoFromTableID(tableID)
		}
		previous := snapshotByTable[tableID]
		if err := s.repo.UpsertTable(ctx, model.Table{
			ID:            tableID,
			TournamentID:  plan.TournamentID,
			State:         model.TableStateOpen,
			TableNo:       tableNo,
			RoundNo:       1,
			CurrentHandID: model.HandID(plan.TournamentID, tableNo, 1),
			ActingSeatNo:  0,
			MinRaiseSize:  minRaiseToForLevel(level),
			StateSeq:      previous.StateSeq,
			LevelNo:       level.LevelNo,
			TruthMetadata: truthMetadata(tableID),
			Payload:       json.RawMessage(`{"source":"hub_publish"}`),
			CreatedAt:     now,
			UpdatedAt:     now,
		}); err != nil {
			return err
		}

		state := table.State{
			CurrentPhase: table.PhaseSignal,
			HandNumber:   0,
			Seats:        make(map[int]table.Seat, len(assignments)),
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
		nextState, _, err := table.Apply(state, table.StartHand{
			SmallBlind: level.SmallBlind,
			BigBlind:   level.BigBlind,
			Ante:       level.Ante,
			MinRaiseTo: minRaiseToForLevel(level),
		})
		if err != nil {
			return err
		}
		state = nextState
		handID := model.HandID(plan.TournamentID, tableNo, state.HandNumber)

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
			ActingSeat: state.ActingSeatNo,
			ToCall:     state.CurrentToCall,
			DeadlineAt: &deadlineAt,
		}); err != nil {
			return err
		}

		actorState := actor.State()
		if err := s.repo.UpsertTable(ctx, tableRowFromActor(actorState, 1, false, s.now)); err != nil {
			return err
		}

		s.actors[tableID] = actor
		view := tableViewFromActorState(actorState)
		view["player_count"] = len(assignments)
		tournamentRuntime.liveTables[tableID] = view
		for _, assignment := range assignments {
			tournamentRuntime.seatAssignments[assignment.MinerID] = httpapi.SeatAssignment{
				TableID:  tableID,
				SeatNo:   assignment.SeatNo,
				StateSeq: actorState.StateSeq,
				ReadOnly: false,
			}
		}
		if s.gateway != nil {
			s.gateway.RegisterActor(tableID, actor)
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

	refreshStanding(tournamentRuntime)
	return nil
}

func (s *runtimeService) advanceClosedTableLocked(ctx context.Context, tournamentRuntime *tournamentRuntime, tableID string) (table.ActorState, int, error) {
	waveRuntime, ok := s.waves[tournamentRuntime.waveID]
	if !ok || waveRuntime.liveHub == nil {
		return table.ActorState{}, 0, nil
	}

	waveRuntime.liveHub.MarkHandClosed(tableID)
	if err := s.persistRoundBarrierLocked(ctx, waveRuntime, tournamentRuntime); err != nil {
		return table.ActorState{}, 0, err
	}
	if !waveRuntime.liveHub.CanAdvanceRound() {
		return table.ActorState{}, 0, nil
	}

	assignments := s.currentAssignmentsForTournamentLocked(waveRuntime, tournamentRuntime.id)
	if err := s.syncActiveEntrantsLocked(ctx, waveRuntime, tournamentRuntime, assignments); err != nil {
		return table.ActorState{}, 0, err
	}
	liveTables := liveTablesForHub(assignments)
	playersRemaining := len(assignments)
	s.resetLiveHubLocked(waveRuntime, tournamentRuntime.id, playersRemaining, liveTables, assignments)
	plan := waveRuntime.liveHub.BuildTransitionPlan()

	currentRoundNo := tournamentRuntime.tournament.CurrentRoundNo
	if currentRoundNo == 0 {
		currentRoundNo = 1
	}

	if completionReason := completionReason(tournamentRuntime.tournament, waveRuntime.liveHub, playersRemaining); completionReason != "" {
		if err := s.completeTournamentLocked(ctx, waveRuntime, tournamentRuntime, assignments, currentRoundNo, completionReason); err != nil {
			return table.ActorState{}, 0, err
		}
		return table.ActorState{}, currentRoundNo, nil
	}

	nextRoundNo := currentRoundNo + 1
	nextLevel := blindLevelForRound(nextRoundNo)

	tournament := tournamentRuntime.tournament
	tournament.CurrentRoundNo = nextRoundNo
	tournament.CurrentLevelNo = nextLevel.LevelNo
	tournament.PlayersRemaining = playersRemaining
	tournament.ActiveTableCount = len(uniqueTableIDs(plan.SeatAssignments))
	if plan.Decision == hub.TransitionFinalTable {
		tournament.FinalTableTableID = model.TableID(tournamentRuntime.id, 1)
		tournament.State = model.TournamentStateLiveFinalTable
	} else if len(uniqueTableIDs(plan.SeatAssignments)) <= 1 {
		tournament.State = model.TournamentStateLiveFinalTable
	} else {
		tournament.State = model.TournamentStateLiveMultiTable
	}
	tournament.UpdatedAt = s.now()
	if err := s.repo.UpsertTournament(ctx, tournament); err != nil {
		return table.ActorState{}, 0, err
	}
	tournamentRuntime.tournament = tournament
	refreshStanding(tournamentRuntime)
	var states map[string]table.ActorState
	var err error
	if plan.Decision == hub.TransitionNone {
		states, err = s.startNextRoundLocked(ctx, tournamentRuntime, nextRoundNo)
	} else {
		states, err = s.applyTransitionPlanLocked(ctx, waveRuntime, tournamentRuntime, plan, nextRoundNo)
	}
	if err != nil {
		return table.ActorState{}, 0, err
	}
	if err := s.persistRoundBarrierLocked(ctx, waveRuntime, tournamentRuntime); err != nil {
		return table.ActorState{}, 0, err
	}
	state, ok := states[tableID]
	if ok {
		return state, nextRoundNo, nil
	}
	for _, value := range states {
		return value, nextRoundNo, nil
	}
	return table.ActorState{}, nextRoundNo, nil
}

func (s *runtimeService) syncActiveEntrantsLocked(ctx context.Context, waveRuntime *waveRuntime, tournamentRuntime *tournamentRuntime, assignments []hub.SeatAssignment) error {
	activeByMiner := make(map[string]hub.SeatAssignment, len(assignments))
	for _, assignment := range assignments {
		activeByMiner[assignment.MinerID] = assignment
	}

	if tournamentRuntime != nil {
		nextSeatAssignments := make(map[string]httpapi.SeatAssignment, len(tournamentRuntime.seatAssignments))
		for minerID, current := range tournamentRuntime.seatAssignments {
			current.ReadOnly = true
			nextSeatAssignments[minerID] = current
		}
		for minerID, assignment := range activeByMiner {
			current := nextSeatAssignments[minerID]
			current.TableID = assignment.TableID
			current.SeatNo = assignment.SeatNo
			current.ReadOnly = false
			nextSeatAssignments[minerID] = current
		}
		tournamentRuntime.seatAssignments = nextSeatAssignments
	}

	for minerID, entrant := range waveRuntime.entrants {
		if tournamentRuntime == nil || entrant.TournamentID != tournamentRuntime.id {
			continue
		}

		assignment, active := activeByMiner[minerID]
		updated := false
		if active {
			desiredSeatID := seatID(assignment.TableID, assignment.SeatNo)
			if entrant.TableID != assignment.TableID {
				entrant.TableID = assignment.TableID
				updated = true
			}
			if entrant.SeatID != desiredSeatID {
				entrant.SeatID = desiredSeatID
				updated = true
			}
			if entrant.RegistrationState != model.RegistrationStatePlaying {
				entrant.RegistrationState = model.RegistrationStatePlaying
				updated = true
			}
		} else {
			intervention, disqualified := tournamentRuntime.pendingDisqualifications[minerID]
			stageReached := "eliminated"
			registrationState := model.RegistrationStateEliminated
			if disqualified {
				stageReached = "disqualified"
				registrationState = model.RegistrationStateDisqualified
			}
			if entrant.RegistrationState != registrationState {
				eventID, err := s.appendFieldExitEventLocked(ctx, tournamentRuntime.id, entrant, stageReached)
				if err != nil {
					return err
				}
				if disqualified {
					intervention.Status = interventionStatusApplied
					intervention.ResolvedEventID = eventID
					intervention.UpdatedAt = s.now()
					intervention.Payload = mustJSON(map[string]any{"stage": "live", "applied": true})
					if err := s.repo.UpsertOperatorIntervention(ctx, intervention); err != nil {
						return err
					}
					delete(tournamentRuntime.pendingDisqualifications, minerID)
				}
			}
			if entrant.TableID != "" {
				entrant.TableID = ""
				updated = true
			}
			if entrant.SeatID != "" {
				entrant.SeatID = ""
				updated = true
			}
			if entrant.RegistrationState != registrationState {
				entrant.RegistrationState = registrationState
				updated = true
			}
			if entrant.StageReached != stageReached {
				entrant.StageReached = stageReached
				updated = true
			}
		}

		if !updated {
			continue
		}
		entrant.UpdatedAt = s.now()
		if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
			return err
		}
		waveRuntime.entrants[minerID] = entrant
	}

	return nil
}

func (s *runtimeService) recoverActorLocked(ctx context.Context, tournamentID, tableID string) (*table.Actor, error) {
	if tournamentRuntime, ok := s.tournaments[tournamentID]; ok && !tournamentAcceptsPlay(tournamentRuntime.tournament.State) {
		return nil, nil
	}

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
		if s.gateway != nil {
			s.gateway.RegisterActor(tableID, actor)
		}

		if tournamentRuntime, ok := s.tournaments[tournamentID]; ok {
			view := tableViewFromActorState(actor.State())
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

func (s *runtimeService) completeTournamentLocked(ctx context.Context, waveRuntime *waveRuntime, tournamentRuntime *tournamentRuntime, assignments []hub.SeatAssignment, currentRoundNo int, reason string) error {
	now := s.now()
	tournament := tournamentRuntime.tournament
	tableIDs := uniqueTableIDs(assignments)
	tournament.State = model.TournamentStateCompleted
	tournament.CurrentRoundNo = currentRoundNo
	tournament.PlayersRemaining = len(assignments)
	tournament.ActiveTableCount = len(tableIDs)
	if tournament.FinalTableTableID == "" && len(tableIDs) == 1 {
		tournament.FinalTableTableID = tableIDs[0]
	}
	tournament.CompletedAt = &now
	tournament.UpdatedAt = now
	if err := s.repo.UpsertTournament(ctx, tournament); err != nil {
		return err
	}
	tournamentRuntime.tournament = tournament
	refreshStanding(tournamentRuntime)
	tournamentRuntime.standing["status"] = "completed"
	tournamentRuntime.standing["completed_reason"] = reason
	if len(assignments) == 1 {
		tournamentRuntime.standing["winner_miner_id"] = assignments[0].MinerID
	}

	completion, finishRanks, stageReached, eliminationEvents, err := s.buildTournamentCompletionLocked(ctx, waveRuntime, tournamentRuntime, assignments, reason)
	if err != nil {
		return err
	}
	tournamentRuntime.standing["final_standings"] = finalStandingEntries(completion.Entrants)
	if err := s.saveTournamentCompletionSnapshotLocked(ctx, tournamentRuntime, currentRoundNo, reason); err != nil {
		return err
	}
	if len(eliminationEvents) > 0 {
		if err := s.repo.AppendEliminationEvents(ctx, eliminationEvents); err != nil {
			return err
		}
	}
	for minerID, assignment := range tournamentRuntime.seatAssignments {
		assignment.ReadOnly = true
		tournamentRuntime.seatAssignments[minerID] = assignment
	}
	tournamentRuntime.liveTables = make(map[string]map[string]any)

	for minerID, entrant := range waveRuntime.entrants {
		if entrant.TournamentID != tournamentRuntime.id {
			continue
		}
		entrant.UpdatedAt = now
		if rank := finishRanks[minerID]; rank > 0 {
			entrant.FinishRank = rank
		}
		if stage := stageReached[minerID]; stage != "" {
			entrant.StageReached = stage
		}
		entrant.TableID = ""
		entrant.SeatID = ""
		switch {
		case entrant.RegistrationState == model.RegistrationStateDisqualified:
			// Preserve disqualification truth while still freezing placement metadata.
		case len(assignments) == 1 && minerID == assignments[0].MinerID:
			entrant.RegistrationState = model.RegistrationStateChampion
		default:
			entrant.RegistrationState = model.RegistrationStateEliminated
		}
		if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
			return err
		}
		waveRuntime.entrants[minerID] = entrant
	}

	if s.rating != nil && len(completion.Entrants) > 0 {
		if err := s.rating.OnTournamentCompleted(ctx, completion); err != nil {
			return fmt.Errorf("persist tournament completion rating outcome: %w", err)
		}
	}

	for tableID, actor := range s.actors {
		if actor.State().TournamentID != tournamentRuntime.id {
			continue
		}
		delete(s.actors, tableID)
		if s.gateway != nil {
			s.gateway.RemoveActor(tableID)
		}
	}
	waveRuntime.liveHub = nil
	return nil
}

func (s *runtimeService) saveTournamentCompletionSnapshotLocked(ctx context.Context, tournamentRuntime *tournamentRuntime, currentRoundNo int, reason string) error {
	snapshotID := fmt.Sprintf("snap:%s:completed", tournamentRuntime.id)
	payload := mustJSON(map[string]any{
		"stage":              "completed",
		"completed_reason":   reason,
		"players_remaining":  tournamentRuntime.tournament.PlayersRemaining,
		"active_table_count": tournamentRuntime.tournament.ActiveTableCount,
		"round_no":           currentRoundNo,
		"level_no":           tournamentRuntime.tournament.CurrentLevelNo,
		"no_multiplier":      tournamentRuntime.tournament.NoMultiplier,
		"winner_miner_id":    tournamentRuntime.standing["winner_miner_id"],
		"final_standings":    tournamentRuntime.standing["final_standings"],
	})

	return s.repo.SaveTournamentSnapshot(ctx, model.TournamentSnapshot{
		ID:           snapshotID,
		TournamentID: tournamentRuntime.id,
		StreamKey:    fmt.Sprintf("tournament:%s", tournamentRuntime.id),
		StreamSeq:    int64(1_000_000 + currentRoundNo),
		StateSeq:     int64(currentRoundNo),
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			StateHash:           fmt.Sprintf("snapshot-state:%s:completed", tournamentRuntime.id),
			PayloadHash:         fmt.Sprintf("snapshot-payload:%s:completed", tournamentRuntime.id),
		},
		Payload:   payload,
		CreatedAt: s.now(),
	})
}

func (s *runtimeService) buildTournamentCompletionLocked(ctx context.Context, waveRuntime *waveRuntime, tournamentRuntime *tournamentRuntime, assignments []hub.SeatAssignment, reason string) (rating.Completion, map[string]int, map[string]string, []model.EliminationEvent, error) {
	entrants := tournamentEntrantsForCompletion(waveRuntime, tournamentRuntime.id)
	finishRanks := make(map[string]int, len(entrants))
	stageReached := make(map[string]string, len(entrants))
	if len(entrants) == 0 {
		return rating.Completion{}, finishRanks, stageReached, nil, nil
	}

	entrantByID := make(map[string]model.Entrant, len(entrants))
	entrantByMiner := make(map[string]model.Entrant, len(entrants))
	for _, entrant := range entrants {
		entrantByID[entrant.ID] = entrant
		entrantByMiner[entrant.MinerID] = entrant
	}

	seats, err := s.repo.ListSeatsByTournament(ctx, tournamentRuntime.id)
	if err != nil {
		return rating.Completion{}, nil, nil, nil, err
	}
	seatByID := make(map[string]model.Seat, len(seats))
	stackByEntrantID := make(map[string]int64, len(seats))
	for _, seat := range seats {
		seatByID[seat.ID] = seat
		if seat.EntrantID != "" {
			stackByEntrantID[seat.EntrantID] = seat.Stack
		}
	}

	survivors := rankedSurvivors(assignments, seatByID)
	usedRanks := make(map[int]struct{}, len(entrants))
	rankSourceByMiner := make(map[string]string, len(entrants))
	rankTiebreakByMiner := make(map[string]any, len(entrants))
	for idx, survivor := range survivors {
		rank := idx + 1
		finishRanks[survivor.MinerID] = rank
		rankSourceByMiner[survivor.MinerID] = "survivor_stack_desc"
		rankTiebreakByMiner[survivor.MinerID] = map[string]any{
			"final_stack": survivor.Stack,
			"miner_id":    survivor.MinerID,
		}
		usedRanks[rank] = struct{}{}
	}

	eliminationEvents, err := s.repo.ListEliminationEventsByTournament(ctx, tournamentRuntime.id)
	if err != nil {
		return rating.Completion{}, nil, nil, nil, err
	}
	sortEliminationEventsForRanking(eliminationEvents)
	for idx := range eliminationEvents {
		event := eliminationEvents[idx]
		entrant, ok := entrantByID[event.EntrantID]
		if !ok || entrant.MinerID == "" {
			continue
		}
		rank := len(entrants) - idx
		finishRanks[entrant.MinerID] = rank
		rankSourceByMiner[entrant.MinerID] = "elimination_order"
		rankTiebreakByMiner[entrant.MinerID] = map[string]any{
			"occurred_at": event.OccurredAt.UTC().Format(time.RFC3339Nano),
			"created_at":  event.CreatedAt.UTC().Format(time.RFC3339Nano),
			"table_id":    event.TableID,
			"entrant_id":  event.EntrantID,
		}
		usedRanks[rank] = struct{}{}
		eliminationEvents[idx].FinishRank = rank
	}

	remainingRanks := make([]int, 0)
	for rank := 1; rank <= len(entrants); rank++ {
		if _, used := usedRanks[rank]; used {
			continue
		}
		remainingRanks = append(remainingRanks, rank)
	}
	missingMinerIDs := make([]string, 0)
	for _, entrant := range entrants {
		if finishRanks[entrant.MinerID] != 0 {
			continue
		}
		missingMinerIDs = append(missingMinerIDs, entrant.MinerID)
	}
	sort.Strings(missingMinerIDs)
	for idx, minerID := range missingMinerIDs {
		if idx >= len(remainingRanks) {
			break
		}
		finishRanks[minerID] = remainingRanks[idx]
		rankSourceByMiner[minerID] = "fallback_miner_id"
		rankTiebreakByMiner[minerID] = map[string]any{
			"miner_id": minerID,
		}
	}

	measurementSummaries, err := s.repo.ListActionMeasurementSummaries(ctx, tournamentRuntime.id)
	if err != nil {
		return rating.Completion{}, nil, nil, nil, err
	}
	measurementByMiner := make(map[string]model.ActionMeasurementSummary, len(measurementSummaries))
	for _, summary := range measurementSummaries {
		measurementByMiner[summary.MinerID] = summary
	}

	completedEntrants := make([]rating.CompletedEntrant, 0, len(entrants))
	for _, entrant := range entrants {
		rank := finishRanks[entrant.MinerID]
		stage := stageReachedForPlacement(reason, entrant.StageReached, entrant.RegistrationState, len(entrants), rank, len(survivors))
		stageReached[entrant.MinerID] = stage
		finalStack := stackByEntrantID[entrant.ID]
		percentile := finishPercentile(len(entrants), rank)
		measurement := measurementByMiner[entrant.MinerID]
		rankSource := rankSourceByMiner[entrant.MinerID]
		rankTiebreaker := rankTiebreakByMiner[entrant.MinerID]
		completedEntrants = append(completedEntrants, rating.CompletedEntrant{
			EntrantID:           entrant.ID,
			MinerAddress:        entrant.MinerID,
			Name:                entrant.MinerID,
			EconomicUnitID:      entrant.EconomicUnitID,
			FinishRank:          rank,
			FinishPercentile:    percentile,
			HandsPlayed:         measurement.HandsPlayed,
			MeaningfulDecisions: measurement.MeaningfulDecisions,
			AutoActions:         measurement.AutoActions,
			TimeoutActions:      measurement.TimeoutActions,
			InvalidActions:      measurement.InvalidActions,
			StageReached:        stage,
			StackPathSummary: mustJSON(map[string]any{
				"final_stack": finalStack,
			}),
			ScoreComponents: mustJSON(map[string]any{
				"field_size":           len(entrants),
				"finish_percentile":    percentile,
				"finish_rank":          rank,
				"final_stack":          finalStack,
				"rank_source":          rankSource,
				"rank_tiebreaker":      rankTiebreaker,
				"survivor_count":       len(survivors),
				"completed_reason":     reason,
				"hands_played":         measurement.HandsPlayed,
				"meaningful_decisions": measurement.MeaningfulDecisions,
				"auto_actions":         measurement.AutoActions,
				"timeout_actions":      measurement.TimeoutActions,
				"invalid_actions":      measurement.InvalidActions,
			}),
			Penalties: mustJSON(map[string]any{
				"time_cap_finish": reason == "time_cap",
				"timeout_actions": measurement.TimeoutActions,
				"invalid_actions": measurement.InvalidActions,
			}),
			TournamentScore:   percentile,
			ConfidenceWeight:  completionConfidenceWeight(reason),
			TimeCapAdjustment: completionTimeCapAdjustment(reason),
			Payload: mustJSON(map[string]any{
				"completed_reason":     reason,
				"final_stack":          finalStack,
				"rank_source":          rankSource,
				"rank_tiebreaker":      rankTiebreaker,
				"hands_played":         measurement.HandsPlayed,
				"meaningful_decisions": measurement.MeaningfulDecisions,
				"auto_actions":         measurement.AutoActions,
				"timeout_actions":      measurement.TimeoutActions,
				"invalid_actions":      measurement.InvalidActions,
			}),
		})
	}
	sort.Slice(completedEntrants, func(i, j int) bool {
		if completedEntrants[i].FinishRank == completedEntrants[j].FinishRank {
			return completedEntrants[i].MinerAddress < completedEntrants[j].MinerAddress
		}
		return completedEntrants[i].FinishRank < completedEntrants[j].FinishRank
	})

	return rating.Completion{
		TournamentID:       tournamentRuntime.id,
		Mode:               tournamentRuntime.tournament.Mode,
		HumanOnly:          tournamentRuntime.tournament.HumanOnly,
		NoMultiplier:       tournamentRuntime.tournament.NoMultiplier,
		NoMultiplierReason: standingNoMultiplierReason(tournamentRuntime.standing),
		CompletedAt:        s.now(),
		ConfidenceWeight:   completionConfidenceWeight(reason),
		Entrants:           completedEntrants,
	}, finishRanks, stageReached, eliminationEvents, nil
}

type rankedSurvivor struct {
	MinerID string
	Stack   int64
}

func rankedSurvivors(assignments []hub.SeatAssignment, seatByID map[string]model.Seat) []rankedSurvivor {
	survivors := make([]rankedSurvivor, 0, len(assignments))
	for _, assignment := range assignments {
		stack := int64(0)
		if seat, ok := seatByID[seatID(assignment.TableID, assignment.SeatNo)]; ok {
			stack = seat.Stack
		}
		survivors = append(survivors, rankedSurvivor{
			MinerID: assignment.MinerID,
			Stack:   stack,
		})
	}
	sort.Slice(survivors, func(i, j int) bool {
		if survivors[i].Stack == survivors[j].Stack {
			return survivors[i].MinerID < survivors[j].MinerID
		}
		return survivors[i].Stack > survivors[j].Stack
	})
	return survivors
}

func tournamentEntrantsForCompletion(waveRuntime *waveRuntime, tournamentID string) []model.Entrant {
	entrants := make([]model.Entrant, 0)
	for _, entrant := range waveRuntime.entrants {
		if entrant.TournamentID != tournamentID {
			continue
		}
		entrants = append(entrants, entrant)
	}
	sort.Slice(entrants, func(i, j int) bool {
		return entrants[i].MinerID < entrants[j].MinerID
	})
	return entrants
}

func sortEliminationEventsForRanking(events []model.EliminationEvent) {
	sort.Slice(events, func(i, j int) bool {
		if !events[i].OccurredAt.Equal(events[j].OccurredAt) {
			return events[i].OccurredAt.Before(events[j].OccurredAt)
		}
		if events[i].CreatedAt != events[j].CreatedAt {
			return events[i].CreatedAt.Before(events[j].CreatedAt)
		}
		if events[i].TableID == events[j].TableID {
			return events[i].EntrantID < events[j].EntrantID
		}
		return events[i].TableID < events[j].TableID
	})
}

func finishPercentile(fieldSize, finishRank int) float64 {
	if fieldSize <= 1 {
		return 1
	}
	if finishRank <= 1 {
		return 1
	}
	if finishRank >= fieldSize {
		return 0
	}
	return float64(fieldSize-finishRank) / float64(fieldSize-1)
}

func stageReachedForPlacement(reason, existing string, registrationState model.RegistrationState, fieldSize, finishRank, survivorCount int) string {
	if registrationState == model.RegistrationStateDisqualified || existing == "disqualified" {
		return "disqualified"
	}
	if reason == "time_cap" {
		if finishRank > 0 && finishRank <= survivorCount {
			return "time_cap_finish"
		}
		if existing != "" {
			return existing
		}
		return "eliminated"
	}
	if finishRank == 1 && survivorCount == 1 {
		return "completed"
	}
	if finishRank > 0 && finishRank <= minInt(fieldSize, 9) {
		return "final_table"
	}
	if existing != "" {
		return existing
	}
	return "eliminated"
}

func completionConfidenceWeight(reason string) float64 {
	if reason == "time_cap" {
		return 0.5
	}
	return 1.0
}

func completionTimeCapAdjustment(reason string) float64 {
	if reason == "time_cap" {
		return -0.10
	}
	return 0
}

func standingNoMultiplierReason(standing map[string]any) string {
	if standing == nil {
		return ""
	}
	value, ok := standing["no_multiplier_reason"].(string)
	if !ok {
		return ""
	}
	return value
}

func minInt(left, right int) int {
	if left < right {
		return left
	}
	return right
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
		if entrant.TournamentID != tournamentID || !entrantParticipatesInPlay(entrant) || entrant.TableID == "" || entrant.SeatID == "" {
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

func seatAssignmentsFromEntrantsAndTruth(entrants []model.Entrant, seats []model.Seat, eliminations []model.EliminationEvent, tournament model.Tournament) map[string]httpapi.SeatAssignment {
	entrantByMiner := make(map[string]model.Entrant)
	for _, entrant := range entrants {
		if entrant.TournamentID != tournament.ID {
			continue
		}
		entrantByMiner[entrant.MinerID] = entrant
	}

	latestSeatByMiner := make(map[string]model.Seat)
	for _, seat := range seats {
		if seat.TournamentID != tournament.ID || seat.MinerID == "" {
			continue
		}
		current, ok := latestSeatByMiner[seat.MinerID]
		if ok && !seat.UpdatedAt.After(current.UpdatedAt) && !seat.CreatedAt.After(current.CreatedAt) {
			continue
		}
		latestSeatByMiner[seat.MinerID] = seat
	}

	latestEliminationByEntrant := make(map[string]model.EliminationEvent)
	for _, event := range eliminations {
		if event.TournamentID != tournament.ID || event.EntrantID == "" {
			continue
		}
		current, ok := latestEliminationByEntrant[event.EntrantID]
		if ok && !event.OccurredAt.After(current.OccurredAt) && !event.CreatedAt.After(current.CreatedAt) {
			continue
		}
		latestEliminationByEntrant[event.EntrantID] = event
	}

	assignments := make(map[string]httpapi.SeatAssignment)
	for minerID, entrant := range entrantByMiner {
		if !entrantSupportsSeatHydrate(entrant) {
			continue
		}
		if entrant.RegistrationState == model.RegistrationStateEliminated || entrant.RegistrationState == model.RegistrationStateDisqualified {
			if event, ok := latestEliminationByEntrant[entrant.ID]; ok && event.TableID != "" && event.SeatID != "" {
				assignments[minerID] = httpapi.SeatAssignment{
					TableID:  event.TableID,
					SeatNo:   seatNoFromSeatID(event.SeatID),
					StateSeq: 0,
					ReadOnly: true,
				}
				continue
			}
		}
		seat, ok := latestSeatByMiner[minerID]
		if !ok {
			continue
		}
		assignments[minerID] = httpapi.SeatAssignment{
			TableID:  seat.TableID,
			SeatNo:   seat.SeatNo,
			StateSeq: 0,
			ReadOnly: !entrantCanWrite(tournament.State, entrant.RegistrationState),
		}
	}
	return assignments
}

func entrantParticipatesInPlay(entrant model.Entrant) bool {
	switch entrant.RegistrationState {
	case model.RegistrationStateSeated, model.RegistrationStatePlaying:
		return true
	default:
		return false
	}
}

func entrantSupportsSeatHydrate(entrant model.Entrant) bool {
	switch entrant.RegistrationState {
	case model.RegistrationStateSeated, model.RegistrationStatePlaying, model.RegistrationStateEliminated, model.RegistrationStateChampion, model.RegistrationStateDisqualified:
		return true
	default:
		return false
	}
}

func entrantCanWrite(tournamentState model.TournamentState, registrationState model.RegistrationState) bool {
	return tournamentAcceptsPlay(tournamentState) && registrationState == model.RegistrationStatePlaying
}

func (s *runtimeService) appendFieldExitEventLocked(ctx context.Context, tournamentID string, entrant model.Entrant, stageReached string) (string, error) {
	if entrant.ID == "" || entrant.TableID == "" || entrant.SeatID == "" {
		return "", nil
	}
	eventID := fmt.Sprintf("field_exit:%s", entrant.ID)
	if err := s.repo.AppendEliminationEvents(ctx, []model.EliminationEvent{{
		ID:           eventID,
		TournamentID: tournamentID,
		TableID:      entrant.TableID,
		SeatID:       entrant.SeatID,
		EntrantID:    entrant.ID,
		StageReached: stageReached,
		OccurredAt:   s.now(),
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			StateHash:           fmt.Sprintf("elimination-state:%s", eventID),
			PayloadHash:         fmt.Sprintf("elimination-payload:%s", eventID),
		},
		Payload:   mustJSON(map[string]any{"source": "runtime_sync", "stage_reached": stageReached}),
		CreatedAt: s.now(),
	}}); err != nil {
		return "", err
	}
	return eventID, nil
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

func (s *runtimeService) liveTablesForTournament(tournamentID string) []hub.LiveTable {
	liveTables := make([]hub.LiveTable, 0)
	for tableID, actor := range s.actors {
		state := actor.State()
		if state.TournamentID != tournamentID {
			continue
		}
		playerCount := 0
		for _, seat := range state.Table.Seats {
			if seat.State != table.SeatStateEliminated {
				playerCount++
			}
		}
		if playerCount == 0 {
			continue
		}
		liveTables = append(liveTables, hub.LiveTable{
			TableID:     tableID,
			PlayerCount: playerCount,
		})
	}
	sort.Slice(liveTables, func(i, j int) bool {
		return liveTables[i].TableID < liveTables[j].TableID
	})
	return liveTables
}

func (s *runtimeService) resetLiveHubLocked(waveRuntime *waveRuntime, tournamentID string, playersRemaining int, liveTables []hub.LiveTable, assignments []hub.SeatAssignment) {
	s.resetLiveHubWithBarrierLocked(waveRuntime, tournamentID, playersRemaining, liveTables, assignments, nil)
}

func (s *runtimeService) resetLiveHubWithBarrierLocked(waveRuntime *waveRuntime, tournamentID string, playersRemaining int, liveTables []hub.LiveTable, assignments []hub.SeatAssignment, closedTables map[string]bool) {
	if closedTables == nil {
		closedTables = map[string]bool{}
	}
	waveRuntime.liveHub = hub.NewService(hub.State{
		TournamentID:     tournamentID,
		PlayersRemaining: playersRemaining,
		LiveTables:       liveTables,
		ClosedTables:     closedTables,
		Tournaments: []hub.TournamentPlan{{
			TournamentID:    tournamentID,
			SeatAssignments: assignments,
		}},
	}, nil)
	if tournamentID == "" || waveRuntime.liveHub == nil {
		return
	}
	if tournamentRuntime, ok := s.tournaments[tournamentID]; ok && tournamentRuntime.tournament.TimeCapAt != nil {
		waveRuntime.liveHub.ArmTimeCap()
	}
}

func closedTablesFromBarrier(barrier model.RoundBarrier) map[string]bool {
	if len(barrier.Payload) == 0 {
		return nil
	}
	var payload roundBarrierPayload
	if err := json.Unmarshal(barrier.Payload, &payload); err != nil {
		return nil
	}
	if len(payload.ClosedTableIDs) == 0 {
		return nil
	}
	closedTables := make(map[string]bool, len(payload.ClosedTableIDs))
	for _, tableID := range payload.ClosedTableIDs {
		if tableID == "" {
			continue
		}
		closedTables[tableID] = true
	}
	return closedTables
}

func (s *runtimeService) persistRoundBarrierLocked(ctx context.Context, waveRuntime *waveRuntime, tournamentRuntime *tournamentRuntime) error {
	if waveRuntime == nil || waveRuntime.liveHub == nil || tournamentRuntime == nil {
		return nil
	}
	roundNo := roundNoForTournament(tournamentRuntime.tournament)
	closedTableIDs := waveRuntime.liveHub.ClosedTableIDs()
	return s.repo.UpsertRoundBarrier(ctx, model.RoundBarrier{
		ID:                         model.BarrierID(tournamentRuntime.id, roundNo),
		TournamentID:               tournamentRuntime.id,
		RoundNo:                    roundNo,
		ExpectedTableCount:         len(liveTablesForHub(s.currentAssignmentsForTournamentLocked(waveRuntime, tournamentRuntime.id))),
		ReceivedHandCloseCount:     len(closedTableIDs),
		BarrierState:               "open",
		PendingLevelNo:             tournamentRuntime.tournament.CurrentLevelNo,
		TerminateAfterCurrentRound: waveRuntime.liveHub.TerminateAfterCurrentRound(),
		TruthMetadata:              truthMetadata(model.BarrierID(tournamentRuntime.id, roundNo)),
		Payload:                    mustJSON(roundBarrierPayload{ClosedTableIDs: closedTableIDs}),
		CreatedAt:                  s.now(),
		UpdatedAt:                  s.now(),
	})
}

func (s *runtimeService) currentAssignmentsForTournamentLocked(waveRuntime *waveRuntime, tournamentID string) []hub.SeatAssignment {
	assignments := make([]hub.SeatAssignment, 0)
	tournamentRuntime := s.tournaments[tournamentID]
	for _, entrant := range waveRuntime.entrants {
		if entrant.TournamentID != tournamentID || entrant.TableID == "" || entrant.SeatID == "" {
			continue
		}
		if tournamentRuntime != nil {
			if _, blocked := tournamentRuntime.pendingDisqualifications[entrant.MinerID]; blocked {
				continue
			}
		}
		actor := s.actors[entrant.TableID]
		if actor == nil {
			continue
		}
		seatNo := seatNoFromSeatID(entrant.SeatID)
		seat, ok := actor.State().Table.Seats[seatNo]
		if !ok || seat.State == table.SeatStateEliminated {
			continue
		}
		assignments = append(assignments, hub.SeatAssignment{
			EntrantID: entrant.ID,
			MinerID:   entrant.MinerID,
			TableID:   entrant.TableID,
			TableNo:   tableNoFromTableID(entrant.TableID),
			SeatNo:    seatNo,
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

func (s *runtimeService) startNextRoundLocked(ctx context.Context, tournamentRuntime *tournamentRuntime, nextRoundNo int) (map[string]table.ActorState, error) {
	states := make(map[string]table.ActorState)
	liveTables := s.liveTablesForTournament(tournamentRuntime.id)
	playerCountByTable := make(map[string]int, len(liveTables))
	for _, liveTable := range liveTables {
		playerCountByTable[liveTable.TableID] = liveTable.PlayerCount
	}
	for tableID, actor := range s.actors {
		if actor.State().TournamentID != tournamentRuntime.id {
			continue
		}
		state, err := s.startNextHandLocked(ctx, actor, tableID, tournamentRuntime.id, nextRoundNo, false)
		if err != nil {
			return nil, err
		}
		view := tableViewFromActorState(state)
		view["player_count"] = playerCountByTable[tableID]
		tournamentRuntime.liveTables[tableID] = view
		updateSeatAssignmentSeq(tournamentRuntime, tableID, state.StateSeq)
		states[tableID] = state
	}
	return states, nil
}

func (s *runtimeService) applyTransitionPlanLocked(ctx context.Context, waveRuntime *waveRuntime, tournamentRuntime *tournamentRuntime, plan hub.TransitionPlan, nextRoundNo int) (map[string]table.ActorState, error) {
	existingSnapshots, err := s.repo.LoadLatestTableSnapshots(ctx, tournamentRuntime.id)
	if err != nil {
		return nil, err
	}
	snapshotByTable := make(map[string]model.TableSnapshot, len(existingSnapshots))
	for _, snapshot := range existingSnapshots {
		snapshotByTable[snapshot.TableID] = snapshot
	}

	carriedByMiner := make(map[string]table.Seat)
	streamSeqByTable := make(map[string]int64)
	stateSeqByTable := make(map[string]int64)
	for _, entrant := range waveRuntime.entrants {
		if entrant.TournamentID != tournamentRuntime.id || entrant.TableID == "" || entrant.SeatID == "" {
			continue
		}
		actor := s.actors[entrant.TableID]
		if actor == nil {
			continue
		}
		seatNo := seatNoFromSeatID(entrant.SeatID)
		seat, ok := actor.State().Table.Seats[seatNo]
		if ok {
			carriedByMiner[entrant.MinerID] = seat
		}
	}
	for tableID, actor := range s.actors {
		if actor.State().TournamentID != tournamentRuntime.id {
			continue
		}
		streamSeqByTable[tableID] = actor.StreamSeq()
		stateSeqByTable[tableID] = actor.State().StateSeq
		delete(s.actors, tableID)
		if s.gateway != nil {
			s.gateway.RemoveActor(tableID)
		}
	}

	previousSeatAssignments := make(map[string]httpapi.SeatAssignment, len(tournamentRuntime.seatAssignments))
	for minerID, assignment := range tournamentRuntime.seatAssignments {
		assignment.ReadOnly = true
		previousSeatAssignments[minerID] = assignment
	}
	tournamentRuntime.seatAssignments = make(map[string]httpapi.SeatAssignment)
	for minerID, assignment := range previousSeatAssignments {
		tournamentRuntime.seatAssignments[minerID] = assignment
	}
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

	states := make(map[string]table.ActorState, len(tableIDs))
	level := blindLevelForRound(nextRoundNo)
	for _, tableID := range tableIDs {
		assignments := grouped[tableID]
		sort.Slice(assignments, func(i, j int) bool { return assignments[i].SeatNo < assignments[j].SeatNo })
		previous := snapshotByTable[tableID]
		streamSeq := streamSeqByTable[tableID]
		if streamSeq == 0 {
			streamSeq = previous.StreamSeq
		}
		stateSeq := stateSeqByTable[tableID]
		if stateSeq == 0 {
			stateSeq = previous.StateSeq
		}
		state := table.State{
			CurrentPhase: table.PhaseSignal,
			HandNumber:   nextRoundNo - 1,
			Seats:        make(map[int]table.Seat, len(assignments)),
		}
		for _, assignment := range assignments {
			carried, ok := carriedByMiner[assignment.MinerID]
			if !ok {
				return nil, fmt.Errorf("missing carried seat for miner %s during transition", assignment.MinerID)
			}
			if carried.Stack <= 0 {
				return nil, fmt.Errorf("non-positive carried stack for miner %s during transition", assignment.MinerID)
			}
			carried.SeatNo = assignment.SeatNo
			carried.Folded = false
			carried.AllInThisHand = false
			carried.TimedOutThisHand = false
			carried.ManualActionThisHand = false
			carried.CommittedThisHand = 0
			carried.WonThisHand = 0
			carried.ShowdownValue = 0
			state.Seats[assignment.SeatNo] = carried
			entrant := waveRuntime.entrants[assignment.MinerID]
			entrant.TableID = assignment.TableID
			entrant.SeatID = seatID(assignment.TableID, assignment.SeatNo)
			entrant.RegistrationState = model.RegistrationStatePlaying
			entrant.UpdatedAt = s.now()
			if err := s.repo.UpsertEntrant(ctx, entrant); err != nil {
				return nil, err
			}
			waveRuntime.entrants[assignment.MinerID] = entrant
			if err := s.repo.UpsertSeat(ctx, model.Seat{
				ID:                      entrant.SeatID,
				TableID:                 assignment.TableID,
				TournamentID:            tournamentRuntime.id,
				EntrantID:               entrant.ID,
				SeatNo:                  assignment.SeatNo,
				SeatAlias:               entrant.SeatAlias,
				MinerID:                 entrant.MinerID,
				State:                   model.SeatState(carried.State),
				Stack:                   carried.Stack,
				TimeoutStreak:           carried.TimeoutStreak,
				SitOutWarningCount:      carried.SitOutWarningCount,
				TournamentSeatDrawToken: fmt.Sprintf("draw:%s:%02d", tournamentRuntime.id, assignment.SeatNo),
				TruthMetadata:           truthMetadata(entrant.SeatID),
				Payload:                 mustJSON(carried),
				CreatedAt:               s.now(),
				UpdatedAt:               s.now(),
			}); err != nil {
				return nil, err
			}
			tournamentRuntime.seatAssignments[assignment.MinerID] = httpapi.SeatAssignment{
				TableID:  assignment.TableID,
				SeatNo:   assignment.SeatNo,
				ReadOnly: false,
			}
		}
		nextState, _, err := table.Apply(state, table.StartHand{
			SmallBlind: level.SmallBlind,
			BigBlind:   level.BigBlind,
			Ante:       level.Ante,
			MinRaiseTo: minRaiseToForLevel(level),
		})
		if err != nil {
			return nil, err
		}
		state = nextState

		actor := table.NewRecoveredActor(table.ActorState{
			TableID:      tableID,
			TournamentID: tournamentRuntime.id,
			HandID:       model.HandID(tournamentRuntime.id, tableNoFromTableID(tableID), state.HandNumber),
			StateSeq:     stateSeq,
			Table:        state,
		}, streamSeq, runtimeClock{now: s.now}, s.repo)
		deadlineAt := s.now().Add(30 * time.Second)
		if err := actor.OpenPhase(ctx, table.PhaseDefinition{
			ID:         model.PhaseID(model.HandID(tournamentRuntime.id, tableNoFromTableID(tableID), state.HandNumber), model.PhaseTypeSignal),
			HandID:     model.HandID(tournamentRuntime.id, tableNoFromTableID(tableID), state.HandNumber),
			Type:       table.PhaseSignal,
			ActingSeat: state.ActingSeatNo,
			ToCall:     state.CurrentToCall,
			DeadlineAt: &deadlineAt,
		}); err != nil {
			return nil, err
		}
		s.actors[tableID] = actor
		if s.gateway != nil {
			s.gateway.RegisterActor(tableID, actor)
		}
		actorState := actor.State()
		if err := s.repo.UpsertTable(ctx, tableRowFromActor(actorState, nextRoundNo, plan.Decision == hub.TransitionFinalTable, s.now)); err != nil {
			return nil, err
		}
		view := tableViewFromActorState(actorState)
		view["player_count"] = len(assignments)
		tournamentRuntime.liveTables[tableID] = view
		updateSeatAssignmentSeq(tournamentRuntime, tableID, actorState.StateSeq)
		states[tableID] = actorState
	}
	s.resetLiveHubLocked(waveRuntime, tournamentRuntime.id, len(plan.SeatAssignments), liveTablesForHub(plan.SeatAssignments), plan.SeatAssignments)
	return states, nil
}

func (s *runtimeService) startNextHandLocked(ctx context.Context, actor *table.Actor, tableID, tournamentID string, roundNo int, finalTable bool) (table.ActorState, error) {
	before := actor.State()
	level := blindLevelForRound(roundNo)
	if _, err := actor.Handle(ctx, table.CommandEnvelope{
		RequestID:        fmt.Sprintf("sys:start:%s:%d", tableID, roundNo),
		ExpectedStateSeq: before.StateSeq,
		Command: table.StartHand{
			SmallBlind: level.SmallBlind,
			BigBlind:   level.BigBlind,
			Ante:       level.Ante,
			MinRaiseTo: minRaiseToForLevel(level),
		},
	}); err != nil {
		return table.ActorState{}, err
	}
	state := actor.State()
	handID := model.HandID(tournamentID, tableNoFromTableID(tableID), state.Table.HandNumber)
	deadlineAt := s.now().Add(30 * time.Second)
	if err := actor.OpenPhase(ctx, table.PhaseDefinition{
		ID:         model.PhaseID(handID, model.PhaseTypeSignal),
		HandID:     handID,
		Type:       table.PhaseSignal,
		ActingSeat: firstSeatForOpenedPhase(state.Table),
		ToCall:     state.Table.CurrentToCall,
		DeadlineAt: &deadlineAt,
	}); err != nil {
		return table.ActorState{}, err
	}
	state = actor.State()
	if err := s.repo.UpsertTable(ctx, tableRowFromActor(state, roundNo, finalTable, s.now)); err != nil {
		return table.ActorState{}, err
	}
	return state, nil
}

func tableRowFromActor(state table.ActorState, roundNo int, finalTable bool, now func() time.Time) model.Table {
	timestamp := time.Now().UTC()
	if now != nil {
		timestamp = now().UTC()
	}
	level := blindLevelForRound(roundNo)
	return model.Table{
		ID:            state.TableID,
		TournamentID:  state.TournamentID,
		State:         tableModelState(state.Table),
		TableNo:       tableNoFromTableID(state.TableID),
		RoundNo:       roundNo,
		CurrentHandID: state.HandID,
		ActingSeatNo:  state.Table.ActingSeatNo,
		CurrentToCall: state.Table.CurrentToCall,
		MinRaiseSize:  state.Table.MinRaiseSize,
		PotMain:       state.Table.PotMain,
		StateSeq:      state.StateSeq,
		LevelNo:       level.LevelNo,
		IsFinalTable:  finalTable,
		TruthMetadata: truthMetadata(state.TableID),
		Payload:       mustJSON(state.Table),
		CreatedAt:     timestamp,
		UpdatedAt:     timestamp,
	}
}

func standingFromTournament(tournament model.Tournament) map[string]any {
	roundNo := roundNoForTournament(tournament)
	levelNo := tournament.CurrentLevelNo
	if levelNo == 0 {
		levelNo = blindLevelForRound(roundNo).LevelNo
	}
	standing := map[string]any{
		"players_remaining": tournament.PlayersRemaining,
		"round_no":          roundNo,
		"level_no":          levelNo,
		"state":             string(tournament.State),
		"no_multiplier":     tournament.NoMultiplier,
	}
	if tournament.TimeCapAt != nil {
		standing["terminate_after_current_round"] = true
	}
	if tournament.State == model.TournamentStateCompleted {
		standing["status"] = "completed"
	}
	if tournament.Voided {
		standing["status"] = "voided"
	}
	return standing
}

func finalStandingEntries(entrants []rating.CompletedEntrant) []map[string]any {
	entries := make([]map[string]any, 0, len(entrants))
	for _, entrant := range entrants {
		components := jsonObjectFromRaw(entrant.ScoreComponents)
		entry := map[string]any{
			"miner_id":             entrant.MinerAddress,
			"entrant_id":           entrant.EntrantID,
			"finish_rank":          entrant.FinishRank,
			"finish_percentile":    entrant.FinishPercentile,
			"stage_reached":        entrant.StageReached,
			"hands_played":         entrant.HandsPlayed,
			"meaningful_decisions": entrant.MeaningfulDecisions,
			"auto_actions":         entrant.AutoActions,
			"timeout_actions":      entrant.TimeoutActions,
			"invalid_actions":      entrant.InvalidActions,
			"tournament_score":     entrant.TournamentScore,
			"confidence_weight":    entrant.ConfidenceWeight,
			"time_cap_adjustment":  entrant.TimeCapAdjustment,
			"economic_unit_id":     entrant.EconomicUnitID,
		}
		if rankSource, ok := components["rank_source"]; ok {
			entry["rank_source"] = rankSource
		}
		if rankTiebreaker, ok := components["rank_tiebreaker"]; ok {
			entry["rank_tiebreaker"] = rankTiebreaker
		}
		if finalStack, ok := finalStackFromSummary(entrant.StackPathSummary); ok {
			entry["final_stack"] = finalStack
		}
		entries = append(entries, entry)
	}
	return entries
}

func finalStackFromSummary(payload json.RawMessage) (int64, bool) {
	if len(payload) == 0 {
		return 0, false
	}
	var summary struct {
		FinalStack int64 `json:"final_stack"`
	}
	if err := json.Unmarshal(payload, &summary); err != nil {
		return 0, false
	}
	return summary.FinalStack, true
}

func jsonObjectFromRaw(payload json.RawMessage) map[string]any {
	if len(payload) == 0 {
		return nil
	}
	var result map[string]any
	if err := json.Unmarshal(payload, &result); err != nil {
		return nil
	}
	return result
}

func refreshStanding(tournamentRuntime *tournamentRuntime) {
	if tournamentRuntime == nil {
		return
	}
	tournamentRuntime.standing = standingFromTournament(tournamentRuntime.tournament)
	if tournamentRuntime.disqualificationSeen {
		tournamentRuntime.standing["no_multiplier_reason"] = noMultiplierReasonLiveDQ
	}
}

func pendingDisqualificationsFromInterventions(interventions []model.OperatorIntervention) (map[string]model.OperatorIntervention, bool) {
	pending := make(map[string]model.OperatorIntervention)
	seen := false
	for _, intervention := range interventions {
		if intervention.InterventionType != interventionTypeDisqualify {
			continue
		}
		seen = true
		if intervention.Status != interventionStatusRequested || intervention.MinerID == "" {
			continue
		}
		pending[intervention.MinerID] = intervention
	}
	return pending, seen
}

func completionReason(tournament model.Tournament, liveHub *hub.Service, playersRemaining int) string {
	switch {
	case playersRemaining <= 1:
		return "natural_finish"
	case tournament.TimeCapAt != nil && liveHub != nil && liveHub.TerminateAfterCurrentRound():
		return "time_cap"
	default:
		return ""
	}
}

func tournamentAcceptsPlay(state model.TournamentState) bool {
	switch state {
	case model.TournamentStateReady,
		model.TournamentStateLiveMultiTable,
		model.TournamentStateRebalancing,
		model.TournamentStateFinalTableTransition,
		model.TournamentStateLiveFinalTable:
		return true
	default:
		return false
	}
}

func tableViewFromActorState(state table.ActorState) map[string]any {
	view := tableViewFromState(state.Table)
	view["state_seq"] = state.StateSeq
	return view
}

func tableViewFromState(state table.State) map[string]any {
	level := blindLevelForRound(state.HandNumber)
	return map[string]any{
		"acting_seat_no":      state.ActingSeatNo,
		"level_no":            level.LevelNo,
		"small_blind":         level.SmallBlind,
		"big_blind":           level.BigBlind,
		"ante":                level.Ante,
		"pot_main":            state.PotMain,
		"current_phase":       string(state.CurrentPhase),
		"current_to_call":     state.CurrentToCall,
		"min_raise_size":      state.MinRaiseSize,
		"hand_number":         state.HandNumber,
		"legal_actions":       legalActionsView(state),
		"min_raise_to":        minRaiseToView(state),
		"max_raise_to":        maxRaiseToView(state),
		"visible_stacks":      visibleStacksView(state),
		"seat_public_actions": seatPublicActionsView(state),
	}
}

func legalActionsView(state table.State) []any {
	seat, ok := state.Seats[state.ActingSeatNo]
	if !ok || seat.State == table.SeatStateEliminated || seat.Folded || seat.AllInThisHand {
		return []any{}
	}

	switch state.CurrentPhase {
	case table.PhaseSignal:
		return []any{string(table.ActionSignalNone)}
	case table.PhaseProbe:
		return []any{string(table.ActionPassProbe)}
	case table.PhaseWager:
		actions := make([]any, 0, 4)
		toCall := chipsToCallView(state, seat)
		if toCall == 0 {
			actions = append(actions, string(table.ActionCheck))
		}
		if toCall > 0 && toCall <= seat.Stack {
			actions = append(actions, string(table.ActionCall))
		}
		actions = append(actions, string(table.ActionFold))
		if canRaiseView(state, seat) {
			actions = append(actions, string(table.ActionRaise))
		}
		if seat.Stack > 0 {
			actions = append(actions, string(table.ActionAllIn))
		}
		return actions
	default:
		return []any{}
	}
}

func minRaiseToView(state table.State) int64 {
	seat, ok := state.Seats[state.ActingSeatNo]
	if !ok || !canRaiseView(state, seat) {
		return 0
	}

	minRaiseTo := state.CurrentToCall + 1
	if minRaiseTo < state.MinRaiseSize {
		minRaiseTo = state.MinRaiseSize
	}
	if minRaiseTo <= seat.CommittedThisHand {
		minRaiseTo = seat.CommittedThisHand + 1
	}
	return minRaiseTo
}

func maxRaiseToView(state table.State) int64 {
	seat, ok := state.Seats[state.ActingSeatNo]
	if !ok || !canRaiseView(state, seat) {
		return 0
	}
	return seat.CommittedThisHand + seat.Stack - 1
}

func canRaiseView(state table.State, seat table.Seat) bool {
	if state.CurrentPhase != table.PhaseWager || seat.Stack <= 0 {
		return false
	}

	minRaiseTo := state.CurrentToCall + 1
	if minRaiseTo < state.MinRaiseSize {
		minRaiseTo = state.MinRaiseSize
	}
	if minRaiseTo <= seat.CommittedThisHand {
		minRaiseTo = seat.CommittedThisHand + 1
	}
	raiseAmount := minRaiseTo - seat.CommittedThisHand
	return raiseAmount > 0 && raiseAmount < seat.Stack
}

func chipsToCallView(state table.State, seat table.Seat) int64 {
	if state.CurrentToCall <= seat.CommittedThisHand {
		return 0
	}
	return state.CurrentToCall - seat.CommittedThisHand
}

func visibleStacksView(state table.State) []any {
	seatNos := make([]int, 0, len(state.Seats))
	for seatNo := range state.Seats {
		seatNos = append(seatNos, seatNo)
	}
	sort.Ints(seatNos)

	items := make([]any, 0, len(seatNos))
	for _, seatNo := range seatNos {
		seat := state.Seats[seatNo]
		items = append(items, map[string]any{
			"seat_no":    seatNo,
			"seat_state": string(seat.State),
			"stack":      seat.Stack,
		})
	}
	return items
}

func seatPublicActionsView(state table.State) []any {
	seatNos := make([]int, 0, len(state.Seats))
	for seatNo := range state.Seats {
		seatNos = append(seatNos, seatNo)
	}
	sort.Ints(seatNos)

	items := make([]any, 0, len(seatNos))
	for _, seatNo := range seatNos {
		seat := state.Seats[seatNo]
		items = append(items, map[string]any{
			"seat_no":             seatNo,
			"committed_this_hand": seat.CommittedThisHand,
			"folded":              seat.Folded,
			"all_in":              seat.AllInThisHand,
			"timed_out_this_hand": seat.TimedOutThisHand,
			"manual_action":       seat.ManualActionThisHand,
		})
	}
	return items
}

func tableModelState(state table.State) model.TableState {
	if state.HandClosed {
		return model.TableStateAwaitingBarrier
	}
	return model.TableStateHandLive
}

func firstActiveSeat(state table.State) int {
	seatNos := make([]int, 0, len(state.Seats))
	for seatNo, seat := range state.Seats {
		if seat.State == table.SeatStateEliminated {
			continue
		}
		seatNos = append(seatNos, seatNo)
	}
	if len(seatNos) == 0 {
		return 0
	}
	sort.Ints(seatNos)
	return seatNos[0]
}

func firstSeatForOpenedPhase(state table.State) int {
	if state.ActingSeatNo != 0 {
		return state.ActingSeatNo
	}
	return firstActiveSeat(state)
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

func nextTurnPhaseID(handID string, phase table.Phase, stateSeq int64) string {
	return fmt.Sprintf("phase:%s:%s:%03d", handID, phase, stateSeq)
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
		output[key] = cloneValue(value)
	}
	return output
}

func cloneValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneMap(typed)
	case []any:
		out := make([]any, len(typed))
		for idx, item := range typed {
			out[idx] = cloneValue(item)
		}
		return out
	default:
		return value
	}
}

func mustJSON(value any) json.RawMessage {
	payload, err := json.Marshal(value)
	if err != nil {
		panic(err)
	}
	return payload
}
