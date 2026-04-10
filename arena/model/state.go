package model

import "fmt"

type ArenaMode string

const (
	RatedMode    ArenaMode = "rated"
	PracticeMode ArenaMode = "practice"
)

type WaveState string

const (
	WaveStateScheduled            WaveState = "scheduled"
	WaveStateRegistrationOpen     WaveState = "registration_open"
	WaveStateRegistrationFrozen   WaveState = "registration_frozen"
	WaveStateFieldLocked          WaveState = "field_locked"
	WaveStateEligibilityResolving WaveState = "eligibility_resolving"
	WaveStateFieldFinalized       WaveState = "field_finalized"
	WaveStatePacking              WaveState = "packing"
	WaveStateTournamentsCreated   WaveState = "tournaments_created"
	WaveStateSeatingGenerated     WaveState = "seating_generated"
	WaveStateSeatsPublished       WaveState = "seats_published"
	WaveStateStartArmed           WaveState = "start_armed"
	WaveStateInProgress           WaveState = "in_progress"
	WaveStateCompleted            WaveState = "completed"
	WaveStateFinalized            WaveState = "finalized"
	WaveStateCancelled            WaveState = "cancelled"
	WaveStateVoided               WaveState = "voided"
)

type TournamentState string

const (
	TournamentStateScheduled             TournamentState = "scheduled"
	TournamentStateRegistrationConfirmed TournamentState = "registration_confirmed"
	TournamentStateSeating               TournamentState = "seating"
	TournamentStateReady                 TournamentState = "ready"
	TournamentStateLiveMultiTable        TournamentState = "live_multi_table"
	TournamentStateRebalancing           TournamentState = "rebalancing"
	TournamentStateFinalTableTransition  TournamentState = "final_table_transition"
	TournamentStateLiveFinalTable        TournamentState = "live_final_table"
	TournamentStateCompleted             TournamentState = "completed"
	TournamentStateRated                 TournamentState = "rated"
	TournamentStateSettled               TournamentState = "settled"
	TournamentStateCancelled             TournamentState = "cancelled"
	TournamentStateVoided                TournamentState = "voided"
)

type TableState string

const (
	TableStateOpen               TableState = "open"
	TableStateHandStarting       TableState = "hand_starting"
	TableStateHandLive           TableState = "hand_live"
	TableStateHandClosing        TableState = "hand_closing"
	TableStateAwaitingBarrier    TableState = "awaiting_barrier"
	TableStatePausedForRebalance TableState = "paused_for_rebalance"
	TableStateClosed             TableState = "closed"
)

type HandState string

const (
	HandStateCreated             HandState = "created"
	HandStateBlindsPosted        HandState = "blinds_posted"
	HandStateSignalOpen          HandState = "signal_open"
	HandStateSignalClosed        HandState = "signal_closed"
	HandStateProbeOpen           HandState = "probe_open"
	HandStateProbeClosed         HandState = "probe_closed"
	HandStateWagerOpen           HandState = "wager_open"
	HandStateWagerClosed         HandState = "wager_closed"
	HandStateShowdownResolved    HandState = "showdown_resolved"
	HandStateAwardsApplied       HandState = "awards_applied"
	HandStateEliminationResolved HandState = "elimination_resolved"
	HandStateClosed              HandState = "closed"
)

type PhaseState string

const (
	PhaseStatePending PhaseState = "pending"
	PhaseStateOpen    PhaseState = "open"
	PhaseStateClosing PhaseState = "closing"
	PhaseStateClosed  PhaseState = "closed"
)

type SeatState string

const (
	SeatStateActive     SeatState = "active"
	SeatStateSitOut     SeatState = "sit_out"
	SeatStateEliminated SeatState = "eliminated"
)

type RegistrationState string

const (
	RegistrationStateNotRegistered      RegistrationState = "not_registered"
	RegistrationStateRegistered         RegistrationState = "registered"
	RegistrationStateWaitlisted         RegistrationState = "waitlisted"
	RegistrationStateConfirmed          RegistrationState = "confirmed"
	RegistrationStateSeated             RegistrationState = "seated"
	RegistrationStatePlaying            RegistrationState = "playing"
	RegistrationStateEliminated         RegistrationState = "eliminated"
	RegistrationStateChampion           RegistrationState = "champion"
	RegistrationStateRemovedBeforeStart RegistrationState = "removed_before_start"
	RegistrationStateDisqualified       RegistrationState = "disqualified"
)

