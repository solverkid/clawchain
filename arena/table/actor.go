package table

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/clawchain/clawchain/arena/model"
)

var (
	errActorContextRequired = errors.New("context is required")
	errStateSeqMismatch     = errors.New("state_seq_mismatch")
)

type Clock interface {
	Now() time.Time
}

type actorStore interface {
	AppendEvents(ctx context.Context, events []model.EventLogEntry) error
	AppendActionRecords(ctx context.Context, actions []model.ActionRecord) error
	SaveTableSnapshot(ctx context.Context, snapshot model.TableSnapshot) error
	SaveHandSnapshot(ctx context.Context, snapshot model.HandSnapshot) error
	UpsertActionDeadline(ctx context.Context, deadline model.ActionDeadline) error
}

type ActorState struct {
	TableID      string
	TournamentID string
	HandID       string
	PhaseID      string
	StateSeq     int64
	Table        State
}

type CommandEnvelope struct {
	RequestID        string
	ExpectedStateSeq int64
	Command          Command
}

type Result struct {
	ResultEventID string
	StateSeq      int64
}

type PhaseDefinition struct {
	ID         string
	HandID     string
	Type       Phase
	ActingSeat int
	ToCall     int64
	DeadlineAt *time.Time
}

type Actor struct {
	mu        sync.Mutex
	state     ActorState
	clock     Clock
	store     actorStore
	streamSeq int64
	results   map[string]Result
}

func NewActor(initial ActorState, clock Clock, store actorStore) *Actor {
	return &Actor{
		state:   initial,
		clock:   clock,
		store:   store,
		results: make(map[string]Result),
	}
}

func (a *Actor) State() ActorState {
	a.mu.Lock()
	defer a.mu.Unlock()

	state := a.state
	state.Table = a.state.Table.clone()
	return state
}

func (a *Actor) Handle(ctx context.Context, envelope CommandEnvelope) (Result, error) {
	if ctx == nil {
		return Result{}, errActorContextRequired
	}

	a.mu.Lock()
	defer a.mu.Unlock()

	if result, ok := a.results[envelope.RequestID]; ok {
		return result, nil
	}
	if envelope.ExpectedStateSeq != a.state.StateSeq {
		return Result{}, errStateSeqMismatch
	}

	nextTable, events, err := Apply(a.state.Table, envelope.Command)
	if err != nil {
		return Result{}, err
	}

	a.streamSeq++
	nextSeq := a.state.StateSeq + 1
	eventID := model.EventID(a.streamKey(), a.streamSeq)

	if err := a.persistAction(ctx, envelope, eventID, nextSeq); err != nil {
		return Result{}, err
	}
	if err := a.persistEvents(ctx, eventID, nextSeq, events); err != nil {
		return Result{}, err
	}
	if err := a.persistDerivedState(ctx, envelope.Command, nextTable, nextSeq, eventID); err != nil {
		return Result{}, err
	}

	a.state.Table = nextTable
	a.state.StateSeq = nextSeq
	result := Result{
		ResultEventID: eventID,
		StateSeq:      nextSeq,
	}
	a.results[envelope.RequestID] = result

	return result, nil
}

