package hub

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"time"

	"github.com/clawchain/clawchain/arena/model"
)

const seatsPerTable = 8

var (
	errContextRequired       = errors.New("context is required")
	errWaveNotOpen           = errors.New("wave is not registration_open")
	errNoPackedTournament    = errors.New("no packed tournament")
	errSeatsNotPublished     = errors.New("seats are not published")
	errRepublishAlreadyUsed  = errors.New("republish already used")
	errRepublishNotRequired  = errors.New("republish not required")
	errEntrantNotFound       = errors.New("entrant not found")
	errEntrantAlreadyRemoved = errors.New("entrant already removed")
)

type persistence interface {
	SaveTournamentSnapshot(ctx context.Context, snapshot model.TournamentSnapshot) error
	UpsertOperatorIntervention(ctx context.Context, intervention model.OperatorIntervention) error
	AppendReseatEvents(ctx context.Context, events []model.ReseatEvent) error
}

type noopStore struct{}

func (noopStore) SaveTournamentSnapshot(context.Context, model.TournamentSnapshot) error { return nil }
func (noopStore) UpsertOperatorIntervention(context.Context, model.OperatorIntervention) error {
	return nil
}
func (noopStore) AppendReseatEvents(context.Context, []model.ReseatEvent) error { return nil }

type Service struct {
	state State
	store persistence
	now   func() time.Time
}

func NewService(state State, store persistence) *Service {
	if store == nil {
		store = noopStore{}
	}

	nowFn := time.Now().UTC
	if !state.StartedAt.IsZero() {
		fixed := state.StartedAt.UTC()
		nowFn = func() time.Time { return fixed }
	}

	return &Service{
		state: state,
		store: store,
		now:   nowFn,
	}
}

func (s *Service) Result() PackResult {
	return s.state.result()
}

func (s *Service) MarkHandClosed(tableID string) {
	if s.state.ClosedTables == nil {
		s.state.ClosedTables = make(map[string]bool)
	}
	s.state.ClosedTables[tableID] = true
}

func (s *Service) CanAdvanceRound() bool {
	if len(s.state.LiveTables) == 0 {
		return false
	}
	if len(s.state.ClosedTables) < len(s.state.LiveTables) {
		return false
	}

	for _, table := range s.state.LiveTables {
		if !s.state.ClosedTables[table.TableID] {
			return false
		}
	}

	return true
}

func (s *Service) NextBarrierDecision() TransitionDecision {
	tableCount := len(s.state.LiveTables)
	if tableCount == 0 {
		return TransitionNone
	}
	if s.state.PlayersRemaining <= seatsPerTable && tableCount > 1 {
		return TransitionFinalTable
	}

	targetTables := targetTableCount(s.state.PlayersRemaining)
	switch {
	case targetTables < tableCount:
		return TransitionBreakTable
	case needsRebalance(s.state.LiveTables):
		return TransitionRebalance
	default:
		return TransitionNone
	}
}

func (s *Service) ArmTimeCap() {
	s.state.terminateAfterRound = true
	s.state.terminateAfterHand = false
}

func (s *Service) TerminateAfterCurrentRound() bool {
	return s.state.terminateAfterRound
}

func (s *Service) TerminateAfterCurrentHand() bool {
	return s.state.terminateAfterHand
}

func (s *Service) LockAndPack(ctx context.Context) (PackResult, error) {
	if ctx == nil {
		return PackResult{}, errContextRequired
	}
	if s.state.WaveState != model.WaveStateRegistrationOpen {
		return PackResult{}, errWaveNotOpen
	}

	entrants := s.state.activeEntrants()
	mode, noMultiplier := classifyShard(len(entrants))

	s.state.WaveState = model.WaveStateRegistrationFrozen
	s.state.WaveState = model.WaveStateFieldLocked

	tournamentID := model.TournamentID(s.state.WaveID, 1)
	plan := TournamentPlan{
		TournamentID:    tournamentID,
		RatedOrPractice: string(mode),
		NoMultiplier:    noMultiplier,
		EntrantIDs:      entrantIDs(entrants),
		SeatAssignments: assignSeats(tournamentID, entrants),
	}

	s.state.Tournaments = []TournamentPlan{plan}
	s.state.WaveState = model.WaveStateSeatingGenerated

	if err := s.persistSnapshots(ctx, "field_locked"); err != nil {
		return PackResult{}, err
	}

	return s.Result(), nil
}

