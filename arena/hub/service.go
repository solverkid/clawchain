package hub

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"slices"
	"sort"
	"time"

	"github.com/clawchain/clawchain/arena/model"
)

const seatsPerTable = 9

const (
	ratedShardMinEntrants = 33
	ratedShardMaxEntrants = 64
)

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

func (s *Service) ClosedTableIDs() []string {
	tableIDs := make([]string, 0, len(s.state.ClosedTables))
	for tableID, closed := range s.state.ClosedTables {
		if !closed {
			continue
		}
		tableIDs = append(tableIDs, tableID)
	}
	sort.Strings(tableIDs)
	return tableIDs
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

func (s *Service) BuildTransitionPlan() TransitionPlan {
	decision := s.NextBarrierDecision()
	assignments := currentAssignments(s.state)
	if decision == TransitionNone || len(assignments) == 0 {
		return TransitionPlan{
			Decision:        decision,
			SeatAssignments: assignments,
		}
	}

	switch decision {
	case TransitionFinalTable:
		return TransitionPlan{
			Decision:        decision,
			SeatAssignments: reseatAssignments(tableID(s.state.TournamentID, 1), 1, assignments),
		}
	case TransitionBreakTable, TransitionRebalance:
		return TransitionPlan{
			Decision:        decision,
			SeatAssignments: rebalanceAssignments(s.state.TournamentID, assignments, targetTableCount(s.state.PlayersRemaining)),
		}
	default:
		return TransitionPlan{
			Decision:        decision,
			SeatAssignments: assignments,
		}
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
	case entrants >= ratedShardMinEntrants && entrants <= ratedShardMaxEntrants:
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
	if len(entrants) == 0 {
		return nil
	}

	draw := shuffledEntrants(tournamentID, entrants)
	targets := balancedTargetSizes(len(draw), targetTableCount(len(draw)))
	assignments := make([]SeatAssignment, 0, len(entrants))

	offset := 0
	for tableIdx, tableSize := range targets {
		tableNo := tableIdx + 1
		for seatIdx := 0; seatIdx < tableSize; seatIdx++ {
			entrant := draw[offset+seatIdx]
			assignments = append(assignments, SeatAssignment{
				EntrantID: entrant.ID,
				MinerID:   entrant.MinerID,
				TableID:   model.TableID(tournamentID, tableNo),
				TableNo:   tableNo,
				SeatNo:    seatIdx + 1,
			})
		}
		offset += tableSize
	}
	return assignments
}

func shuffledEntrants(tournamentID string, entrants []model.Entrant) []model.Entrant {
	draw := slices.Clone(entrants)
	sort.Slice(draw, func(i, j int) bool {
		left := drawKey(tournamentID, draw[i])
		right := drawKey(tournamentID, draw[j])
		if cmp := bytes.Compare(left[:], right[:]); cmp != 0 {
			return cmp < 0
		}
		if draw[i].MinerID != draw[j].MinerID {
			return draw[i].MinerID < draw[j].MinerID
		}
		return draw[i].ID < draw[j].ID
	})
	return draw
}

func drawKey(tournamentID string, entrant model.Entrant) [32]byte {
	return sha256.Sum256([]byte(tournamentID + "|" + entrant.ID + "|" + entrant.MinerID + "|" + entrant.SeatAlias))
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
	if playersRemaining <= 0 {
		return 0
	}
	return int(math.Ceil(float64(playersRemaining) / float64(seatsPerTable)))
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

func currentAssignments(state State) []SeatAssignment {
	if len(state.Tournaments) == 0 {
		return nil
	}
	assignments := slices.Clone(state.Tournaments[0].SeatAssignments)
	sort.Slice(assignments, func(i, j int) bool {
		if assignments[i].TableID != assignments[j].TableID {
			return assignments[i].TableID < assignments[j].TableID
		}
		return assignments[i].SeatNo < assignments[j].SeatNo
	})
	return assignments
}

func reseatAssignments(targetTableID string, targetTableNo int, assignments []SeatAssignment) []SeatAssignment {
	next := slices.Clone(assignments)
	sort.Slice(next, func(i, j int) bool {
		if next[i].TableID != next[j].TableID {
			return next[i].TableID < next[j].TableID
		}
		return next[i].SeatNo < next[j].SeatNo
	})
	for i := range next {
		next[i].TableID = targetTableID
		next[i].TableNo = targetTableNo
		next[i].SeatNo = i + 1
	}
	return next
}

func rebalanceAssignments(tournamentID string, assignments []SeatAssignment, targetTables int) []SeatAssignment {
	if targetTables <= 0 {
		return slices.Clone(assignments)
	}

	grouped := make(map[string][]SeatAssignment)
	for _, assignment := range assignments {
		grouped[assignment.TableID] = append(grouped[assignment.TableID], assignment)
	}

	tableIDs := make([]string, 0, len(grouped))
	for tableID := range grouped {
		tableIDs = append(tableIDs, tableID)
	}
	sort.Slice(tableIDs, func(i, j int) bool {
		if len(grouped[tableIDs[i]]) != len(grouped[tableIDs[j]]) {
			return len(grouped[tableIDs[i]]) > len(grouped[tableIDs[j]])
		}
		return tableIDs[i] < tableIDs[j]
	})
	if targetTables > len(tableIDs) {
		targetTables = len(tableIDs)
	}
	keepTableIDs := append([]string(nil), tableIDs[:targetTables]...)
	sort.Strings(keepTableIDs)

	kept := make(map[string][]SeatAssignment, len(keepTableIDs))
	for _, tableID := range keepTableIDs {
		kept[tableID] = append([]SeatAssignment(nil), grouped[tableID]...)
		sort.Slice(kept[tableID], func(i, j int) bool { return kept[tableID][i].SeatNo < kept[tableID][j].SeatNo })
	}

	pool := make([]SeatAssignment, 0)
	for _, tableID := range tableIDs[targetTables:] {
		tableAssignments := append([]SeatAssignment(nil), grouped[tableID]...)
		sort.Slice(tableAssignments, func(i, j int) bool { return tableAssignments[i].SeatNo > tableAssignments[j].SeatNo })
		pool = append(pool, tableAssignments...)
	}

	targetSizes := balancedTargetSizes(len(assignments), targetTables)
	for idx, tableID := range keepTableIDs {
		for len(kept[tableID]) > targetSizes[idx] {
			source := kept[tableID]
			pool = append(pool, source[len(source)-1])
			kept[tableID] = source[:len(source)-1]
		}
	}

	sort.Slice(pool, func(i, j int) bool {
		if pool[i].TableID != pool[j].TableID {
			return pool[i].TableID < pool[j].TableID
		}
		return pool[i].SeatNo > pool[j].SeatNo
	})

	for idx, tableID := range keepTableIDs {
		for len(kept[tableID]) < targetSizes[idx] && len(pool) > 0 {
			mover := pool[0]
			pool = pool[1:]
			mover.TableID = tableID
			mover.TableNo = tableNoFromTableID(tableID)
			kept[tableID] = append(kept[tableID], mover)
		}
	}

	next := make([]SeatAssignment, 0, len(assignments))
	for _, tableID := range keepTableIDs {
		tableAssignments := kept[tableID]
		sort.Slice(tableAssignments, func(i, j int) bool {
			if tableAssignments[i].TableID != tableAssignments[j].TableID {
				return tableAssignments[i].TableID < tableAssignments[j].TableID
			}
			return tableAssignments[i].SeatNo < tableAssignments[j].SeatNo
		})
		for idx := range tableAssignments {
			tableAssignments[idx].SeatNo = idx + 1
			tableAssignments[idx].TableID = tableID
			tableAssignments[idx].TableNo = tableNoFromTableID(tableID)
		}
		next = append(next, tableAssignments...)
	}

	sort.Slice(next, func(i, j int) bool {
		if next[i].TableID != next[j].TableID {
			return next[i].TableID < next[j].TableID
		}
		return next[i].SeatNo < next[j].SeatNo
	})
	return next
}

func balancedTargetSizes(playersRemaining, tableCount int) []int {
	targets := make([]int, tableCount)
	base := playersRemaining / tableCount
	remainder := playersRemaining % tableCount
	for i := range targets {
		targets[i] = base
		if i < remainder {
			targets[i]++
		}
	}
	sort.Slice(targets, func(i, j int) bool { return targets[i] > targets[j] })
	return targets
}

func tableNoFromTableID(tableID string) int {
	for idx := len(tableID) - 1; idx >= 0; idx-- {
		if tableID[idx] == ':' {
			value := 0
			for _, ch := range tableID[idx+1:] {
				value = value*10 + int(ch-'0')
			}
			return value
		}
	}
	return 0
}
