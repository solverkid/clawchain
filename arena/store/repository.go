package store

import (
	"context"

	"github.com/clawchain/clawchain/arena/model"
)

type WaveStore interface {
	UpsertWave(ctx context.Context, wave model.Wave) error
}

type TournamentStore interface {
	UpsertTournament(ctx context.Context, tournament model.Tournament) error
}

type EntrantStore interface {
	UpsertEntrant(ctx context.Context, entrant model.Entrant) error
	UpsertWaitlistEntry(ctx context.Context, entry model.WaitlistEntry) error
	UpsertPrestartCheck(ctx context.Context, check model.PrestartCheck) error
	UpsertShardAssignment(ctx context.Context, assignment model.ShardAssignment) error
}

type LevelStore interface {
	UpsertLevel(ctx context.Context, level model.Level) error
}

type TableStore interface {
	UpsertTable(ctx context.Context, table model.Table) error
	UpsertHand(ctx context.Context, hand model.Hand) error
	UpsertPhase(ctx context.Context, phase model.Phase) error
	UpsertSeat(ctx context.Context, seat model.Seat) error
	UpsertAliasMap(ctx context.Context, alias model.AliasMap) error
	AppendReseatEvents(ctx context.Context, events []model.ReseatEvent) error
	AppendEliminationEvents(ctx context.Context, events []model.EliminationEvent) error
}

type IngressStore interface {
	AppendSubmissionLedgerEntries(ctx context.Context, entries []model.SubmissionLedger) error
	AppendActionRecords(ctx context.Context, actions []model.ActionRecord) error
	UpsertActionDeadline(ctx context.Context, deadline model.ActionDeadline) error
}

type ControlStore interface {
	UpsertRoundBarrier(ctx context.Context, barrier model.RoundBarrier) error
	UpsertOperatorIntervention(ctx context.Context, intervention model.OperatorIntervention) error
}

type EventStore interface {
	AppendEvents(ctx context.Context, events []model.EventLogEntry) error
}

type SnapshotStore interface {
	SaveTournamentSnapshot(ctx context.Context, snapshot model.TournamentSnapshot) error
	SaveTableSnapshot(ctx context.Context, snapshot model.TableSnapshot) error
	SaveHandSnapshot(ctx context.Context, snapshot model.HandSnapshot) error
	SaveStandingSnapshot(ctx context.Context, snapshot model.StandingSnapshot) error
}

type ProjectorStore interface {
	EnqueueOutboxEvents(ctx context.Context, events []model.OutboxEvent) error
	SaveProjectorCursor(ctx context.Context, cursor model.ProjectorCursor) error
	SaveDeadLetterEvent(ctx context.Context, event model.DeadLetterEvent) error
}

type RatingStore interface {
	AppendRatingInputs(ctx context.Context, inputs []model.RatingInput) error
	UpsertRatingState(ctx context.Context, state model.RatingState) error
	SaveRatingSnapshot(ctx context.Context, snapshot model.RatingSnapshot) error
	SavePublicLadderSnapshot(ctx context.Context, snapshot model.PublicLadderSnapshot) error
	SaveMultiplierSnapshot(ctx context.Context, snapshot model.MultiplierSnapshot) error
	UpsertMinerCompatibility(ctx context.Context, miner model.MinerCompatibility) error
	UpsertArenaResultEntry(ctx context.Context, entry model.ArenaResultEntry) error
}

type Repository interface {
	WaveStore
	TournamentStore
	EntrantStore
	LevelStore
	TableStore
	IngressStore
	ControlStore
	EventStore
	SnapshotStore
	ProjectorStore
	RatingStore
}