func (s *Service) PublishSeats(ctx context.Context) error {
	if ctx == nil {
		return errContextRequired
	}
	if len(s.state.Tournaments) == 0 {
		return errNoPackedTournament
	}

	s.state.WaveState = model.WaveStateSeatsPublished
	for i := range s.state.Tournaments {
		s.state.Tournaments[i].SeatsWerePublished = true
	}

	return s.persistSnapshots(ctx, "seating_published")
}

func (s *Service) ForceRemoveBeforeStart(ctx context.Context, minerID string) error {
	if ctx == nil {
		return errContextRequired
	}
	if s.state.WaveState != model.WaveStateSeatsPublished {
		return errSeatsNotPublished
	}

	index := -1
	var removed model.Entrant
	for i, entrant := range s.state.Entrants {
		if entrant.MinerID != minerID {
			continue
		}
		if entrant.RegistrationState == model.RegistrationStateRemovedBeforeStart {
			return errEntrantAlreadyRemoved
		}
		index = i
		removed = entrant
		break
	}
	if index == -1 {
		return errEntrantNotFound
	}

	s.state.Entrants[index].RegistrationState = model.RegistrationStateRemovedBeforeStart
	s.state.pendingRepublish = true

	assignment, tournamentID := s.lookupAssignment(removed.ID)
	if err := s.store.UpsertOperatorIntervention(ctx, model.OperatorIntervention{
		ID:               fmt.Sprintf("ops:%s:%s", s.state.WaveID, minerID),
		TournamentID:     tournamentID,
		TableID:          assignment.TableID,
		SeatID:           seatID(assignment.TableID, assignment.SeatNo),
		MinerID:          minerID,
		InterventionType: "force_remove_before_start",
		Status:           "requested",
		RequestedBy:      "hub",
		RequestedAt:      s.now(),
		ReasonCode:       "forced_remove_before_start",
		ReasonDetail:     "removed during pre-start seating window",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           fmt.Sprintf("ops-state:%s", minerID),
			PayloadHash:         fmt.Sprintf("ops-payload:%s", minerID),
		},
		Payload:   json.RawMessage(`{"stage":"pre_start"}`),
		CreatedAt: s.now(),
		UpdatedAt: s.now(),
	}); err != nil {
		return err
	}

	return nil
}

func (s *Service) RepublishSeats(ctx context.Context) error {
	if ctx == nil {
		return errContextRequired
	}
	if s.state.WaveState != model.WaveStateSeatsPublished {
		return errSeatsNotPublished
	}
	if s.state.republishUsed {
		return errRepublishAlreadyUsed
	}
	if !s.state.pendingRepublish {
		return errRepublishNotRequired
	}
	if len(s.state.Tournaments) == 0 {
		return errNoPackedTournament
	}

	plan := s.state.Tournaments[0]
	oldAssignments := seatingByEntrant(plan.SeatAssignments)
	newAssignments := assignSeats(plan.TournamentID, s.state.activeEntrants())
	plan.EntrantIDs = entrantIDs(s.state.activeEntrants())
	plan.SeatAssignments = newAssignments
	plan.RepublishCount++
	plan.SeatsWerePublished = true
	s.state.Tournaments[0] = plan
	s.state.republishUsed = true
	s.state.pendingRepublish = false

	reseats := make([]model.ReseatEvent, 0)
	for _, assignment := range newAssignments {
		previous, ok := oldAssignments[assignment.EntrantID]
		if !ok {
			continue
		}
		if previous.TableID == assignment.TableID && previous.SeatNo == assignment.SeatNo {
			continue
		}
		reseats = append(reseats, model.ReseatEvent{
			ID:                fmt.Sprintf("reseat:%s:%s", plan.TournamentID, assignment.EntrantID),
			TournamentID:      plan.TournamentID,
			FromTableID:       previous.TableID,
			ToTableID:         assignment.TableID,
			SeatID:            seatID(assignment.TableID, assignment.SeatNo),
			EntrantID:         assignment.EntrantID,
			RoundNo:           0,
			CausedByBarrierID: "",
			OccurredAt:        s.now(),
			TruthMetadata: model.TruthMetadata{
				PolicyBundleVersion: "policy-v1",
				StateHash:           fmt.Sprintf("reseat-state:%s", assignment.EntrantID),
				PayloadHash:         fmt.Sprintf("reseat-payload:%s", assignment.EntrantID),
			},
			Payload:   json.RawMessage(`{"kind":"pre_start_republish"}`),
			CreatedAt: s.now(),
		})
	}
	if len(reseats) > 0 {
		if err := s.store.AppendReseatEvents(ctx, reseats); err != nil {
			return err
		}
	}

	return s.persistSnapshots(ctx, "seating_published")
}