type PhaseType string

const (
	PhaseTypeSignal PhaseType = "signal"
	PhaseTypeProbe  PhaseType = "probe"
	PhaseTypeWager  PhaseType = "wager"
)

var (
	arenaModes = allowedSet[ArenaMode](
		RatedMode,
		PracticeMode,
	)
	waveStates = allowedSet[WaveState](
		WaveStateScheduled,
		WaveStateRegistrationOpen,
		WaveStateRegistrationFrozen,
		WaveStateFieldLocked,
		WaveStateEligibilityResolving,
		WaveStateFieldFinalized,
		WaveStatePacking,
		WaveStateTournamentsCreated,
		WaveStateSeatingGenerated,
		WaveStateSeatsPublished,
		WaveStateStartArmed,
		WaveStateInProgress,
		WaveStateCompleted,
		WaveStateFinalized,
		WaveStateCancelled,
		WaveStateVoided,
	)
	tournamentStates = allowedSet[TournamentState](
		TournamentStateScheduled,
		TournamentStateRegistrationConfirmed,
		TournamentStateSeating,
		TournamentStateReady,
		TournamentStateLiveMultiTable,
		TournamentStateRebalancing,
		TournamentStateFinalTableTransition,
		TournamentStateLiveFinalTable,
		TournamentStateCompleted,
		TournamentStateRated,
		TournamentStateSettled,
		TournamentStateCancelled,
		TournamentStateVoided,
	)
	tableStates = allowedSet[TableState](
		TableStateOpen,
		TableStateHandStarting,
		TableStateHandLive,
		TableStateHandClosing,
		TableStateAwaitingBarrier,
		TableStatePausedForRebalance,
		TableStateClosed,
	)
	handStates = allowedSet[HandState](
		HandStateCreated,
		HandStateBlindsPosted,
		HandStateSignalOpen,
		HandStateSignalClosed,
		HandStateProbeOpen,
		HandStateProbeClosed,
		HandStateWagerOpen,
		HandStateWagerClosed,
		HandStateShowdownResolved,
		HandStateAwardsApplied,
		HandStateEliminationResolved,
		HandStateClosed,
	)
	phaseStates = allowedSet[PhaseState](
		PhaseStatePending,
		PhaseStateOpen,
		PhaseStateClosing,
		PhaseStateClosed,
	)
	seatStates = allowedSet[SeatState](
		SeatStateActive,
		SeatStateSitOut,
		SeatStateEliminated,
	)
	registrationStates = allowedSet[RegistrationState](
		RegistrationStateNotRegistered,
		RegistrationStateRegistered,
		RegistrationStateWaitlisted,
		RegistrationStateConfirmed,
		RegistrationStateSeated,
		RegistrationStatePlaying,
		RegistrationStateEliminated,
		RegistrationStateChampion,
		RegistrationStateRemovedBeforeStart,
		RegistrationStateDisqualified,
	)
	phaseTypes = allowedSet[PhaseType](
		PhaseTypeSignal,
		PhaseTypeProbe,
		PhaseTypeWager,
	)
)

func (m ArenaMode) Validate() error {
	return validateEnum("arena mode", m, arenaModes)
}

func (s WaveState) Validate() error {
	return validateEnum("wave state", s, waveStates)
}

func (s TournamentState) Validate() error {
	return validateEnum("tournament state", s, tournamentStates)
}

func (s TableState) Validate() error {
	return validateEnum("table state", s, tableStates)
}

func (s HandState) Validate() error {
	return validateEnum("hand state", s, handStates)
}

func (s PhaseState) Validate() error {
	return validateEnum("phase state", s, phaseStates)
}

func (s SeatState) Validate() error {
	return validateEnum("seat state", s, seatStates)
}

func (s RegistrationState) Validate() error {
	return validateEnum("registration state", s, registrationStates)
}

func (p PhaseType) Validate() error {
	return validateEnum("phase type", p, phaseTypes)
}

func allowedSet[T ~string](values ...T) map[T]struct{} {
	items := make(map[T]struct{}, len(values))
	for _, value := range values {
		items[value] = struct{}{}
	}
	return items
}

func validateEnum[T ~string](kind string, value T, allowed map[T]struct{}) error {
	if _, ok := allowed[value]; ok {
		return nil
	}

	return fmt.Errorf("invalid %s %q", kind, value)
}