func (a *Actor) OpenPhase(ctx context.Context, phase PhaseDefinition) error {
	if ctx == nil {
		return errActorContextRequired
	}

	a.mu.Lock()
	defer a.mu.Unlock()

	a.streamSeq++
	nextSeq := a.state.StateSeq + 1
	now := a.clock.Now().UTC()
	a.state.PhaseID = phase.ID
	if phase.HandID != "" {
		a.state.HandID = phase.HandID
	}
	a.state.Table.CurrentPhase = phase.Type
	a.state.Table.ActingSeatNo = phase.ActingSeat
	a.state.Table.CurrentToCall = phase.ToCall

	if err := a.store.AppendEvents(ctx, []model.EventLogEntry{{
		EventID:       model.EventID(a.streamKey(), a.streamSeq),
		AggregateType: "table",
		AggregateID:   a.state.TableID,
		StreamKey:     a.streamKey(),
		StreamSeq:     a.streamSeq,
		TournamentID:  a.state.TournamentID,
		TableID:       a.state.TableID,
		HandID:        a.state.HandID,
		PhaseID:       phase.ID,
		EventType:     "table.phase.opened",
		EventVersion:  1,
		StateSeq:      nextSeq,
		OccurredAt:    now,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			StateHash:           fmt.Sprintf("phase-open-state:%s:%d", a.state.TableID, nextSeq),
			PayloadHash:         fmt.Sprintf("phase-open-payload:%s:%d", a.state.TableID, nextSeq),
		},
		Payload: json.RawMessage(`{"kind":"phase_open"}`),
	}}); err != nil {
		return err
	}

	if phase.DeadlineAt != nil {
		if err := a.store.UpsertActionDeadline(ctx, model.ActionDeadline{
			DeadlineID:      fmt.Sprintf("ddl:%s", phase.ID),
			TournamentID:    a.state.TournamentID,
			TableID:         a.state.TableID,
			HandID:          a.state.HandID,
			PhaseID:         phase.ID,
			SeatID:          fmt.Sprintf("seat:%s:%02d", a.state.TableID, phase.ActingSeat),
			DeadlineAt:      phase.DeadlineAt.UTC(),
			Status:          "open",
			OpenedByEventID: model.EventID(a.streamKey(), a.streamSeq),
			TruthMetadata: model.TruthMetadata{
				SchemaVersion:       1,
				PolicyBundleVersion: "policy-v1",
				StateHash:           fmt.Sprintf("deadline-state:%s:%d", phase.ID, nextSeq),
				PayloadHash:         fmt.Sprintf("deadline-payload:%s:%d", phase.ID, nextSeq),
			},
			Payload:   json.RawMessage(`{"kind":"phase_deadline"}`),
			CreatedAt: now,
			UpdatedAt: now,
		}); err != nil {
			return err
		}
	}

	if err := a.store.SaveTableSnapshot(ctx, model.TableSnapshot{
		ID:           fmt.Sprintf("tblsnap:%s:%d", a.state.TableID, nextSeq),
		TournamentID: a.state.TournamentID,
		TableID:      a.state.TableID,
		StreamKey:    a.streamKey(),
		StreamSeq:    a.streamSeq,
		StateSeq:     nextSeq,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			StateHash:           fmt.Sprintf("table-snapshot-state:%s:%d", a.state.TableID, nextSeq),
			PayloadHash:         fmt.Sprintf("table-snapshot-payload:%s:%d", a.state.TableID, nextSeq),
		},
		Payload:   mustJSON(a.state.Table),
		CreatedAt: now,
	}); err != nil {
		return err
	}

	a.state.StateSeq = nextSeq
	return nil
}

func (a *Actor) persistAction(ctx context.Context, envelope CommandEnvelope, eventID string, nextSeq int64) error {
	actionType := ""
	switch cmd := envelope.Command.(type) {
	case SubmitArenaAction:
		actionType = string(cmd.ActionType)
	case ApplyPhaseTimeout:
		actionType = "timeout"
	case CloseHand:
		actionType = "close_hand"
	case StartHand:
		actionType = "start_hand"
	}

	return a.store.AppendActionRecords(ctx, []model.ActionRecord{{
		RequestID:        envelope.RequestID,
		TournamentID:     a.state.TournamentID,
		TableID:          a.state.TableID,
		HandID:           a.state.HandID,
		PhaseID:          a.state.PhaseID,
		ActionType:       actionType,
		ExpectedStateSeq: envelope.ExpectedStateSeq,
		AcceptedStateSeq: nextSeq,
		ValidationStatus: "accepted",
		ResultEventID:    eventID,
		ReceivedAt:       a.clock.Now().UTC(),
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			StateHash:           fmt.Sprintf("action-state:%s:%d", envelope.RequestID, nextSeq),
			PayloadHash:         fmt.Sprintf("action-payload:%s:%d", envelope.RequestID, nextSeq),
		},
		Payload: json.RawMessage(`{"kind":"actor_action"}`),
	}})
}