func (s *Service) persistSnapshots(ctx context.Context, stage string) error {
	for _, tournament := range s.state.Tournaments {
		s.state.snapshotStreamSeq++
		payload, err := json.Marshal(map[string]any{
			"stage":             stage,
			"rated_or_practice": tournament.RatedOrPractice,
			"no_multiplier":     tournament.NoMultiplier,
			"entrant_ids":       tournament.EntrantIDs,
			"republish_count":   tournament.RepublishCount,
		})
		if err != nil {
			return fmt.Errorf("marshal snapshot payload: %w", err)
		}

		if err := s.store.SaveTournamentSnapshot(ctx, model.TournamentSnapshot{
			ID:           fmt.Sprintf("snap:%s:%s", tournament.TournamentID, stage),
			TournamentID: tournament.TournamentID,
			StreamKey:    fmt.Sprintf("tournament:%s", tournament.TournamentID),
			StreamSeq:    s.state.snapshotStreamSeq,
			StateSeq:     int64(tournament.RepublishCount),
			TruthMetadata: model.TruthMetadata{
				PolicyBundleVersion: "policy-v1",
				StateHash:           fmt.Sprintf("snapshot-state:%s:%s", tournament.TournamentID, stage),
				PayloadHash:         fmt.Sprintf("snapshot-payload:%s:%s", tournament.TournamentID, stage),
			},
			Payload:   payload,
			CreatedAt: s.now(),
		}); err != nil {
			return fmt.Errorf("save tournament snapshot: %w", err)
		}
	}

	return nil
}

func classifyShard(entrants int) (model.ArenaMode, bool) {
	switch {
	case entrants >= 56 && entrants <= 64:
		return model.RatedMode, false
	case entrants >= 48:
		return model.PracticeMode, true
	default:
		return model.PracticeMode, true
	}
}

func entrantIDs(entrants []model.Entrant) []string {
	ids := make([]string, 0, len(entrants))
	for _, entrant := range entrants {
		ids = append(ids, entrant.ID)
	}
	return ids
}

func assignSeats(tournamentID string, entrants []model.Entrant) []SeatAssignment {
	assignments := make([]SeatAssignment, 0, len(entrants))
	for i, entrant := range entrants {
		tableNo := (i / seatsPerTable) + 1
		seatNo := (i % seatsPerTable) + 1
		assignments = append(assignments, SeatAssignment{
			EntrantID: entrant.ID,
			MinerID:   entrant.MinerID,
			TableID:   model.TableID(tournamentID, tableNo),
			TableNo:   tableNo,
			SeatNo:    seatNo,
		})
	}
	return assignments
}

func seatingByEntrant(assignments []SeatAssignment) map[string]SeatAssignment {
	byEntrant := make(map[string]SeatAssignment, len(assignments))
	for _, assignment := range assignments {
		byEntrant[assignment.EntrantID] = assignment
	}
	return byEntrant
}

func seatID(tableID string, seatNo int) string {
	return fmt.Sprintf("seat:%s:%02d", tableID, seatNo)
}

func (s *Service) lookupAssignment(entrantID string) (SeatAssignment, string) {
	for _, tournament := range s.state.Tournaments {
		for _, assignment := range tournament.SeatAssignments {
			if assignment.EntrantID == entrantID {
				return assignment, tournament.TournamentID
			}
		}
	}
	return SeatAssignment{}, ""
}

func targetTableCount(playersRemaining int) int {
	switch {
	case playersRemaining <= seatsPerTable:
		return 1
	case playersRemaining >= 9 && playersRemaining <= 13:
		return 2
	default:
		for n := 2; n <= int(math.Max(2, float64(playersRemaining))); n++ {
			if 7*n <= playersRemaining && playersRemaining <= 9*n {
				return n
			}
		}
		return 2
	}
}

func needsRebalance(tables []LiveTable) bool {
	if len(tables) < 2 {
		return false
	}

	minPlayers := tables[0].PlayerCount
	maxPlayers := tables[0].PlayerCount
	for _, table := range tables[1:] {
		if table.PlayerCount < minPlayers {
			minPlayers = table.PlayerCount
		}
		if table.PlayerCount > maxPlayers {
			maxPlayers = table.PlayerCount
		}
	}

	return maxPlayers-minPlayers > 1
}

func tableID(tournamentID string, tableNo int) string {
	return model.TableID(tournamentID, tableNo)
}