func (a *Actor) persistEvents(ctx context.Context, eventID string, nextSeq int64, events []Event) error {
	logEntries := make([]model.EventLogEntry, 0, len(events))
	for idx, event := range events {
		logEntries = append(logEntries, model.EventLogEntry{
			EventID:       eventIDForIndex(eventID, idx),
			AggregateType: "table",
			AggregateID:   a.state.TableID,
			StreamKey:     a.streamKey(),
			StreamSeq:     a.streamSeq,
			TournamentID:  a.state.TournamentID,
			TableID:       a.state.TableID,
			HandID:        a.state.HandID,
			PhaseID:       a.state.PhaseID,
			EventType:     string(event.Type),
			EventVersion:  1,
			StateSeq:      nextSeq,
			OccurredAt:    a.clock.Now().UTC(),
			TruthMetadata: model.TruthMetadata{
				SchemaVersion:       1,
				PolicyBundleVersion: "policy-v1",
				StateHash:           fmt.Sprintf("event-state:%s:%d", eventID, idx),
				PayloadHash:         fmt.Sprintf("event-payload:%s:%d", eventID, idx),
			},
			Payload: mustJSON(event),
		})
	}
	if len(logEntries) == 0 {
		return nil
	}
	return a.store.AppendEvents(ctx, logEntries)
}

func (a *Actor) persistDerivedState(ctx context.Context, cmd Command, nextTable State, nextSeq int64, eventID string) error {
	now := a.clock.Now().UTC()

	switch typed := cmd.(type) {
	case SubmitArenaAction, ApplyPhaseTimeout:
		if a.state.PhaseID != "" {
			if err := a.store.UpsertActionDeadline(ctx, model.ActionDeadline{
				DeadlineID:        fmt.Sprintf("ddl:%s", a.state.PhaseID),
				TournamentID:      a.state.TournamentID,
				TableID:           a.state.TableID,
				HandID:            a.state.HandID,
				PhaseID:           a.state.PhaseID,
				DeadlineAt:        now,
				Status:            "closed",
				ResolvedByEventID: eventID,
				TruthMetadata: model.TruthMetadata{
					SchemaVersion:       1,
					PolicyBundleVersion: "policy-v1",
					StateHash:           fmt.Sprintf("deadline-close-state:%s:%d", a.state.PhaseID, nextSeq),
					PayloadHash:         fmt.Sprintf("deadline-close-payload:%s:%d", a.state.PhaseID, nextSeq),
				},
				Payload:   json.RawMessage(`{"kind":"phase_deadline_closed"}`),
				CreatedAt: now,
				UpdatedAt: now,
			}); err != nil {
				return err
			}
		}
		_ = typed
	case CloseHand:
		if err := a.store.SaveHandSnapshot(ctx, model.HandSnapshot{
			ID:           fmt.Sprintf("handsnap:%s:%d", a.state.HandID, nextSeq),
			TournamentID: a.state.TournamentID,
			TableID:      a.state.TableID,
			HandID:       a.state.HandID,
			StreamKey:    a.streamKey(),
			StreamSeq:    a.streamSeq,
			StateSeq:     nextSeq,
			TruthMetadata: model.TruthMetadata{
				SchemaVersion:       1,
				PolicyBundleVersion: "policy-v1",
				StateHash:           fmt.Sprintf("hand-snapshot-state:%s:%d", a.state.HandID, nextSeq),
				PayloadHash:         fmt.Sprintf("hand-snapshot-payload:%s:%d", a.state.HandID, nextSeq),
			},
			Payload:   mustJSON(nextTable),
			CreatedAt: now,
		}); err != nil {
			return err
		}
	}

	if _, ok := cmd.(CloseHand); ok || a.state.PhaseID != "" {
		return a.store.SaveTableSnapshot(ctx, model.TableSnapshot{
			ID:           fmt.Sprintf("tblsnap:%s:%d", a.state.TableID, nextSeq),
			TournamentID: a.state.TournamentID,
			TableID:      a.state.TableID,
			StreamKey:    a.streamKey(),
			StreamSeq:    a.streamSeq,
			StateSeq:     nextSeq,
			TruthMetadata: model.TruthMetadata{
				SchemaVersion:       1,
				PolicyBundleVersion: "policy-v1",
				StateHash:           fmt.Sprintf("table-snapshot-state:%s:%d", a.state.TableID, nextSeq),
				PayloadHash:         fmt.Sprintf("table-snapshot-payload:%s:%d", a.state.TableID, nextSeq),
			},
			Payload:   mustJSON(nextTable),
			CreatedAt: now,
		})
	}

	return nil
}

func (a *Actor) streamKey() string {
	return fmt.Sprintf("table:%s", a.state.TableID)
}

func eventIDForIndex(base string, idx int) string {
	if idx == 0 {
		return base
	}
	return fmt.Sprintf("%s:%d", base, idx)
}

func mustJSON(value any) json.RawMessage {
	payload, err := json.Marshal(value)
	if err != nil {
		panic(err)
	}
	return payload
}
