package postgres

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	_ "github.com/lib/pq"

	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/store"
)

var _ store.Repository = (*Repository)(nil)

type Repository struct {
	db *sql.DB
}

func NewRepository(db *sql.DB) (*Repository, error) {
	if db == nil {
		return nil, errors.New("db is required")
	}

	return &Repository{db: db}, nil
}

func (r *Repository) UpsertWave(ctx context.Context, wave model.Wave) error {
	const query = `
		INSERT INTO arena_wave (
			wave_id,
			rated_or_practice,
			wave_state,
			registration_open_at,
			registration_close_at,
			scheduled_start_at,
			target_shard_size,
			soft_min_entrants,
			soft_max_entrants,
			hard_max_entrants,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18
		)
		ON CONFLICT (wave_id) DO UPDATE SET
			rated_or_practice = EXCLUDED.rated_or_practice,
			wave_state = EXCLUDED.wave_state,
			registration_open_at = EXCLUDED.registration_open_at,
			registration_close_at = EXCLUDED.registration_close_at,
			scheduled_start_at = EXCLUDED.scheduled_start_at,
			target_shard_size = EXCLUDED.target_shard_size,
			soft_min_entrants = EXCLUDED.soft_min_entrants,
			soft_max_entrants = EXCLUDED.soft_max_entrants,
			hard_max_entrants = EXCLUDED.hard_max_entrants,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if wave.CreatedAt.IsZero() {
		wave.CreatedAt = now
	}
	if wave.UpdatedAt.IsZero() {
		wave.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		wave.ID,
		string(wave.Mode),
		string(wave.State),
		wave.RegistrationOpenAt,
		wave.RegistrationCloseAt,
		wave.ScheduledStartAt,
		wave.TargetShardSize,
		wave.SoftMinEntrants,
		wave.SoftMaxEntrants,
		wave.HardMaxEntrants,
		defaultSchemaVersion(wave.SchemaVersion),
		defaultString(wave.PolicyBundleVersion, "v1"),
		defaultString(wave.StateHash, wave.ID),
		defaultString(wave.PayloadHash, wave.ID),
		wave.ArtifactRef,
		normalizeJSON(wave.Payload),
		wave.CreatedAt,
		wave.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_wave %s: %w", wave.ID, err)
	}

	return nil
}

func (r *Repository) UpsertTournament(ctx context.Context, tournament model.Tournament) error {
	const query = `
		INSERT INTO arena_tournament (
			tournament_id,
			wave_id,
			rated_or_practice,
			tournament_state,
			exhibition,
			no_multiplier,
			cancelled,
			voided,
			human_only,
			integrity_hold,
			seating_republish_count,
			current_round_no,
			current_level_no,
			players_registered,
			players_confirmed,
			players_remaining,
			active_table_count,
			final_table_table_id,
			rng_root_seed,
			time_cap_at,
			completed_at,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24, $25, $26, $27, $28, $29
		)
		ON CONFLICT (tournament_id) DO UPDATE SET
			wave_id = EXCLUDED.wave_id,
			rated_or_practice = EXCLUDED.rated_or_practice,
			tournament_state = EXCLUDED.tournament_state,
			exhibition = EXCLUDED.exhibition,
			no_multiplier = EXCLUDED.no_multiplier,
			cancelled = EXCLUDED.cancelled,
			voided = EXCLUDED.voided,
			human_only = EXCLUDED.human_only,
			integrity_hold = EXCLUDED.integrity_hold,
			seating_republish_count = EXCLUDED.seating_republish_count,
			current_round_no = EXCLUDED.current_round_no,
			current_level_no = EXCLUDED.current_level_no,
			players_registered = EXCLUDED.players_registered,
			players_confirmed = EXCLUDED.players_confirmed,
			players_remaining = EXCLUDED.players_remaining,
			active_table_count = EXCLUDED.active_table_count,
			final_table_table_id = EXCLUDED.final_table_table_id,
			rng_root_seed = EXCLUDED.rng_root_seed,
			time_cap_at = EXCLUDED.time_cap_at,
			completed_at = EXCLUDED.completed_at,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if tournament.CreatedAt.IsZero() {
		tournament.CreatedAt = now
	}
	if tournament.UpdatedAt.IsZero() {
		tournament.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		tournament.ID,
		tournament.WaveID,
		string(tournament.Mode),
		string(tournament.State),
		tournament.Exhibition,
		tournament.NoMultiplier,
		tournament.Cancelled,
		tournament.Voided,
		tournament.HumanOnly,
		tournament.IntegrityHold,
		tournament.SeatingRepublishCount,
		tournament.CurrentRoundNo,
		tournament.CurrentLevelNo,
		tournament.PlayersRegistered,
		tournament.PlayersConfirmed,
		tournament.PlayersRemaining,
		tournament.ActiveTableCount,
		tournament.FinalTableTableID,
		tournament.RNGRootSeed,
		nullTime(tournament.TimeCapAt),
		nullTime(tournament.CompletedAt),
		defaultSchemaVersion(tournament.SchemaVersion),
		defaultString(tournament.PolicyBundleVersion, "v1"),
		defaultString(tournament.StateHash, tournament.ID),
		defaultString(tournament.PayloadHash, tournament.ID),
		tournament.ArtifactRef,
		normalizeJSON(tournament.Payload),
		tournament.CreatedAt,
		tournament.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_tournament %s: %w", tournament.ID, err)
	}

	return nil
}

func (r *Repository) UpsertEntrant(ctx context.Context, entrant model.Entrant) error {
	const query = `
		INSERT INTO arena_entrant (
			entrant_id,
			wave_id,
			tournament_id,
			miner_id,
			economic_unit_id,
			seat_alias,
			registration_state,
			table_id,
			seat_id,
			finish_rank,
			stage_reached,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19
		)
		ON CONFLICT (entrant_id) DO UPDATE SET
			wave_id = EXCLUDED.wave_id,
			tournament_id = EXCLUDED.tournament_id,
			miner_id = EXCLUDED.miner_id,
			economic_unit_id = EXCLUDED.economic_unit_id,
			seat_alias = EXCLUDED.seat_alias,
			registration_state = EXCLUDED.registration_state,
			table_id = EXCLUDED.table_id,
			seat_id = EXCLUDED.seat_id,
			finish_rank = EXCLUDED.finish_rank,
			stage_reached = EXCLUDED.stage_reached,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if entrant.CreatedAt.IsZero() {
		entrant.CreatedAt = now
	}
	if entrant.UpdatedAt.IsZero() {
		entrant.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		entrant.ID,
		entrant.WaveID,
		nullableString(entrant.TournamentID),
		entrant.MinerID,
		entrant.EconomicUnitID,
		entrant.SeatAlias,
		string(entrant.RegistrationState),
		nullableString(entrant.TableID),
		nullableString(entrant.SeatID),
		entrant.FinishRank,
		entrant.StageReached,
		defaultSchemaVersion(entrant.SchemaVersion),
		defaultString(entrant.PolicyBundleVersion, "v1"),
		defaultString(entrant.StateHash, entrant.ID),
		defaultString(entrant.PayloadHash, entrant.ID),
		entrant.ArtifactRef,
		normalizeJSON(entrant.Payload),
		entrant.CreatedAt,
		entrant.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_entrant %s: %w", entrant.ID, err)
	}

	return nil
}

func (r *Repository) UpsertWaitlistEntry(ctx context.Context, entry model.WaitlistEntry) error {
	const query = `
		INSERT INTO arena_waitlist (
			waitlist_entry_id,
			wave_id,
			entrant_id,
			miner_id,
			registration_state,
			waitlist_position,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14
		)
		ON CONFLICT (waitlist_entry_id) DO UPDATE SET
			wave_id = EXCLUDED.wave_id,
			entrant_id = EXCLUDED.entrant_id,
			miner_id = EXCLUDED.miner_id,
			registration_state = EXCLUDED.registration_state,
			waitlist_position = EXCLUDED.waitlist_position,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if entry.CreatedAt.IsZero() {
		entry.CreatedAt = now
	}
	if entry.UpdatedAt.IsZero() {
		entry.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		entry.ID,
		entry.WaveID,
		entry.EntrantID,
		entry.MinerID,
		string(entry.RegistrationState),
		entry.WaitlistPosition,
		defaultSchemaVersion(entry.SchemaVersion),
		defaultString(entry.PolicyBundleVersion, "v1"),
		defaultString(entry.StateHash, entry.ID),
		defaultString(entry.PayloadHash, entry.ID),
		entry.ArtifactRef,
		normalizeJSON(entry.Payload),
		entry.CreatedAt,
		entry.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_waitlist %s: %w", entry.ID, err)
	}

	return nil
}

func (r *Repository) UpsertPrestartCheck(ctx context.Context, check model.PrestartCheck) error {
	const query = `
		INSERT INTO arena_prestart_check (
			prestart_check_id,
			wave_id,
			entrant_id,
			check_type,
			check_status,
			reason_code,
			checked_at,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15
		)
		ON CONFLICT (prestart_check_id) DO UPDATE SET
			wave_id = EXCLUDED.wave_id,
			entrant_id = EXCLUDED.entrant_id,
			check_type = EXCLUDED.check_type,
			check_status = EXCLUDED.check_status,
			reason_code = EXCLUDED.reason_code,
			checked_at = EXCLUDED.checked_at,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if check.CreatedAt.IsZero() {
		check.CreatedAt = now
	}
	if check.UpdatedAt.IsZero() {
		check.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		check.ID,
		check.WaveID,
		check.EntrantID,
		check.CheckType,
		check.CheckStatus,
		check.ReasonCode,
		defaultTime(check.CheckedAt),
		defaultSchemaVersion(check.SchemaVersion),
		defaultString(check.PolicyBundleVersion, "v1"),
		defaultString(check.StateHash, check.ID),
		defaultString(check.PayloadHash, check.ID),
		check.ArtifactRef,
		normalizeJSON(check.Payload),
		check.CreatedAt,
		check.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_prestart_check %s: %w", check.ID, err)
	}

	return nil
}

func (r *Repository) UpsertShardAssignment(ctx context.Context, assignment model.ShardAssignment) error {
	const query = `
		INSERT INTO arena_shard_assignment (
			shard_assignment_id,
			wave_id,
			tournament_id,
			entrant_id,
			shard_no,
			table_no,
			seat_draw_token,
			assignment_state,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16
		)
		ON CONFLICT (shard_assignment_id) DO UPDATE SET
			wave_id = EXCLUDED.wave_id,
			tournament_id = EXCLUDED.tournament_id,
			entrant_id = EXCLUDED.entrant_id,
			shard_no = EXCLUDED.shard_no,
			table_no = EXCLUDED.table_no,
			seat_draw_token = EXCLUDED.seat_draw_token,
			assignment_state = EXCLUDED.assignment_state,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if assignment.CreatedAt.IsZero() {
		assignment.CreatedAt = now
	}
	if assignment.UpdatedAt.IsZero() {
		assignment.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		assignment.ID,
		assignment.WaveID,
		nullableString(assignment.TournamentID),
		assignment.EntrantID,
		assignment.ShardNo,
		assignment.TableNo,
		assignment.SeatDrawToken,
		assignment.AssignmentState,
		defaultSchemaVersion(assignment.SchemaVersion),
		defaultString(assignment.PolicyBundleVersion, "v1"),
		defaultString(assignment.StateHash, assignment.ID),
		defaultString(assignment.PayloadHash, assignment.ID),
		assignment.ArtifactRef,
		normalizeJSON(assignment.Payload),
		assignment.CreatedAt,
		assignment.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_shard_assignment %s: %w", assignment.ID, err)
	}

	return nil
}

func (r *Repository) UpsertLevel(ctx context.Context, level model.Level) error {
	const query = `
		INSERT INTO arena_level (
			level_id,
			tournament_id,
			level_no,
			small_blind,
			big_blind,
			ante,
			starts_at,
			ends_at,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16
		)
		ON CONFLICT (level_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			level_no = EXCLUDED.level_no,
			small_blind = EXCLUDED.small_blind,
			big_blind = EXCLUDED.big_blind,
			ante = EXCLUDED.ante,
			starts_at = EXCLUDED.starts_at,
			ends_at = EXCLUDED.ends_at,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if level.CreatedAt.IsZero() {
		level.CreatedAt = now
	}
	if level.UpdatedAt.IsZero() {
		level.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		level.ID,
		level.TournamentID,
		level.LevelNo,
		level.SmallBlind,
		level.BigBlind,
		level.Ante,
		defaultTime(level.StartsAt),
		defaultTime(level.EndsAt),
		defaultSchemaVersion(level.SchemaVersion),
		defaultString(level.PolicyBundleVersion, "v1"),
		defaultString(level.StateHash, level.ID),
		defaultString(level.PayloadHash, level.ID),
		level.ArtifactRef,
		normalizeJSON(level.Payload),
		level.CreatedAt,
		level.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_level %s: %w", level.ID, err)
	}

	return nil
}

func (r *Repository) UpsertTable(ctx context.Context, table model.Table) error {
	const query = `
		INSERT INTO arena_table (
			table_id,
			tournament_id,
			table_state,
			table_no,
			round_no,
			current_hand_id,
			button_seat_no,
			acting_seat_no,
			current_to_call,
			min_raise_size,
			pot_main,
			state_seq,
			level_no,
			is_final_table,
			paused_for_rebalance,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24, $25, $26, $27, $28
		)
		ON CONFLICT (table_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			table_state = EXCLUDED.table_state,
			table_no = EXCLUDED.table_no,
			round_no = EXCLUDED.round_no,
			current_hand_id = EXCLUDED.current_hand_id,
			button_seat_no = EXCLUDED.button_seat_no,
			acting_seat_no = EXCLUDED.acting_seat_no,
			current_to_call = EXCLUDED.current_to_call,
			min_raise_size = EXCLUDED.min_raise_size,
			pot_main = EXCLUDED.pot_main,
			state_seq = EXCLUDED.state_seq,
			level_no = EXCLUDED.level_no,
			is_final_table = EXCLUDED.is_final_table,
			paused_for_rebalance = EXCLUDED.paused_for_rebalance,
			rng_root_seed = EXCLUDED.rng_root_seed,
			seed_table_id = EXCLUDED.seed_table_id,
			seed_hand_no = EXCLUDED.seed_hand_no,
			seed_seat_no = EXCLUDED.seed_seat_no,
			seed_stream_name = EXCLUDED.seed_stream_name,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if table.CreatedAt.IsZero() {
		table.CreatedAt = now
	}
	if table.UpdatedAt.IsZero() {
		table.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		table.ID,
		table.TournamentID,
		string(table.State),
		table.TableNo,
		table.RoundNo,
		table.CurrentHandID,
		table.ButtonSeatNo,
		table.ActingSeatNo,
		table.CurrentToCall,
		table.MinRaiseSize,
		table.PotMain,
		table.StateSeq,
		table.LevelNo,
		table.IsFinalTable,
		table.PausedForRebalance,
		table.RNGRootSeed,
		defaultString(table.SeedDerivation.TableID, table.ID),
		table.SeedDerivation.HandNumber,
		table.SeedDerivation.SeatNumber,
		table.SeedDerivation.StreamName,
		defaultSchemaVersion(table.SchemaVersion),
		defaultString(table.PolicyBundleVersion, "v1"),
		defaultString(table.StateHash, table.ID),
		defaultString(table.PayloadHash, table.ID),
		table.ArtifactRef,
		normalizeJSON(table.Payload),
		table.CreatedAt,
		table.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_table %s: %w", table.ID, err)
	}

	return nil
}

func (r *Repository) UpsertHand(ctx context.Context, hand model.Hand) error {
	const query = `
		INSERT INTO arena_hand (
			hand_id,
			table_id,
			tournament_id,
			round_no,
			level_no,
			hand_state,
			hand_started_at,
			hand_closed_at,
			button_seat_no,
			active_seat_count,
			pot_main,
			winner_count,
			time_cap_forced_last_hand,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24, $25, $26
		)
		ON CONFLICT (hand_id) DO UPDATE SET
			table_id = EXCLUDED.table_id,
			tournament_id = EXCLUDED.tournament_id,
			round_no = EXCLUDED.round_no,
			level_no = EXCLUDED.level_no,
			hand_state = EXCLUDED.hand_state,
			hand_started_at = EXCLUDED.hand_started_at,
			hand_closed_at = EXCLUDED.hand_closed_at,
			button_seat_no = EXCLUDED.button_seat_no,
			active_seat_count = EXCLUDED.active_seat_count,
			pot_main = EXCLUDED.pot_main,
			winner_count = EXCLUDED.winner_count,
			time_cap_forced_last_hand = EXCLUDED.time_cap_forced_last_hand,
			rng_root_seed = EXCLUDED.rng_root_seed,
			seed_table_id = EXCLUDED.seed_table_id,
			seed_hand_no = EXCLUDED.seed_hand_no,
			seed_seat_no = EXCLUDED.seed_seat_no,
			seed_stream_name = EXCLUDED.seed_stream_name,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if hand.CreatedAt.IsZero() {
		hand.CreatedAt = now
	}
	if hand.UpdatedAt.IsZero() {
		hand.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		hand.ID,
		hand.TableID,
		hand.TournamentID,
		hand.RoundNo,
		hand.LevelNo,
		string(hand.State),
		defaultTime(hand.HandStartedAt),
		nullTime(hand.HandClosedAt),
		hand.ButtonSeatNo,
		hand.ActiveSeatCount,
		hand.PotMain,
		hand.WinnerCount,
		hand.TimeCapForcedLastHand,
		hand.RNGRootSeed,
		defaultString(hand.SeedDerivation.TableID, hand.TableID),
		hand.SeedDerivation.HandNumber,
		hand.SeedDerivation.SeatNumber,
		hand.SeedDerivation.StreamName,
		defaultSchemaVersion(hand.SchemaVersion),
		defaultString(hand.PolicyBundleVersion, "v1"),
		defaultString(hand.StateHash, hand.ID),
		defaultString(hand.PayloadHash, hand.ID),
		hand.ArtifactRef,
		normalizeJSON(hand.Payload),
		hand.CreatedAt,
		hand.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_hand %s: %w", hand.ID, err)
	}

	return nil
}

func (r *Repository) UpsertPhase(ctx context.Context, phase model.Phase) error {
	const query = `
		INSERT INTO arena_phase (
			phase_id,
			hand_id,
			table_id,
			phase_type,
			phase_state,
			opened_at,
			deadline_at,
			closed_at,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21
		)
		ON CONFLICT (phase_id) DO UPDATE SET
			hand_id = EXCLUDED.hand_id,
			table_id = EXCLUDED.table_id,
			phase_type = EXCLUDED.phase_type,
			phase_state = EXCLUDED.phase_state,
			opened_at = EXCLUDED.opened_at,
			deadline_at = EXCLUDED.deadline_at,
			closed_at = EXCLUDED.closed_at,
			rng_root_seed = EXCLUDED.rng_root_seed,
			seed_table_id = EXCLUDED.seed_table_id,
			seed_hand_no = EXCLUDED.seed_hand_no,
			seed_seat_no = EXCLUDED.seed_seat_no,
			seed_stream_name = EXCLUDED.seed_stream_name,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if phase.CreatedAt.IsZero() {
		phase.CreatedAt = now
	}
	if phase.UpdatedAt.IsZero() {
		phase.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		phase.ID,
		phase.HandID,
		phase.TableID,
		string(phase.Type),
		string(phase.State),
		defaultTime(phase.OpenedAt),
		nullTime(phase.DeadlineAt),
		nullTime(phase.ClosedAt),
		phase.RNGRootSeed,
		phase.SeedDerivation.TableID,
		phase.SeedDerivation.HandNumber,
		phase.SeedDerivation.SeatNumber,
		phase.SeedDerivation.StreamName,
		defaultSchemaVersion(phase.SchemaVersion),
		defaultString(phase.PolicyBundleVersion, "v1"),
		defaultString(phase.StateHash, phase.ID),
		defaultString(phase.PayloadHash, phase.ID),
		phase.ArtifactRef,
		normalizeJSON(phase.Payload),
		phase.CreatedAt,
		phase.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_phase %s: %w", phase.ID, err)
	}

	return nil
}

func (r *Repository) UpsertSeat(ctx context.Context, seat model.Seat) error {
	const query = `
		INSERT INTO arena_seat (
			seat_id,
			table_id,
			tournament_id,
			entrant_id,
			seat_no,
			seat_alias,
			miner_id,
			seat_state,
			stack,
			timeout_streak,
			sit_out_warning_count,
			last_forced_blind_round,
			last_manual_action_at,
			tournament_seat_draw_token,
			admin_status_overlay,
			removed_reason,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24, $25, $26, $27, $28, $29
		)
		ON CONFLICT (seat_id) DO UPDATE SET
			table_id = EXCLUDED.table_id,
			tournament_id = EXCLUDED.tournament_id,
			entrant_id = EXCLUDED.entrant_id,
			seat_no = EXCLUDED.seat_no,
			seat_alias = EXCLUDED.seat_alias,
			miner_id = EXCLUDED.miner_id,
			seat_state = EXCLUDED.seat_state,
			stack = EXCLUDED.stack,
			timeout_streak = EXCLUDED.timeout_streak,
			sit_out_warning_count = EXCLUDED.sit_out_warning_count,
			last_forced_blind_round = EXCLUDED.last_forced_blind_round,
			last_manual_action_at = EXCLUDED.last_manual_action_at,
			tournament_seat_draw_token = EXCLUDED.tournament_seat_draw_token,
			admin_status_overlay = EXCLUDED.admin_status_overlay,
			removed_reason = EXCLUDED.removed_reason,
			rng_root_seed = EXCLUDED.rng_root_seed,
			seed_table_id = EXCLUDED.seed_table_id,
			seed_hand_no = EXCLUDED.seed_hand_no,
			seed_seat_no = EXCLUDED.seed_seat_no,
			seed_stream_name = EXCLUDED.seed_stream_name,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if seat.CreatedAt.IsZero() {
		seat.CreatedAt = now
	}
	if seat.UpdatedAt.IsZero() {
		seat.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		seat.ID,
		seat.TableID,
		seat.TournamentID,
		nullableString(seat.EntrantID),
		seat.SeatNo,
		seat.SeatAlias,
		seat.MinerID,
		string(seat.State),
		seat.Stack,
		seat.TimeoutStreak,
		seat.SitOutWarningCount,
		seat.LastForcedBlindRound,
		nullTime(seat.LastManualActionAt),
		seat.TournamentSeatDrawToken,
		seat.AdminStatusOverlay,
		seat.RemovedReason,
		seat.RNGRootSeed,
		defaultString(seat.SeedDerivation.TableID, seat.TableID),
		seat.SeedDerivation.HandNumber,
		seat.SeedDerivation.SeatNumber,
		seat.SeedDerivation.StreamName,
		defaultSchemaVersion(seat.SchemaVersion),
		defaultString(seat.PolicyBundleVersion, "v1"),
		defaultString(seat.StateHash, seat.ID),
		defaultString(seat.PayloadHash, seat.ID),
		seat.ArtifactRef,
		normalizeJSON(seat.Payload),
		seat.CreatedAt,
		seat.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_seat %s: %w", seat.ID, err)
	}

	return nil
}

func (r *Repository) UpsertAliasMap(ctx context.Context, alias model.AliasMap) error {
	const query = `
		INSERT INTO arena_alias_map (
			alias_map_id,
			tournament_id,
			table_id,
			seat_id,
			entrant_id,
			seat_alias,
			miner_id,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15
		)
		ON CONFLICT (alias_map_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			table_id = EXCLUDED.table_id,
			seat_id = EXCLUDED.seat_id,
			entrant_id = EXCLUDED.entrant_id,
			seat_alias = EXCLUDED.seat_alias,
			miner_id = EXCLUDED.miner_id,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if alias.CreatedAt.IsZero() {
		alias.CreatedAt = now
	}
	if alias.UpdatedAt.IsZero() {
		alias.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		alias.ID,
		alias.TournamentID,
		nullableString(alias.TableID),
		nullableString(alias.SeatID),
		nullableString(alias.EntrantID),
		alias.SeatAlias,
		alias.MinerID,
		defaultSchemaVersion(alias.SchemaVersion),
		defaultString(alias.PolicyBundleVersion, "v1"),
		defaultString(alias.StateHash, alias.ID),
		defaultString(alias.PayloadHash, alias.ID),
		alias.ArtifactRef,
		normalizeJSON(alias.Payload),
		alias.CreatedAt,
		alias.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_alias_map %s: %w", alias.ID, err)
	}

	return nil
}

func (r *Repository) AppendSubmissionLedgerEntries(ctx context.Context, entries []model.SubmissionLedger) error {
	const query = `
		INSERT INTO submission_ledger (
			request_id,
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			seat_id,
			seat_alias,
			miner_id,
			expected_state_seq,
			validation_status,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload_artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19
		)
		ON CONFLICT (request_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			table_id = EXCLUDED.table_id,
			hand_id = EXCLUDED.hand_id,
			phase_id = EXCLUDED.phase_id,
			seat_id = EXCLUDED.seat_id,
			seat_alias = EXCLUDED.seat_alias,
			miner_id = EXCLUDED.miner_id,
			expected_state_seq = EXCLUDED.expected_state_seq,
			validation_status = EXCLUDED.validation_status,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload_artifact_ref = EXCLUDED.payload_artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
		WHERE submission_ledger.payload_hash = EXCLUDED.payload_hash
	`

	for _, entry := range entries {
		now := nowUTC()
		if entry.CreatedAt.IsZero() {
			entry.CreatedAt = now
		}
		if entry.UpdatedAt.IsZero() {
			entry.UpdatedAt = now
		}

		result, err := r.db.ExecContext(
			ctx,
			query,
			entry.RequestID,
			entry.TournamentID,
			entry.TableID,
			entry.HandID,
			entry.PhaseID,
			entry.SeatID,
			entry.SeatAlias,
			entry.MinerID,
			entry.ExpectedStateSeq,
			entry.ValidationStatus,
			defaultSchemaVersion(entry.SchemaVersion),
			defaultString(entry.PolicyBundleVersion, "v1"),
			defaultString(entry.StateHash, entry.RequestID),
			defaultString(entry.PayloadHash, entry.RequestID),
			entry.ArtifactRef,
			entry.PayloadArtifactRef,
			normalizeJSON(entry.Payload),
			entry.CreatedAt,
			entry.UpdatedAt,
		)
		if err != nil {
			return fmt.Errorf("append submission_ledger %s: %w", entry.RequestID, err)
		}
		rowsAffected, err := result.RowsAffected()
		if err != nil {
			return fmt.Errorf("append submission_ledger %s rows affected: %w", entry.RequestID, err)
		}
		if rowsAffected == 0 {
			return fmt.Errorf("append submission_ledger %s: request_id payload conflict", entry.RequestID)
		}
	}

	return nil
}

func (r *Repository) AppendActionRecords(ctx context.Context, actions []model.ActionRecord) error {
	const query = `
		INSERT INTO arena_action (
			request_id,
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			seat_id,
			seat_alias,
			action_type,
			action_amount_bucket,
			action_seq,
			expected_state_seq,
			accepted_state_seq,
			validation_status,
			result_event_id,
			received_at,
			processed_at,
			error_code,
			duplicate_of_request_id,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24
		)
		ON CONFLICT (request_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			table_id = EXCLUDED.table_id,
			hand_id = EXCLUDED.hand_id,
			phase_id = EXCLUDED.phase_id,
			seat_id = EXCLUDED.seat_id,
			seat_alias = EXCLUDED.seat_alias,
			action_type = EXCLUDED.action_type,
			action_amount_bucket = EXCLUDED.action_amount_bucket,
			action_seq = EXCLUDED.action_seq,
			expected_state_seq = EXCLUDED.expected_state_seq,
			accepted_state_seq = EXCLUDED.accepted_state_seq,
			validation_status = EXCLUDED.validation_status,
			result_event_id = EXCLUDED.result_event_id,
			received_at = EXCLUDED.received_at,
			processed_at = EXCLUDED.processed_at,
			error_code = EXCLUDED.error_code,
			duplicate_of_request_id = EXCLUDED.duplicate_of_request_id,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload
		`

	for _, action := range actions {
		receivedAt := action.ReceivedAt
		if receivedAt.IsZero() {
			receivedAt = nowUTC()
		}

		_, err := r.db.ExecContext(
			ctx,
			query,
			action.RequestID,
			action.TournamentID,
			action.TableID,
			action.HandID,
			action.PhaseID,
			action.SeatID,
			action.SeatAlias,
			action.ActionType,
			action.ActionAmountBucket,
			action.ActionSeq,
			action.ExpectedStateSeq,
			action.AcceptedStateSeq,
			action.ValidationStatus,
			action.ResultEventID,
			receivedAt,
			nullTime(action.ProcessedAt),
			action.ErrorCode,
			action.DuplicateOfRequestID,
			defaultSchemaVersion(action.SchemaVersion),
			defaultString(action.PolicyBundleVersion, "v1"),
			defaultString(action.StateHash, action.RequestID),
			defaultString(action.PayloadHash, action.RequestID),
			action.ArtifactRef,
			normalizeJSON(action.Payload),
		)
		if err != nil {
			existing, loadErr := r.loadArenaActionLogicalIdentity(
				ctx,
				action.HandID,
				action.SeatID,
				action.PhaseID,
				action.ActionSeq,
			)
			if loadErr == nil {
				if conflict := compareArenaActionLogicalIdentity(existing, buildArenaActionLogicalIdentity(action)); conflict == "" {
					continue
				} else {
					return fmt.Errorf("append arena_action %s conflict: %s", action.RequestID, conflict)
				}
			}
			return fmt.Errorf("append arena_action %s: %w", action.RequestID, err)
		}
	}

	return nil
}

func (r *Repository) ListActionMeasurementSummaries(ctx context.Context, tournamentID string) ([]model.ActionMeasurementSummary, error) {
	rows, err := r.db.QueryContext(ctx, `
		WITH resolved_actions AS (
			SELECT
				COALESCE(NULLIF(sl.miner_id, ''), NULLIF(seat.miner_id, '')) AS miner_id,
				NULLIF(a.hand_id, '') AS hand_id,
				a.action_type,
				a.validation_status,
				a.error_code
			FROM arena_action a
			LEFT JOIN submission_ledger sl ON sl.request_id = a.request_id
			LEFT JOIN arena_seat seat ON seat.seat_id = a.seat_id
			WHERE a.tournament_id = $1
		),
		action_summary AS (
			SELECT
				miner_id,
				COUNT(DISTINCT hand_id) FILTER (WHERE hand_id IS NOT NULL) AS hands_played,
				COUNT(*) FILTER (
					WHERE validation_status = 'accepted'
						AND action_type <> ''
						AND action_type NOT IN ('start_hand', 'close_hand', 'timeout', 'auto_check', 'auto_fold')
				) AS meaningful_decisions,
				COUNT(*) FILTER (
					WHERE validation_status = 'accepted'
						AND action_type IN ('auto_check', 'auto_fold', 'timeout')
				) AS auto_actions,
				COUNT(*) FILTER (
					WHERE validation_status = 'accepted'
						AND action_type = 'timeout'
				) AS timeout_actions,
				COUNT(*) FILTER (
					WHERE action_type NOT IN ('start_hand', 'close_hand')
						AND (validation_status <> 'accepted' OR error_code <> '')
				) AS invalid_actions
			FROM resolved_actions
			WHERE miner_id IS NOT NULL
			GROUP BY miner_id
		),
		invalid_submission_summary AS (
			SELECT
				sl.miner_id,
				COUNT(*) AS invalid_actions
			FROM submission_ledger sl
			LEFT JOIN arena_action a ON a.request_id = sl.request_id
			WHERE sl.tournament_id = $1
				AND sl.miner_id <> ''
				AND a.request_id IS NULL
				AND sl.validation_status <> 'applied'
			GROUP BY sl.miner_id
		),
		miners AS (
			SELECT miner_id FROM action_summary
			UNION
			SELECT miner_id FROM invalid_submission_summary
		)
		SELECT
			miners.miner_id,
			COALESCE(action_summary.hands_played, 0) AS hands_played,
			COALESCE(action_summary.meaningful_decisions, 0) AS meaningful_decisions,
			COALESCE(action_summary.auto_actions, 0) AS auto_actions,
			COALESCE(action_summary.timeout_actions, 0) AS timeout_actions,
			COALESCE(action_summary.invalid_actions, 0) + COALESCE(invalid_submission_summary.invalid_actions, 0) AS invalid_actions
		FROM miners
		LEFT JOIN action_summary ON action_summary.miner_id = miners.miner_id
		LEFT JOIN invalid_submission_summary ON invalid_submission_summary.miner_id = miners.miner_id
		ORDER BY miners.miner_id
	`, tournamentID)
	if err != nil {
		return nil, fmt.Errorf("list action measurement summaries for %s: %w", tournamentID, err)
	}
	defer rows.Close()

	summaries := make([]model.ActionMeasurementSummary, 0)
	for rows.Next() {
		var summary model.ActionMeasurementSummary
		if err := rows.Scan(
			&summary.MinerID,
			&summary.HandsPlayed,
			&summary.MeaningfulDecisions,
			&summary.AutoActions,
			&summary.TimeoutActions,
			&summary.InvalidActions,
		); err != nil {
			return nil, fmt.Errorf("scan action measurement summary for %s: %w", tournamentID, err)
		}
		summaries = append(summaries, summary)
	}
	return summaries, rows.Err()
}

func (r *Repository) AppendReseatEvents(ctx context.Context, events []model.ReseatEvent) error {
	const query = `
		INSERT INTO arena_reseat_event (
			reseat_event_id,
			tournament_id,
			from_table_id,
			to_table_id,
			seat_id,
			entrant_id,
			round_no,
			caused_by_barrier_id,
			occurred_at,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16
		)
		ON CONFLICT (reseat_event_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			from_table_id = EXCLUDED.from_table_id,
			to_table_id = EXCLUDED.to_table_id,
			seat_id = EXCLUDED.seat_id,
			entrant_id = EXCLUDED.entrant_id,
			round_no = EXCLUDED.round_no,
			caused_by_barrier_id = EXCLUDED.caused_by_barrier_id,
			occurred_at = EXCLUDED.occurred_at,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			created_at = EXCLUDED.created_at
	`

	for _, event := range events {
		_, err := r.db.ExecContext(
			ctx,
			query,
			event.ID,
			event.TournamentID,
			nullableString(event.FromTableID),
			nullableString(event.ToTableID),
			nullableString(event.SeatID),
			nullableString(event.EntrantID),
			event.RoundNo,
			event.CausedByBarrierID,
			defaultTime(event.OccurredAt),
			defaultSchemaVersion(event.SchemaVersion),
			defaultString(event.PolicyBundleVersion, "v1"),
			defaultString(event.StateHash, event.ID),
			defaultString(event.PayloadHash, event.ID),
			event.ArtifactRef,
			normalizeJSON(event.Payload),
			defaultTime(event.CreatedAt),
		)
		if err != nil {
			return fmt.Errorf("append arena_reseat_event %s: %w", event.ID, err)
		}
	}

	return nil
}

func (r *Repository) AppendEliminationEvents(ctx context.Context, events []model.EliminationEvent) error {
	const query = `
		INSERT INTO arena_elimination_event (
			elimination_event_id,
			tournament_id,
			table_id,
			hand_id,
			seat_id,
			entrant_id,
			finish_rank,
			stage_reached,
			occurred_at,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16
		)
		ON CONFLICT (elimination_event_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			table_id = EXCLUDED.table_id,
			hand_id = EXCLUDED.hand_id,
			seat_id = EXCLUDED.seat_id,
			entrant_id = EXCLUDED.entrant_id,
			finish_rank = EXCLUDED.finish_rank,
			stage_reached = EXCLUDED.stage_reached,
			occurred_at = EXCLUDED.occurred_at,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			created_at = EXCLUDED.created_at
	`

	for _, event := range events {
		_, err := r.db.ExecContext(
			ctx,
			query,
			event.ID,
			event.TournamentID,
			nullableString(event.TableID),
			nullableString(event.HandID),
			nullableString(event.SeatID),
			nullableString(event.EntrantID),
			event.FinishRank,
			event.StageReached,
			defaultTime(event.OccurredAt),
			defaultSchemaVersion(event.SchemaVersion),
			defaultString(event.PolicyBundleVersion, "v1"),
			defaultString(event.StateHash, event.ID),
			defaultString(event.PayloadHash, event.ID),
			event.ArtifactRef,
			normalizeJSON(event.Payload),
			defaultTime(event.CreatedAt),
		)
		if err != nil {
			return fmt.Errorf("append arena_elimination_event %s: %w", event.ID, err)
		}
	}

	return nil
}

func (r *Repository) AppendEvents(ctx context.Context, events []model.EventLogEntry) error {
	const query = `
		INSERT INTO arena_event_log (
			event_id,
			aggregate_type,
			aggregate_id,
			stream_key,
			stream_seq,
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			round_no,
			barrier_id,
			event_type,
			event_version,
			schema_version,
			policy_bundle_version,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			state_seq,
			causation_id,
			correlation_id,
			occurred_at,
			payload,
			payload_uri,
			payload_hash,
			artifact_ref,
			state_hash_after
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24, $25, $26, $27, $28, $29
		)
		ON CONFLICT (event_id) DO NOTHING
	`

	for _, event := range events {
		occurredAt := event.OccurredAt
		if occurredAt.IsZero() {
			occurredAt = nowUTC()
		}

		result, err := r.db.ExecContext(
			ctx,
			query,
			event.EventID,
			event.AggregateType,
			event.AggregateID,
			event.StreamKey,
			event.StreamSeq,
			event.TournamentID,
			event.TableID,
			event.HandID,
			event.PhaseID,
			event.RoundNo,
			event.BarrierID,
			event.EventType,
			defaultInt(event.EventVersion, 1),
			defaultSchemaVersion(event.SchemaVersion),
			defaultString(event.PolicyBundleVersion, "v1"),
			event.RNGRootSeed,
			event.SeedDerivation.TableID,
			event.SeedDerivation.HandNumber,
			event.SeedDerivation.SeatNumber,
			event.SeedDerivation.StreamName,
			event.StateSeq,
			event.CausationID,
			event.CorrelationID,
			occurredAt,
			normalizeJSON(event.Payload),
			event.PayloadURI,
			defaultString(event.PayloadHash, event.EventID),
			event.ArtifactRef,
			defaultString(event.StateHashAfter, event.EventID),
		)
		if err != nil {
			return fmt.Errorf("append arena_event_log %s: %w", event.EventID, err)
		}
		rowsAffected, err := result.RowsAffected()
		if err != nil {
			return fmt.Errorf("append arena_event_log %s rows affected: %w", event.EventID, err)
		}
		if rowsAffected > 0 {
			continue
		}
		existing, err := r.loadArenaEventLogIdentity(ctx, event.EventID)
		if err != nil {
			return fmt.Errorf("load arena_event_log %s: %w", event.EventID, err)
		}
		if conflict := compareArenaEventLogIdentity(existing, buildArenaEventLogIdentity(event)); conflict != "" {
			return fmt.Errorf("append arena_event_log %s conflict: %s", event.EventID, conflict)
		}
	}

	return nil
}

func (r *Repository) UpsertActionDeadline(ctx context.Context, deadline model.ActionDeadline) error {
	const query = `
		INSERT INTO arena_action_deadline (
			deadline_id,
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			seat_id,
			deadline_at,
			status,
			opened_by_event_id,
			resolved_by_event_id,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18
		)
		ON CONFLICT (deadline_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			table_id = EXCLUDED.table_id,
			hand_id = EXCLUDED.hand_id,
			phase_id = EXCLUDED.phase_id,
			seat_id = EXCLUDED.seat_id,
			deadline_at = EXCLUDED.deadline_at,
			status = EXCLUDED.status,
			opened_by_event_id = EXCLUDED.opened_by_event_id,
			resolved_by_event_id = EXCLUDED.resolved_by_event_id,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if deadline.CreatedAt.IsZero() {
		deadline.CreatedAt = now
	}
	if deadline.UpdatedAt.IsZero() {
		deadline.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		deadline.DeadlineID,
		deadline.TournamentID,
		deadline.TableID,
		deadline.HandID,
		deadline.PhaseID,
		deadline.SeatID,
		deadline.DeadlineAt,
		deadline.Status,
		deadline.OpenedByEventID,
		deadline.ResolvedByEventID,
		defaultSchemaVersion(deadline.SchemaVersion),
		defaultString(deadline.PolicyBundleVersion, "v1"),
		defaultString(deadline.StateHash, deadline.DeadlineID),
		defaultString(deadline.PayloadHash, deadline.DeadlineID),
		deadline.ArtifactRef,
		normalizeJSON(deadline.Payload),
		deadline.CreatedAt,
		deadline.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_action_deadline %s: %w", deadline.DeadlineID, err)
	}

	return nil
}

func (r *Repository) UpsertRoundBarrier(ctx context.Context, barrier model.RoundBarrier) error {
	const query = `
		INSERT INTO arena_round_barrier (
			barrier_id,
			tournament_id,
			round_no,
			expected_table_count,
			received_hand_close_count,
			barrier_state,
			pending_reseat_plan_ref,
			pending_level_no,
			terminate_after_current_round,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17
		)
		ON CONFLICT (barrier_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			round_no = EXCLUDED.round_no,
			expected_table_count = EXCLUDED.expected_table_count,
			received_hand_close_count = EXCLUDED.received_hand_close_count,
			barrier_state = EXCLUDED.barrier_state,
			pending_reseat_plan_ref = EXCLUDED.pending_reseat_plan_ref,
			pending_level_no = EXCLUDED.pending_level_no,
			terminate_after_current_round = EXCLUDED.terminate_after_current_round,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if barrier.CreatedAt.IsZero() {
		barrier.CreatedAt = now
	}
	if barrier.UpdatedAt.IsZero() {
		barrier.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		barrier.ID,
		barrier.TournamentID,
		barrier.RoundNo,
		barrier.ExpectedTableCount,
		barrier.ReceivedHandCloseCount,
		barrier.BarrierState,
		barrier.PendingReseatPlanRef,
		barrier.PendingLevelNo,
		barrier.TerminateAfterCurrentRound,
		defaultSchemaVersion(barrier.SchemaVersion),
		defaultString(barrier.PolicyBundleVersion, "v1"),
		defaultString(barrier.StateHash, barrier.ID),
		defaultString(barrier.PayloadHash, barrier.ID),
		barrier.ArtifactRef,
		normalizeJSON(barrier.Payload),
		barrier.CreatedAt,
		barrier.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_round_barrier %s: %w", barrier.ID, err)
	}

	return nil
}

func (r *Repository) UpsertOperatorIntervention(ctx context.Context, intervention model.OperatorIntervention) error {
	const query = `
		INSERT INTO arena_operator_intervention (
			intervention_id,
			tournament_id,
			table_id,
			seat_id,
			miner_id,
			intervention_type,
			status,
			requested_by,
			requested_at,
			effective_at_safe_point,
			reason_code,
			reason_detail,
			created_event_id,
			resolved_event_id,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22
		)
		ON CONFLICT (intervention_id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			table_id = EXCLUDED.table_id,
			seat_id = EXCLUDED.seat_id,
			miner_id = EXCLUDED.miner_id,
			intervention_type = EXCLUDED.intervention_type,
			status = EXCLUDED.status,
			requested_by = EXCLUDED.requested_by,
			requested_at = EXCLUDED.requested_at,
			effective_at_safe_point = EXCLUDED.effective_at_safe_point,
			reason_code = EXCLUDED.reason_code,
			reason_detail = EXCLUDED.reason_detail,
			created_event_id = EXCLUDED.created_event_id,
			resolved_event_id = EXCLUDED.resolved_event_id,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if intervention.CreatedAt.IsZero() {
		intervention.CreatedAt = now
	}
	if intervention.UpdatedAt.IsZero() {
		intervention.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		intervention.ID,
		intervention.TournamentID,
		nullableString(intervention.TableID),
		nullableString(intervention.SeatID),
		intervention.MinerID,
		intervention.InterventionType,
		intervention.Status,
		intervention.RequestedBy,
		defaultTime(intervention.RequestedAt),
		intervention.EffectiveAtSafePoint,
		intervention.ReasonCode,
		intervention.ReasonDetail,
		intervention.CreatedEventID,
		intervention.ResolvedEventID,
		defaultSchemaVersion(intervention.SchemaVersion),
		defaultString(intervention.PolicyBundleVersion, "v1"),
		defaultString(intervention.StateHash, intervention.ID),
		defaultString(intervention.PayloadHash, intervention.ID),
		intervention.ArtifactRef,
		normalizeJSON(intervention.Payload),
		intervention.CreatedAt,
		intervention.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_operator_intervention %s: %w", intervention.ID, err)
	}

	return nil
}

func (r *Repository) SaveTournamentSnapshot(ctx context.Context, snapshot model.TournamentSnapshot) error {
	const query = `
		INSERT INTO arena_tournament_snapshot (
			snapshot_id,
			tournament_id,
			stream_key,
			stream_seq,
			state_seq,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17
		)
		ON CONFLICT (snapshot_id) DO UPDATE SET
			stream_key = EXCLUDED.stream_key,
			stream_seq = EXCLUDED.stream_seq,
			state_seq = EXCLUDED.state_seq,
			rng_root_seed = EXCLUDED.rng_root_seed,
			seed_table_id = EXCLUDED.seed_table_id,
			seed_hand_no = EXCLUDED.seed_hand_no,
			seed_seat_no = EXCLUDED.seed_seat_no,
			seed_stream_name = EXCLUDED.seed_stream_name,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			created_at = EXCLUDED.created_at
	`

	return execSnapshot(
		ctx,
		r.db,
		query,
		snapshot.ID,
		snapshot.TournamentID,
		snapshot.StreamKey,
		snapshot.StreamSeq,
		snapshot.StateSeq,
		snapshot.RNGRootSeed,
		snapshot.SeedDerivation.TableID,
		snapshot.SeedDerivation.HandNumber,
		snapshot.SeedDerivation.SeatNumber,
		snapshot.SeedDerivation.StreamName,
		defaultSchemaVersion(snapshot.SchemaVersion),
		defaultString(snapshot.PolicyBundleVersion, "v1"),
		defaultString(snapshot.StateHash, snapshot.ID),
		defaultString(snapshot.PayloadHash, snapshot.ID),
		snapshot.ArtifactRef,
		normalizeJSON(snapshot.Payload),
		defaultTime(snapshot.CreatedAt),
	)
}

func (r *Repository) SaveTableSnapshot(ctx context.Context, snapshot model.TableSnapshot) error {
	const query = `
		INSERT INTO arena_table_snapshot (
			snapshot_id,
			tournament_id,
			table_id,
			stream_key,
			stream_seq,
			state_seq,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18
		)
		ON CONFLICT (snapshot_id) DO UPDATE SET
			stream_key = EXCLUDED.stream_key,
			stream_seq = EXCLUDED.stream_seq,
			state_seq = EXCLUDED.state_seq,
			rng_root_seed = EXCLUDED.rng_root_seed,
			seed_table_id = EXCLUDED.seed_table_id,
			seed_hand_no = EXCLUDED.seed_hand_no,
			seed_seat_no = EXCLUDED.seed_seat_no,
			seed_stream_name = EXCLUDED.seed_stream_name,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			created_at = EXCLUDED.created_at
	`

	return execSnapshot(
		ctx,
		r.db,
		query,
		snapshot.ID,
		snapshot.TournamentID,
		snapshot.TableID,
		snapshot.StreamKey,
		snapshot.StreamSeq,
		snapshot.StateSeq,
		snapshot.RNGRootSeed,
		defaultString(snapshot.SeedDerivation.TableID, snapshot.TableID),
		snapshot.SeedDerivation.HandNumber,
		snapshot.SeedDerivation.SeatNumber,
		snapshot.SeedDerivation.StreamName,
		defaultSchemaVersion(snapshot.SchemaVersion),
		defaultString(snapshot.PolicyBundleVersion, "v1"),
		defaultString(snapshot.StateHash, snapshot.ID),
		defaultString(snapshot.PayloadHash, snapshot.ID),
		snapshot.ArtifactRef,
		normalizeJSON(snapshot.Payload),
		defaultTime(snapshot.CreatedAt),
	)
}

func (r *Repository) SaveHandSnapshot(ctx context.Context, snapshot model.HandSnapshot) error {
	const query = `
		INSERT INTO arena_hand_snapshot (
			snapshot_id,
			tournament_id,
			table_id,
			hand_id,
			stream_key,
			stream_seq,
			state_seq,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19
		)
		ON CONFLICT (snapshot_id) DO UPDATE SET
			stream_key = EXCLUDED.stream_key,
			stream_seq = EXCLUDED.stream_seq,
			state_seq = EXCLUDED.state_seq,
			rng_root_seed = EXCLUDED.rng_root_seed,
			seed_table_id = EXCLUDED.seed_table_id,
			seed_hand_no = EXCLUDED.seed_hand_no,
			seed_seat_no = EXCLUDED.seed_seat_no,
			seed_stream_name = EXCLUDED.seed_stream_name,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			created_at = EXCLUDED.created_at
	`

	return execSnapshot(
		ctx,
		r.db,
		query,
		snapshot.ID,
		snapshot.TournamentID,
		snapshot.TableID,
		snapshot.HandID,
		snapshot.StreamKey,
		snapshot.StreamSeq,
		snapshot.StateSeq,
		snapshot.RNGRootSeed,
		defaultString(snapshot.SeedDerivation.TableID, snapshot.TableID),
		snapshot.SeedDerivation.HandNumber,
		snapshot.SeedDerivation.SeatNumber,
		snapshot.SeedDerivation.StreamName,
		defaultSchemaVersion(snapshot.SchemaVersion),
		defaultString(snapshot.PolicyBundleVersion, "v1"),
		defaultString(snapshot.StateHash, snapshot.ID),
		defaultString(snapshot.PayloadHash, snapshot.ID),
		snapshot.ArtifactRef,
		normalizeJSON(snapshot.Payload),
		defaultTime(snapshot.CreatedAt),
	)
}

func (r *Repository) SaveStandingSnapshot(ctx context.Context, snapshot model.StandingSnapshot) error {
	const query = `
		INSERT INTO arena_standing_snapshot (
			snapshot_id,
			tournament_id,
			stream_key,
			stream_seq,
			state_seq,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			payload,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
		)
		ON CONFLICT (snapshot_id) DO UPDATE SET
			stream_key = EXCLUDED.stream_key,
			stream_seq = EXCLUDED.stream_seq,
			state_seq = EXCLUDED.state_seq,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			payload = EXCLUDED.payload,
			created_at = EXCLUDED.created_at
	`

	return execSnapshot(
		ctx,
		r.db,
		query,
		snapshot.ID,
		snapshot.TournamentID,
		snapshot.StreamKey,
		snapshot.StreamSeq,
		snapshot.StateSeq,
		defaultSchemaVersion(snapshot.SchemaVersion),
		defaultString(snapshot.PolicyBundleVersion, "v1"),
		defaultString(snapshot.StateHash, snapshot.ID),
		defaultString(snapshot.PayloadHash, snapshot.ID),
		snapshot.ArtifactRef,
		normalizeJSON(snapshot.Payload),
		defaultTime(snapshot.CreatedAt),
	)
}

func (r *Repository) EnqueueOutboxEvents(ctx context.Context, events []model.OutboxEvent) error {
	const query = `
		INSERT INTO outbox_event (
			event_id,
			aggregate_type,
			aggregate_id,
			stream_key,
			lane,
			season_id,
			reward_window_id,
			event_type,
			event_version,
			occurred_at,
			causation_id,
			correlation_id,
			producer,
			visibility,
			payload,
			payload_uri,
			schema_version,
			policy_bundle_version,
			payload_hash,
			artifact_ref
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20
		)
		ON CONFLICT (event_id) DO UPDATE SET
			payload = EXCLUDED.payload,
			payload_uri = EXCLUDED.payload_uri,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			occurred_at = EXCLUDED.occurred_at
	`

	for _, event := range events {
		_, err := r.db.ExecContext(
			ctx,
			query,
			event.ID,
			event.AggregateType,
			event.AggregateID,
			event.StreamKey,
			defaultString(event.Lane, "arena"),
			event.SeasonID,
			event.RewardWindowID,
			event.EventType,
			defaultInt(event.EventVersion, 1),
			defaultTime(event.OccurredAt),
			event.CausationID,
			event.CorrelationID,
			defaultString(event.Producer, "arenad"),
			defaultString(event.Visibility, "internal"),
			normalizeJSON(event.Payload),
			event.PayloadURI,
			defaultSchemaVersion(event.SchemaVersion),
			defaultString(event.PolicyBundleVersion, "v1"),
			defaultString(event.PayloadHash, event.ID),
			event.ArtifactRef,
		)
		if err != nil {
			return fmt.Errorf("enqueue outbox_event %s: %w", event.ID, err)
		}
	}

	return nil
}

func (r *Repository) SaveProjectorCursor(ctx context.Context, cursor model.ProjectorCursor) error {
	const query = `
		INSERT INTO projector_cursor (
			projector_name,
			last_event_id,
			last_stream_key,
			last_stream_seq,
			updated_at
		) VALUES ($1, $2, $3, $4, $5)
		ON CONFLICT (projector_name) DO UPDATE SET
			last_event_id = EXCLUDED.last_event_id,
			last_stream_key = EXCLUDED.last_stream_key,
			last_stream_seq = EXCLUDED.last_stream_seq,
			updated_at = EXCLUDED.updated_at
	`

	_, err := r.db.ExecContext(
		ctx,
		query,
		cursor.ProjectorName,
		cursor.LastEventID,
		cursor.LastStreamKey,
		cursor.LastStreamSeq,
		defaultTime(cursor.UpdatedAt),
	)
	if err != nil {
		return fmt.Errorf("save projector_cursor %s: %w", cursor.ProjectorName, err)
	}

	return nil
}

func (r *Repository) SaveDeadLetterEvent(ctx context.Context, event model.DeadLetterEvent) error {
	const query = `
		INSERT INTO dead_letter_event (
			dead_letter_id,
			outbox_event_id,
			projector_name,
			error_message,
			payload,
			schema_version,
			policy_bundle_version,
			payload_hash,
			artifact_ref,
			occurred_at,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
		)
		ON CONFLICT (dead_letter_id) DO UPDATE SET
			error_message = EXCLUDED.error_message,
			payload = EXCLUDED.payload,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			occurred_at = EXCLUDED.occurred_at,
			created_at = EXCLUDED.created_at
	`

	_, err := r.db.ExecContext(
		ctx,
		query,
		event.ID,
		event.OutboxEventID,
		event.ProjectorName,
		event.ErrorMessage,
		normalizeJSON(event.Payload),
		defaultSchemaVersion(event.SchemaVersion),
		defaultString(event.PolicyBundleVersion, "v1"),
		defaultString(event.PayloadHash, event.ID),
		event.ArtifactRef,
		defaultTime(event.OccurredAt),
		defaultTime(event.CreatedAt),
	)
	if err != nil {
		return fmt.Errorf("save dead_letter_event %s: %w", event.ID, err)
	}

	return nil
}

func (r *Repository) AppendRatingInputs(ctx context.Context, inputs []model.RatingInput) error {
	const query = `
		INSERT INTO arena_rating_input (
			input_id,
			tournament_id,
			entrant_id,
			miner_address,
			rated_or_practice,
			human_only,
			finish_rank,
			finish_percentile,
			hands_played,
			meaningful_decisions,
			auto_actions,
			timeout_actions,
			invalid_actions,
			stage_reached,
			stack_path_summary,
			score_components,
			penalties,
			tournament_score,
			confidence_weight,
			field_strength_adjustment,
			bot_adjustment,
			time_cap_adjustment,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24, $25, $26, $27, $28, $29
		)
		ON CONFLICT (input_id) DO UPDATE SET
			finish_rank = EXCLUDED.finish_rank,
			finish_percentile = EXCLUDED.finish_percentile,
			hands_played = EXCLUDED.hands_played,
			meaningful_decisions = EXCLUDED.meaningful_decisions,
			auto_actions = EXCLUDED.auto_actions,
			timeout_actions = EXCLUDED.timeout_actions,
			invalid_actions = EXCLUDED.invalid_actions,
			stage_reached = EXCLUDED.stage_reached,
			stack_path_summary = EXCLUDED.stack_path_summary,
			score_components = EXCLUDED.score_components,
			penalties = EXCLUDED.penalties,
			tournament_score = EXCLUDED.tournament_score,
			confidence_weight = EXCLUDED.confidence_weight,
			field_strength_adjustment = EXCLUDED.field_strength_adjustment,
			bot_adjustment = EXCLUDED.bot_adjustment,
			time_cap_adjustment = EXCLUDED.time_cap_adjustment,
			payload = EXCLUDED.payload,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			created_at = EXCLUDED.created_at
	`

	for _, input := range inputs {
		_, err := r.db.ExecContext(
			ctx,
			query,
			input.ID,
			input.TournamentID,
			input.EntrantID,
			input.MinerAddress,
			string(input.Mode),
			input.HumanOnly,
			input.FinishRank,
			input.FinishPercentile,
			input.HandsPlayed,
			input.MeaningfulDecisions,
			input.AutoActions,
			input.TimeoutActions,
			input.InvalidActions,
			input.StageReached,
			normalizeJSON(input.StackPathSummary),
			normalizeJSON(input.ScoreComponents),
			normalizeJSON(input.Penalties),
			input.TournamentScore,
			input.ConfidenceWeight,
			input.FieldStrengthAdjustment,
			input.BotAdjustment,
			input.TimeCapAdjustment,
			normalizeJSON(input.Payload),
			defaultSchemaVersion(input.SchemaVersion),
			defaultString(input.PolicyBundleVersion, "v1"),
			defaultString(input.StateHash, input.ID),
			defaultString(input.PayloadHash, input.ID),
			input.ArtifactRef,
			defaultTime(input.CreatedAt),
		)
		if err != nil {
			return fmt.Errorf("append arena_rating_input %s: %w", input.ID, err)
		}
	}

	return nil
}

func (r *Repository) AppendCollusionMetrics(ctx context.Context, metrics []model.CollusionMetric) error {
	const query = `
		INSERT INTO arena_collusion_metric (
			metric_id,
			tournament_id,
			miner_address,
			metric_name,
			metric_value,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
		)
		ON CONFLICT (metric_id) DO UPDATE SET
			metric_value = EXCLUDED.metric_value,
			payload = EXCLUDED.payload,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			created_at = EXCLUDED.created_at
	`

	for _, metric := range metrics {
		_, err := r.db.ExecContext(
			ctx,
			query,
			metric.ID,
			metric.TournamentID,
			metric.MinerAddress,
			metric.MetricName,
			metric.MetricValue,
			normalizeJSON(metric.Payload),
			defaultSchemaVersion(metric.SchemaVersion),
			defaultString(metric.PolicyBundleVersion, "v1"),
			defaultString(metric.StateHash, metric.ID),
			defaultString(metric.PayloadHash, metric.ID),
			metric.ArtifactRef,
			defaultTime(metric.CreatedAt),
		)
		if err != nil {
			return fmt.Errorf("append arena_collusion_metric %s: %w", metric.ID, err)
		}
	}

	return nil
}

func (r *Repository) AssertSharedHarnessTables(ctx context.Context) error {
	for _, table := range []string{"miners", "arena_result_entries"} {
		var regclass sql.NullString
		err := r.db.QueryRowContext(ctx, `
			SELECT to_regclass($1)
		`, table).Scan(&regclass)
		if err != nil {
			return fmt.Errorf("check %s table: %w", table, err)
		}
		if !regclass.Valid {
			return fmt.Errorf("%s table missing", table)
		}
	}

	return nil
}

func (r *Repository) ListWaves(ctx context.Context) ([]model.Wave, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			wave_id,
			rated_or_practice,
			wave_state,
			registration_open_at,
			registration_close_at,
			scheduled_start_at,
			target_shard_size,
			soft_min_entrants,
			soft_max_entrants,
			hard_max_entrants,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at,
			updated_at
		FROM arena_wave
		ORDER BY created_at
	`)
	if err != nil {
		return nil, fmt.Errorf("list arena_wave: %w", err)
	}
	defer rows.Close()

	waves := make([]model.Wave, 0)
	for rows.Next() {
		var wave model.Wave
		var mode string
		var state string
		if err := rows.Scan(
			&wave.ID,
			&mode,
			&state,
			&wave.RegistrationOpenAt,
			&wave.RegistrationCloseAt,
			&wave.ScheduledStartAt,
			&wave.TargetShardSize,
			&wave.SoftMinEntrants,
			&wave.SoftMaxEntrants,
			&wave.HardMaxEntrants,
			&wave.Payload,
			&wave.SchemaVersion,
			&wave.PolicyBundleVersion,
			&wave.StateHash,
			&wave.PayloadHash,
			&wave.ArtifactRef,
			&wave.CreatedAt,
			&wave.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan arena_wave: %w", err)
		}
		wave.Mode = model.ArenaMode(mode)
		wave.State = model.WaveState(state)
		waves = append(waves, wave)
	}

	return waves, rows.Err()
}

func (r *Repository) ListTournamentsByWave(ctx context.Context, waveID string) ([]model.Tournament, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			tournament_id,
			wave_id,
			rated_or_practice,
			tournament_state,
			exhibition,
			no_multiplier,
			cancelled,
			voided,
			human_only,
			integrity_hold,
			seating_republish_count,
			current_round_no,
			current_level_no,
			players_registered,
			players_confirmed,
			players_remaining,
			active_table_count,
			final_table_table_id,
			rng_root_seed,
			time_cap_at,
			completed_at,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at,
			updated_at
		FROM arena_tournament
		WHERE wave_id = $1
		ORDER BY created_at
	`, waveID)
	if err != nil {
		return nil, fmt.Errorf("list arena_tournament by wave %s: %w", waveID, err)
	}
	defer rows.Close()

	tournaments := make([]model.Tournament, 0)
	for rows.Next() {
		var tournament model.Tournament
		var mode string
		var state string
		var timeCapAt sql.NullTime
		var completedAt sql.NullTime
		if err := rows.Scan(
			&tournament.ID,
			&tournament.WaveID,
			&mode,
			&state,
			&tournament.Exhibition,
			&tournament.NoMultiplier,
			&tournament.Cancelled,
			&tournament.Voided,
			&tournament.HumanOnly,
			&tournament.IntegrityHold,
			&tournament.SeatingRepublishCount,
			&tournament.CurrentRoundNo,
			&tournament.CurrentLevelNo,
			&tournament.PlayersRegistered,
			&tournament.PlayersConfirmed,
			&tournament.PlayersRemaining,
			&tournament.ActiveTableCount,
			&tournament.FinalTableTableID,
			&tournament.RNGRootSeed,
			&timeCapAt,
			&completedAt,
			&tournament.Payload,
			&tournament.SchemaVersion,
			&tournament.PolicyBundleVersion,
			&tournament.StateHash,
			&tournament.PayloadHash,
			&tournament.ArtifactRef,
			&tournament.CreatedAt,
			&tournament.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan arena_tournament: %w", err)
		}
		tournament.Mode = model.ArenaMode(mode)
		tournament.State = model.TournamentState(state)
		if timeCapAt.Valid {
			value := timeCapAt.Time.UTC()
			tournament.TimeCapAt = &value
		}
		if completedAt.Valid {
			value := completedAt.Time.UTC()
			tournament.CompletedAt = &value
		}
		tournaments = append(tournaments, tournament)
	}

	return tournaments, rows.Err()
}

func (r *Repository) ListEntrantsByWave(ctx context.Context, waveID string) ([]model.Entrant, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			entrant_id,
			wave_id,
			tournament_id,
			miner_id,
			economic_unit_id,
			seat_alias,
			registration_state,
			table_id,
			seat_id,
			finish_rank,
			stage_reached,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at,
			updated_at
		FROM arena_entrant
		WHERE wave_id = $1
		ORDER BY created_at
	`, waveID)
	if err != nil {
		return nil, fmt.Errorf("list arena_entrant by wave %s: %w", waveID, err)
	}
	defer rows.Close()

	entrants := make([]model.Entrant, 0)
	for rows.Next() {
		var entrant model.Entrant
		var registrationState string
		var tournamentID sql.NullString
		var tableID sql.NullString
		var seatID sql.NullString
		if err := rows.Scan(
			&entrant.ID,
			&entrant.WaveID,
			&tournamentID,
			&entrant.MinerID,
			&entrant.EconomicUnitID,
			&entrant.SeatAlias,
			&registrationState,
			&tableID,
			&seatID,
			&entrant.FinishRank,
			&entrant.StageReached,
			&entrant.Payload,
			&entrant.SchemaVersion,
			&entrant.PolicyBundleVersion,
			&entrant.StateHash,
			&entrant.PayloadHash,
			&entrant.ArtifactRef,
			&entrant.CreatedAt,
			&entrant.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan arena_entrant: %w", err)
		}
		entrant.TournamentID = tournamentID.String
		entrant.TableID = tableID.String
		entrant.SeatID = seatID.String
		entrant.RegistrationState = model.RegistrationState(registrationState)
		entrants = append(entrants, entrant)
	}

	return entrants, rows.Err()
}

func (r *Repository) ListSeatsByTournament(ctx context.Context, tournamentID string) ([]model.Seat, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			seat_id,
			table_id,
			tournament_id,
			entrant_id,
			seat_no,
			seat_alias,
			miner_id,
			seat_state,
			stack,
			timeout_streak,
			sit_out_warning_count,
			last_forced_blind_round,
			last_manual_action_at,
			tournament_seat_draw_token,
			admin_status_overlay,
			removed_reason,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at,
			updated_at
		FROM arena_seat
		WHERE tournament_id = $1
	`, tournamentID)
	if err != nil {
		return nil, fmt.Errorf("list arena_seat for tournament %s: %w", tournamentID, err)
	}
	defer rows.Close()

	seats := make([]model.Seat, 0)
	for rows.Next() {
		var (
			seat             model.Seat
			entrantID        sql.NullString
			lastManualAction sql.NullTime
			seatState        string
		)
		if err := rows.Scan(
			&seat.ID,
			&seat.TableID,
			&seat.TournamentID,
			&entrantID,
			&seat.SeatNo,
			&seat.SeatAlias,
			&seat.MinerID,
			&seatState,
			&seat.Stack,
			&seat.TimeoutStreak,
			&seat.SitOutWarningCount,
			&seat.LastForcedBlindRound,
			&lastManualAction,
			&seat.TournamentSeatDrawToken,
			&seat.AdminStatusOverlay,
			&seat.RemovedReason,
			&seat.Payload,
			&seat.SchemaVersion,
			&seat.PolicyBundleVersion,
			&seat.StateHash,
			&seat.PayloadHash,
			&seat.ArtifactRef,
			&seat.CreatedAt,
			&seat.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan arena_seat for tournament %s: %w", tournamentID, err)
		}
		seat.State = model.SeatState(seatState)
		if entrantID.Valid {
			seat.EntrantID = entrantID.String
		}
		if lastManualAction.Valid {
			ts := lastManualAction.Time
			seat.LastManualActionAt = &ts
		}
		seats = append(seats, seat)
	}

	return seats, rows.Err()
}

func (r *Repository) ListEliminationEventsByTournament(ctx context.Context, tournamentID string) ([]model.EliminationEvent, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			elimination_event_id,
			tournament_id,
			table_id,
			hand_id,
			seat_id,
			entrant_id,
			finish_rank,
			stage_reached,
			occurred_at,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at
		FROM arena_elimination_event
		WHERE tournament_id = $1
	`, tournamentID)
	if err != nil {
		return nil, fmt.Errorf("list arena_elimination_event for tournament %s: %w", tournamentID, err)
	}
	defer rows.Close()

	events := make([]model.EliminationEvent, 0)
	for rows.Next() {
		var (
			event     model.EliminationEvent
			tableID   sql.NullString
			handID    sql.NullString
			seatID    sql.NullString
			entrantID sql.NullString
		)
		if err := rows.Scan(
			&event.ID,
			&event.TournamentID,
			&tableID,
			&handID,
			&seatID,
			&entrantID,
			&event.FinishRank,
			&event.StageReached,
			&event.OccurredAt,
			&event.Payload,
			&event.SchemaVersion,
			&event.PolicyBundleVersion,
			&event.StateHash,
			&event.PayloadHash,
			&event.ArtifactRef,
			&event.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan arena_elimination_event for tournament %s: %w", tournamentID, err)
		}
		if tableID.Valid {
			event.TableID = tableID.String
		}
		if handID.Valid {
			event.HandID = handID.String
		}
		if seatID.Valid {
			event.SeatID = seatID.String
		}
		if entrantID.Valid {
			event.EntrantID = entrantID.String
		}
		events = append(events, event)
	}

	return events, rows.Err()
}

func (r *Repository) ListOperatorInterventionsByTournament(ctx context.Context, tournamentID string) ([]model.OperatorIntervention, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			intervention_id,
			tournament_id,
			table_id,
			seat_id,
			miner_id,
			intervention_type,
			status,
			requested_by,
			requested_at,
			effective_at_safe_point,
			reason_code,
			reason_detail,
			created_event_id,
			resolved_event_id,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at,
			updated_at
		FROM arena_operator_intervention
		WHERE tournament_id = $1
	`, tournamentID)
	if err != nil {
		return nil, fmt.Errorf("list arena_operator_intervention for tournament %s: %w", tournamentID, err)
	}
	defer rows.Close()

	interventions := make([]model.OperatorIntervention, 0)
	for rows.Next() {
		var (
			intervention model.OperatorIntervention
			tableID      sql.NullString
			seatID       sql.NullString
		)
		if err := rows.Scan(
			&intervention.ID,
			&intervention.TournamentID,
			&tableID,
			&seatID,
			&intervention.MinerID,
			&intervention.InterventionType,
			&intervention.Status,
			&intervention.RequestedBy,
			&intervention.RequestedAt,
			&intervention.EffectiveAtSafePoint,
			&intervention.ReasonCode,
			&intervention.ReasonDetail,
			&intervention.CreatedEventID,
			&intervention.ResolvedEventID,
			&intervention.Payload,
			&intervention.SchemaVersion,
			&intervention.PolicyBundleVersion,
			&intervention.StateHash,
			&intervention.PayloadHash,
			&intervention.ArtifactRef,
			&intervention.CreatedAt,
			&intervention.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan arena_operator_intervention for tournament %s: %w", tournamentID, err)
		}
		if tableID.Valid {
			intervention.TableID = tableID.String
		}
		if seatID.Valid {
			intervention.SeatID = seatID.String
		}
		interventions = append(interventions, intervention)
	}

	return interventions, rows.Err()
}

func (r *Repository) ListActionDeadlinesByTournament(ctx context.Context, tournamentID string) ([]model.ActionDeadline, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			deadline_id,
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			seat_id,
			deadline_at,
			status,
			opened_by_event_id,
			resolved_by_event_id,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at,
			updated_at
		FROM arena_action_deadline
		WHERE tournament_id = $1
		ORDER BY deadline_at, created_at
	`, tournamentID)
	if err != nil {
		return nil, fmt.Errorf("list arena_action_deadline by tournament %s: %w", tournamentID, err)
	}
	defer rows.Close()

	deadlines := make([]model.ActionDeadline, 0)
	for rows.Next() {
		var deadline model.ActionDeadline
		if err := rows.Scan(
			&deadline.DeadlineID,
			&deadline.TournamentID,
			&deadline.TableID,
			&deadline.HandID,
			&deadline.PhaseID,
			&deadline.SeatID,
			&deadline.DeadlineAt,
			&deadline.Status,
			&deadline.OpenedByEventID,
			&deadline.ResolvedByEventID,
			&deadline.Payload,
			&deadline.SchemaVersion,
			&deadline.PolicyBundleVersion,
			&deadline.StateHash,
			&deadline.PayloadHash,
			&deadline.ArtifactRef,
			&deadline.CreatedAt,
			&deadline.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan arena_action_deadline: %w", err)
		}
		deadlines = append(deadlines, deadline)
	}

	return deadlines, rows.Err()
}

func (r *Repository) LoadRoundBarrier(ctx context.Context, tournamentID string, roundNo int) (model.RoundBarrier, error) {
	var barrier model.RoundBarrier
	err := r.db.QueryRowContext(ctx, `
		SELECT
			barrier_id,
			tournament_id,
			round_no,
			expected_table_count,
			received_hand_close_count,
			barrier_state,
			pending_reseat_plan_ref,
			pending_level_no,
			terminate_after_current_round,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at,
			updated_at
		FROM arena_round_barrier
		WHERE tournament_id = $1 AND round_no = $2
	`, tournamentID, roundNo).Scan(
		&barrier.ID,
		&barrier.TournamentID,
		&barrier.RoundNo,
		&barrier.ExpectedTableCount,
		&barrier.ReceivedHandCloseCount,
		&barrier.BarrierState,
		&barrier.PendingReseatPlanRef,
		&barrier.PendingLevelNo,
		&barrier.TerminateAfterCurrentRound,
		&barrier.Payload,
		&barrier.SchemaVersion,
		&barrier.PolicyBundleVersion,
		&barrier.StateHash,
		&barrier.PayloadHash,
		&barrier.ArtifactRef,
		&barrier.CreatedAt,
		&barrier.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return model.RoundBarrier{}, sql.ErrNoRows
		}
		return model.RoundBarrier{}, fmt.Errorf("load arena_round_barrier %s round %d: %w", tournamentID, roundNo, err)
	}
	return barrier, nil
}

func (r *Repository) LoadSubmissionLedgerEntry(ctx context.Context, requestID string) (model.SubmissionLedger, error) {
	var entry model.SubmissionLedger
	err := r.db.QueryRowContext(ctx, `
		SELECT
			request_id,
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			seat_id,
			seat_alias,
			miner_id,
			expected_state_seq,
			validation_status,
			payload_artifact_ref,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at,
			updated_at
		FROM submission_ledger
		WHERE request_id = $1
	`, requestID).Scan(
		&entry.RequestID,
		&entry.TournamentID,
		&entry.TableID,
		&entry.HandID,
		&entry.PhaseID,
		&entry.SeatID,
		&entry.SeatAlias,
		&entry.MinerID,
		&entry.ExpectedStateSeq,
		&entry.ValidationStatus,
		&entry.PayloadArtifactRef,
		&entry.Payload,
		&entry.SchemaVersion,
		&entry.PolicyBundleVersion,
		&entry.StateHash,
		&entry.PayloadHash,
		&entry.ArtifactRef,
		&entry.CreatedAt,
		&entry.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return model.SubmissionLedger{}, sql.ErrNoRows
		}
		return model.SubmissionLedger{}, fmt.Errorf("load submission_ledger %s: %w", requestID, err)
	}
	return entry, nil
}

func (r *Repository) LoadActionRecord(ctx context.Context, requestID string) (model.ActionRecord, error) {
	var (
		action      model.ActionRecord
		processedAt sql.NullTime
	)
	err := r.db.QueryRowContext(ctx, `
		SELECT
			request_id,
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			seat_id,
			seat_alias,
			action_type,
			action_amount_bucket,
			action_seq,
			expected_state_seq,
			accepted_state_seq,
			validation_status,
			result_event_id,
			received_at,
			processed_at,
			error_code,
			duplicate_of_request_id,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref
		FROM arena_action
		WHERE request_id = $1
	`, requestID).Scan(
		&action.RequestID,
		&action.TournamentID,
		&action.TableID,
		&action.HandID,
		&action.PhaseID,
		&action.SeatID,
		&action.SeatAlias,
		&action.ActionType,
		&action.ActionAmountBucket,
		&action.ActionSeq,
		&action.ExpectedStateSeq,
		&action.AcceptedStateSeq,
		&action.ValidationStatus,
		&action.ResultEventID,
		&action.ReceivedAt,
		&processedAt,
		&action.ErrorCode,
		&action.DuplicateOfRequestID,
		&action.Payload,
		&action.SchemaVersion,
		&action.PolicyBundleVersion,
		&action.StateHash,
		&action.PayloadHash,
		&action.ArtifactRef,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return model.ActionRecord{}, sql.ErrNoRows
		}
		return model.ActionRecord{}, fmt.Errorf("load arena_action %s: %w", requestID, err)
	}
	if processedAt.Valid {
		ts := processedAt.Time
		action.ProcessedAt = &ts
	}
	return action, nil
}

func (r *Repository) ListExpiredActionDeadlines(ctx context.Context, asOf time.Time) ([]model.ActionDeadline, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			deadline_id,
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			seat_id,
			deadline_at,
			status,
			opened_by_event_id,
			resolved_by_event_id,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at,
			updated_at
		FROM arena_action_deadline
		WHERE status = 'open'
		  AND deadline_at <= $1
		ORDER BY deadline_at, created_at
	`, asOf.UTC())
	if err != nil {
		return nil, fmt.Errorf("list expired arena_action_deadline: %w", err)
	}
	defer rows.Close()

	deadlines := make([]model.ActionDeadline, 0)
	for rows.Next() {
		var deadline model.ActionDeadline
		if err := rows.Scan(
			&deadline.DeadlineID,
			&deadline.TournamentID,
			&deadline.TableID,
			&deadline.HandID,
			&deadline.PhaseID,
			&deadline.SeatID,
			&deadline.DeadlineAt,
			&deadline.Status,
			&deadline.OpenedByEventID,
			&deadline.ResolvedByEventID,
			&deadline.Payload,
			&deadline.SchemaVersion,
			&deadline.PolicyBundleVersion,
			&deadline.StateHash,
			&deadline.PayloadHash,
			&deadline.ArtifactRef,
			&deadline.CreatedAt,
			&deadline.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan expired arena_action_deadline: %w", err)
		}
		deadlines = append(deadlines, deadline)
	}

	return deadlines, rows.Err()
}

func (r *Repository) LoadLatestTableSnapshots(ctx context.Context, tournamentID string) ([]model.TableSnapshot, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT DISTINCT ON (table_id)
			snapshot_id,
			tournament_id,
			table_id,
			stream_key,
			stream_seq,
			state_seq,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at
		FROM arena_table_snapshot
		WHERE tournament_id = $1
		ORDER BY table_id, stream_seq DESC
	`, tournamentID)
	if err != nil {
		return nil, fmt.Errorf("load latest arena_table_snapshot for %s: %w", tournamentID, err)
	}
	defer rows.Close()

	snapshots := make([]model.TableSnapshot, 0)
	for rows.Next() {
		var snapshot model.TableSnapshot
		if err := rows.Scan(
			&snapshot.ID,
			&snapshot.TournamentID,
			&snapshot.TableID,
			&snapshot.StreamKey,
			&snapshot.StreamSeq,
			&snapshot.StateSeq,
			&snapshot.RNGRootSeed,
			&snapshot.SeedDerivation.TableID,
			&snapshot.SeedDerivation.HandNumber,
			&snapshot.SeedDerivation.SeatNumber,
			&snapshot.SeedDerivation.StreamName,
			&snapshot.Payload,
			&snapshot.SchemaVersion,
			&snapshot.PolicyBundleVersion,
			&snapshot.StateHash,
			&snapshot.PayloadHash,
			&snapshot.ArtifactRef,
			&snapshot.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan arena_table_snapshot: %w", err)
		}
		snapshots = append(snapshots, snapshot)
	}

	return snapshots, rows.Err()
}

func (r *Repository) LoadLatestTournamentSnapshot(ctx context.Context, tournamentID string) (model.TournamentSnapshot, error) {
	row := r.db.QueryRowContext(ctx, `
		SELECT
			snapshot_id,
			tournament_id,
			stream_key,
			stream_seq,
			state_seq,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at
		FROM arena_tournament_snapshot
		WHERE tournament_id = $1
		ORDER BY stream_seq DESC
		LIMIT 1
	`, tournamentID)

	var snapshot model.TournamentSnapshot
	if err := row.Scan(
		&snapshot.ID,
		&snapshot.TournamentID,
		&snapshot.StreamKey,
		&snapshot.StreamSeq,
		&snapshot.StateSeq,
		&snapshot.RNGRootSeed,
		&snapshot.SeedDerivation.TableID,
		&snapshot.SeedDerivation.HandNumber,
		&snapshot.SeedDerivation.SeatNumber,
		&snapshot.SeedDerivation.StreamName,
		&snapshot.Payload,
		&snapshot.SchemaVersion,
		&snapshot.PolicyBundleVersion,
		&snapshot.StateHash,
		&snapshot.PayloadHash,
		&snapshot.ArtifactRef,
		&snapshot.CreatedAt,
	); err != nil {
		return model.TournamentSnapshot{}, fmt.Errorf("load latest arena_tournament_snapshot for %s: %w", tournamentID, err)
	}

	return snapshot, nil
}

func (r *Repository) ListRatingInputs(ctx context.Context, tournamentID string) ([]model.RatingInput, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			input_id,
			tournament_id,
			entrant_id,
			miner_address,
			rated_or_practice,
			human_only,
			finish_rank,
			finish_percentile,
			hands_played,
			meaningful_decisions,
			auto_actions,
			timeout_actions,
			invalid_actions,
			stage_reached,
			stack_path_summary,
			score_components,
			penalties,
			tournament_score,
			confidence_weight,
			field_strength_adjustment,
			bot_adjustment,
			time_cap_adjustment,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at
		FROM arena_rating_input
		WHERE tournament_id = $1
		ORDER BY miner_address, created_at
	`, tournamentID)
	if err != nil {
		return nil, fmt.Errorf("list arena_rating_input for %s: %w", tournamentID, err)
	}
	defer rows.Close()

	inputs := make([]model.RatingInput, 0)
	for rows.Next() {
		var input model.RatingInput
		var mode string
		if err := rows.Scan(
			&input.ID,
			&input.TournamentID,
			&input.EntrantID,
			&input.MinerAddress,
			&mode,
			&input.HumanOnly,
			&input.FinishRank,
			&input.FinishPercentile,
			&input.HandsPlayed,
			&input.MeaningfulDecisions,
			&input.AutoActions,
			&input.TimeoutActions,
			&input.InvalidActions,
			&input.StageReached,
			&input.StackPathSummary,
			&input.ScoreComponents,
			&input.Penalties,
			&input.TournamentScore,
			&input.ConfidenceWeight,
			&input.FieldStrengthAdjustment,
			&input.BotAdjustment,
			&input.TimeCapAdjustment,
			&input.Payload,
			&input.SchemaVersion,
			&input.PolicyBundleVersion,
			&input.StateHash,
			&input.PayloadHash,
			&input.ArtifactRef,
			&input.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan arena_rating_input: %w", err)
		}
		input.Mode = model.ArenaMode(mode)
		inputs = append(inputs, input)
	}

	return inputs, rows.Err()
}

func (r *Repository) LoadPersistedMinerStates(ctx context.Context) ([]model.RatingRuntimeState, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			rs.miner_address,
			rs.mu,
			rs.sigma,
			rs.arena_reliability,
			rs.public_elo,
			m.public_rank,
			m.arena_multiplier,
			COALESCE(mult.eligible_tournament_count, 0)
		FROM rating_state_current rs
		LEFT JOIN miners m
			ON m.address = rs.miner_address
		LEFT JOIN (
			SELECT
				miner_address,
				SUM(CASE WHEN eligible_for_multiplier THEN 1 ELSE 0 END) AS eligible_tournament_count
			FROM arena_multiplier_snapshot
			GROUP BY miner_address
		) mult
			ON mult.miner_address = rs.miner_address
		ORDER BY rs.miner_address
	`)
	if err != nil {
		return nil, fmt.Errorf("load persisted miner states: %w", err)
	}
	defer rows.Close()

	states := make([]model.RatingRuntimeState, 0)
	for rows.Next() {
		var (
			state      model.RatingRuntimeState
			publicRank sql.NullInt64
			multiplier sql.NullFloat64
		)
		if err := rows.Scan(
			&state.MinerAddress,
			&state.Mu,
			&state.Sigma,
			&state.ArenaReliability,
			&state.PublicELO,
			&publicRank,
			&multiplier,
			&state.EligibleTournamentCount,
		); err != nil {
			return nil, fmt.Errorf("scan persisted miner state: %w", err)
		}
		if publicRank.Valid {
			state.PublicRank = int(publicRank.Int64)
		}
		if multiplier.Valid {
			state.Multiplier = multiplier.Float64
		}
		states = append(states, state)
	}

	return states, rows.Err()
}

func (r *Repository) UpsertRatingState(ctx context.Context, state model.RatingState) error {
	const query = `
		INSERT INTO rating_state_current (
			miner_address,
			mu,
			sigma,
			arena_reliability,
			public_elo,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
		)
		ON CONFLICT (miner_address) DO UPDATE SET
			mu = EXCLUDED.mu,
			sigma = EXCLUDED.sigma,
			arena_reliability = EXCLUDED.arena_reliability,
			public_elo = EXCLUDED.public_elo,
			payload = EXCLUDED.payload,
			schema_version = EXCLUDED.schema_version,
			policy_bundle_version = EXCLUDED.policy_bundle_version,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			updated_at = EXCLUDED.updated_at
	`

	_, err := r.db.ExecContext(
		ctx,
		query,
		state.MinerAddress,
		state.Mu,
		state.Sigma,
		state.ArenaReliability,
		state.PublicELO,
		normalizeJSON(state.Payload),
		defaultSchemaVersion(state.SchemaVersion),
		defaultString(state.PolicyBundleVersion, "v1"),
		defaultString(state.StateHash, state.MinerAddress),
		defaultString(state.PayloadHash, state.MinerAddress),
		state.ArtifactRef,
		defaultTime(state.UpdatedAt),
	)
	if err != nil {
		return fmt.Errorf("upsert rating_state_current %s: %w", state.MinerAddress, err)
	}

	return nil
}

func (r *Repository) SaveRatingSnapshot(ctx context.Context, snapshot model.RatingSnapshot) error {
	const query = `
		INSERT INTO rating_snapshot (
			snapshot_id,
			miner_address,
			mu,
			sigma,
			arena_reliability,
			public_elo,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
		)
		ON CONFLICT (snapshot_id) DO UPDATE SET
			payload = EXCLUDED.payload,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			created_at = EXCLUDED.created_at
	`

	_, err := r.db.ExecContext(
		ctx,
		query,
		snapshot.ID,
		snapshot.MinerAddress,
		snapshot.Mu,
		snapshot.Sigma,
		snapshot.ArenaReliability,
		snapshot.PublicELO,
		normalizeJSON(snapshot.Payload),
		defaultSchemaVersion(snapshot.SchemaVersion),
		defaultString(snapshot.PolicyBundleVersion, "v1"),
		defaultString(snapshot.StateHash, snapshot.ID),
		defaultString(snapshot.PayloadHash, snapshot.ID),
		snapshot.ArtifactRef,
		defaultTime(snapshot.CreatedAt),
	)
	if err != nil {
		return fmt.Errorf("save rating_snapshot %s: %w", snapshot.ID, err)
	}

	return nil
}

func (r *Repository) SavePublicLadderSnapshot(ctx context.Context, snapshot model.PublicLadderSnapshot) error {
	const query = `
		INSERT INTO public_ladder_snapshot (
			snapshot_id,
			season_id,
			miner_address,
			public_rank,
			public_elo,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
		)
		ON CONFLICT (snapshot_id) DO UPDATE SET
			payload = EXCLUDED.payload,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			created_at = EXCLUDED.created_at
	`

	_, err := r.db.ExecContext(
		ctx,
		query,
		snapshot.ID,
		snapshot.SeasonID,
		snapshot.MinerAddress,
		snapshot.PublicRank,
		snapshot.PublicELO,
		normalizeJSON(snapshot.Payload),
		defaultSchemaVersion(snapshot.SchemaVersion),
		defaultString(snapshot.PolicyBundleVersion, "v1"),
		defaultString(snapshot.StateHash, snapshot.ID),
		defaultString(snapshot.PayloadHash, snapshot.ID),
		snapshot.ArtifactRef,
		defaultTime(snapshot.CreatedAt),
	)
	if err != nil {
		return fmt.Errorf("save public_ladder_snapshot %s: %w", snapshot.ID, err)
	}

	return nil
}

func (r *Repository) SaveMultiplierSnapshot(ctx context.Context, snapshot model.MultiplierSnapshot) error {
	const query = `
		INSERT INTO arena_multiplier_snapshot (
			snapshot_id,
			tournament_id,
			miner_address,
			eligible_for_multiplier,
			tournament_score,
			confidence_weight,
			multiplier_before,
			multiplier_after,
			payload,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref,
			created_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15
		)
		ON CONFLICT (snapshot_id) DO UPDATE SET
			payload = EXCLUDED.payload,
			state_hash = EXCLUDED.state_hash,
			payload_hash = EXCLUDED.payload_hash,
			artifact_ref = EXCLUDED.artifact_ref,
			created_at = EXCLUDED.created_at
	`

	_, err := r.db.ExecContext(
		ctx,
		query,
		snapshot.ID,
		snapshot.TournamentID,
		snapshot.MinerAddress,
		snapshot.EligibleForMultiplier,
		snapshot.TournamentScore,
		snapshot.ConfidenceWeight,
		snapshot.MultiplierBefore,
		snapshot.MultiplierAfter,
		normalizeJSON(snapshot.Payload),
		defaultSchemaVersion(snapshot.SchemaVersion),
		defaultString(snapshot.PolicyBundleVersion, "v1"),
		defaultString(snapshot.StateHash, snapshot.ID),
		defaultString(snapshot.PayloadHash, snapshot.ID),
		snapshot.ArtifactRef,
		defaultTime(snapshot.CreatedAt),
	)
	if err != nil {
		return fmt.Errorf("save arena_multiplier_snapshot %s: %w", snapshot.ID, err)
	}

	return nil
}

func (r *Repository) UpsertMinerCompatibility(ctx context.Context, miner model.MinerCompatibility) error {
	const query = `
		UPDATE miners
		SET (
			arena_multiplier,
			updated_at
		) = (
			$2, $3
		)
		WHERE address = $1
	`

	now := nowUTC()
	if miner.UpdatedAt.IsZero() {
		miner.UpdatedAt = now
	}

	result, err := r.db.ExecContext(
		ctx,
		query,
		miner.Address,
		defaultFloat(miner.ArenaMultiplier, 1),
		miner.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("update miner compatibility %s: %w", miner.Address, err)
	}
	if result == nil {
		return nil
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("rows affected for miner compatibility %s: %w", miner.Address, err)
	}
	if rowsAffected == 0 {
		return fmt.Errorf("update miner compatibility %s: miner not found", miner.Address)
	}

	return nil
}

func (r *Repository) UpsertArenaResultEntry(ctx context.Context, entry model.ArenaResultEntry) error {
	const query = `
		INSERT INTO arena_result_entries (
			id,
			tournament_id,
			miner_address,
			rated_or_practice,
			human_only,
			eligible_for_multiplier,
			arena_score,
			conservative_skill,
			multiplier_after,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
		)
		ON CONFLICT (id) DO UPDATE SET
			tournament_id = EXCLUDED.tournament_id,
			miner_address = EXCLUDED.miner_address,
			rated_or_practice = EXCLUDED.rated_or_practice,
			human_only = EXCLUDED.human_only,
			eligible_for_multiplier = EXCLUDED.eligible_for_multiplier,
			arena_score = EXCLUDED.arena_score,
			conservative_skill = EXCLUDED.conservative_skill,
			multiplier_after = EXCLUDED.multiplier_after,
			updated_at = EXCLUDED.updated_at
	`

	now := nowUTC()
	if entry.CreatedAt.IsZero() {
		entry.CreatedAt = now
	}
	if entry.UpdatedAt.IsZero() {
		entry.UpdatedAt = now
	}

	_, err := r.db.ExecContext(
		ctx,
		query,
		entry.ID,
		entry.TournamentID,
		entry.MinerAddress,
		string(entry.Mode),
		entry.HumanOnly,
		entry.EligibleForMultiplier,
		entry.ArenaScore,
		nullFloat(entry.ConservativeSkill),
		defaultFloat(entry.MultiplierAfter, 1),
		entry.CreatedAt,
		entry.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert arena_result_entries %s: %w", entry.ID, err)
	}

	return nil
}

func execSnapshot(ctx context.Context, db *sql.DB, query string, args ...any) error {
	if _, err := db.ExecContext(ctx, query, args...); err != nil {
		return err
	}
	return nil
}

type arenaEventLogIdentity struct {
	AggregateType       string
	AggregateID         string
	StreamKey           string
	StreamSeq           int64
	TournamentID        string
	TableID             string
	HandID              string
	PhaseID             string
	RoundNo             int
	BarrierID           string
	EventType           string
	EventVersion        int
	SchemaVersion       int
	PolicyBundleVersion string
	RNGRootSeed         string
	SeedTableID         string
	SeedHandNo          int
	SeedSeatNo          int
	SeedStreamName      string
	StateSeq            int64
	CausationID         string
	CorrelationID       string
	PayloadURI          string
	PayloadHash         string
	ArtifactRef         string
	StateHashAfter      string
}

type arenaActionLogicalIdentity struct {
	TournamentID         string
	TableID              string
	HandID               string
	PhaseID              string
	SeatID               string
	SeatAlias            string
	ActionType           string
	ActionAmountBucket   int64
	ActionSeq            int
	ExpectedStateSeq     int64
	AcceptedStateSeq     int64
	ValidationStatus     string
	ResultEventID        string
	ErrorCode            string
	DuplicateOfRequestID string
	SchemaVersion        int
	PolicyBundleVersion  string
	StateHash            string
	PayloadHash          string
	ArtifactRef          string
}

func buildArenaEventLogIdentity(event model.EventLogEntry) arenaEventLogIdentity {
	return arenaEventLogIdentity{
		AggregateType:       event.AggregateType,
		AggregateID:         event.AggregateID,
		StreamKey:           event.StreamKey,
		StreamSeq:           event.StreamSeq,
		TournamentID:        event.TournamentID,
		TableID:             event.TableID,
		HandID:              event.HandID,
		PhaseID:             event.PhaseID,
		RoundNo:             event.RoundNo,
		BarrierID:           event.BarrierID,
		EventType:           event.EventType,
		EventVersion:        defaultInt(event.EventVersion, 1),
		SchemaVersion:       defaultSchemaVersion(event.SchemaVersion),
		PolicyBundleVersion: defaultString(event.PolicyBundleVersion, "v1"),
		RNGRootSeed:         event.RNGRootSeed,
		SeedTableID:         event.SeedDerivation.TableID,
		SeedHandNo:          event.SeedDerivation.HandNumber,
		SeedSeatNo:          event.SeedDerivation.SeatNumber,
		SeedStreamName:      event.SeedDerivation.StreamName,
		StateSeq:            event.StateSeq,
		CausationID:         event.CausationID,
		CorrelationID:       event.CorrelationID,
		PayloadURI:          event.PayloadURI,
		PayloadHash:         defaultString(event.PayloadHash, event.EventID),
		ArtifactRef:         event.ArtifactRef,
		StateHashAfter:      defaultString(event.StateHashAfter, event.EventID),
	}
}

func buildArenaActionLogicalIdentity(action model.ActionRecord) arenaActionLogicalIdentity {
	return arenaActionLogicalIdentity{
		TournamentID:         action.TournamentID,
		TableID:              action.TableID,
		HandID:               action.HandID,
		PhaseID:              action.PhaseID,
		SeatID:               action.SeatID,
		SeatAlias:            action.SeatAlias,
		ActionType:           action.ActionType,
		ActionAmountBucket:   action.ActionAmountBucket,
		ActionSeq:            action.ActionSeq,
		ExpectedStateSeq:     action.ExpectedStateSeq,
		AcceptedStateSeq:     action.AcceptedStateSeq,
		ValidationStatus:     action.ValidationStatus,
		ResultEventID:        action.ResultEventID,
		ErrorCode:            action.ErrorCode,
		DuplicateOfRequestID: action.DuplicateOfRequestID,
		SchemaVersion:        defaultSchemaVersion(action.SchemaVersion),
		PolicyBundleVersion:  defaultString(action.PolicyBundleVersion, "v1"),
		StateHash:            defaultString(action.StateHash, action.RequestID),
		PayloadHash:          defaultString(action.PayloadHash, action.RequestID),
		ArtifactRef:          action.ArtifactRef,
	}
}

func (r *Repository) loadArenaEventLogIdentity(ctx context.Context, eventID string) (arenaEventLogIdentity, error) {
	const query = `
		SELECT
			aggregate_type,
			aggregate_id,
			stream_key,
			stream_seq,
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			round_no,
			barrier_id,
			event_type,
			event_version,
			schema_version,
			policy_bundle_version,
			rng_root_seed,
			seed_table_id,
			seed_hand_no,
			seed_seat_no,
			seed_stream_name,
			state_seq,
			causation_id,
			correlation_id,
			payload_uri,
			payload_hash,
			artifact_ref,
			state_hash_after
		FROM arena_event_log
		WHERE event_id = $1
	`

	var identity arenaEventLogIdentity
	err := r.db.QueryRowContext(ctx, query, eventID).Scan(
		&identity.AggregateType,
		&identity.AggregateID,
		&identity.StreamKey,
		&identity.StreamSeq,
		&identity.TournamentID,
		&identity.TableID,
		&identity.HandID,
		&identity.PhaseID,
		&identity.RoundNo,
		&identity.BarrierID,
		&identity.EventType,
		&identity.EventVersion,
		&identity.SchemaVersion,
		&identity.PolicyBundleVersion,
		&identity.RNGRootSeed,
		&identity.SeedTableID,
		&identity.SeedHandNo,
		&identity.SeedSeatNo,
		&identity.SeedStreamName,
		&identity.StateSeq,
		&identity.CausationID,
		&identity.CorrelationID,
		&identity.PayloadURI,
		&identity.PayloadHash,
		&identity.ArtifactRef,
		&identity.StateHashAfter,
	)
	return identity, err
}

func (r *Repository) loadArenaActionLogicalIdentity(
	ctx context.Context,
	handID string,
	seatID string,
	phaseID string,
	actionSeq int,
) (arenaActionLogicalIdentity, error) {
	const query = `
		SELECT
			tournament_id,
			table_id,
			hand_id,
			phase_id,
			seat_id,
			seat_alias,
			action_type,
			action_amount_bucket,
			action_seq,
			expected_state_seq,
			accepted_state_seq,
			validation_status,
			result_event_id,
			error_code,
			duplicate_of_request_id,
			schema_version,
			policy_bundle_version,
			state_hash,
			payload_hash,
			artifact_ref
		FROM arena_action
		WHERE hand_id = $1
		  AND seat_id = $2
		  AND phase_id = $3
		  AND action_seq = $4
	`

	var identity arenaActionLogicalIdentity
	err := r.db.QueryRowContext(ctx, query, handID, seatID, phaseID, actionSeq).Scan(
		&identity.TournamentID,
		&identity.TableID,
		&identity.HandID,
		&identity.PhaseID,
		&identity.SeatID,
		&identity.SeatAlias,
		&identity.ActionType,
		&identity.ActionAmountBucket,
		&identity.ActionSeq,
		&identity.ExpectedStateSeq,
		&identity.AcceptedStateSeq,
		&identity.ValidationStatus,
		&identity.ResultEventID,
		&identity.ErrorCode,
		&identity.DuplicateOfRequestID,
		&identity.SchemaVersion,
		&identity.PolicyBundleVersion,
		&identity.StateHash,
		&identity.PayloadHash,
		&identity.ArtifactRef,
	)
	return identity, err
}

func compareArenaActionLogicalIdentity(existing, expected arenaActionLogicalIdentity) string {
	switch {
	case existing.TournamentID != expected.TournamentID:
		return fmt.Sprintf("tournament_id mismatch: existing=%q expected=%q", existing.TournamentID, expected.TournamentID)
	case existing.TableID != expected.TableID:
		return fmt.Sprintf("table_id mismatch: existing=%q expected=%q", existing.TableID, expected.TableID)
	case existing.HandID != expected.HandID:
		return fmt.Sprintf("hand_id mismatch: existing=%q expected=%q", existing.HandID, expected.HandID)
	case existing.PhaseID != expected.PhaseID:
		return fmt.Sprintf("phase_id mismatch: existing=%q expected=%q", existing.PhaseID, expected.PhaseID)
	case existing.SeatID != expected.SeatID:
		return fmt.Sprintf("seat_id mismatch: existing=%q expected=%q", existing.SeatID, expected.SeatID)
	case existing.SeatAlias != expected.SeatAlias:
		return fmt.Sprintf("seat_alias mismatch: existing=%q expected=%q", existing.SeatAlias, expected.SeatAlias)
	case existing.ActionType != expected.ActionType:
		return fmt.Sprintf("action_type mismatch: existing=%q expected=%q", existing.ActionType, expected.ActionType)
	case existing.ActionAmountBucket != expected.ActionAmountBucket:
		return fmt.Sprintf("action_amount_bucket mismatch: existing=%d expected=%d", existing.ActionAmountBucket, expected.ActionAmountBucket)
	case existing.ActionSeq != expected.ActionSeq:
		return fmt.Sprintf("action_seq mismatch: existing=%d expected=%d", existing.ActionSeq, expected.ActionSeq)
	case existing.ExpectedStateSeq != expected.ExpectedStateSeq:
		return fmt.Sprintf("expected_state_seq mismatch: existing=%d expected=%d", existing.ExpectedStateSeq, expected.ExpectedStateSeq)
	case existing.AcceptedStateSeq != expected.AcceptedStateSeq:
		return fmt.Sprintf("accepted_state_seq mismatch: existing=%d expected=%d", existing.AcceptedStateSeq, expected.AcceptedStateSeq)
	case existing.ValidationStatus != expected.ValidationStatus:
		return fmt.Sprintf("validation_status mismatch: existing=%q expected=%q", existing.ValidationStatus, expected.ValidationStatus)
	case existing.ResultEventID != expected.ResultEventID:
		return fmt.Sprintf("result_event_id mismatch: existing=%q expected=%q", existing.ResultEventID, expected.ResultEventID)
	case existing.ErrorCode != expected.ErrorCode:
		return fmt.Sprintf("error_code mismatch: existing=%q expected=%q", existing.ErrorCode, expected.ErrorCode)
	case existing.DuplicateOfRequestID != expected.DuplicateOfRequestID:
		return fmt.Sprintf("duplicate_of_request_id mismatch: existing=%q expected=%q", existing.DuplicateOfRequestID, expected.DuplicateOfRequestID)
	case existing.SchemaVersion != expected.SchemaVersion:
		return fmt.Sprintf("schema_version mismatch: existing=%d expected=%d", existing.SchemaVersion, expected.SchemaVersion)
	case existing.PolicyBundleVersion != expected.PolicyBundleVersion:
		return fmt.Sprintf("policy_bundle_version mismatch: existing=%q expected=%q", existing.PolicyBundleVersion, expected.PolicyBundleVersion)
	case existing.StateHash != expected.StateHash:
		return fmt.Sprintf("state_hash mismatch: existing=%q expected=%q", existing.StateHash, expected.StateHash)
	case existing.PayloadHash != expected.PayloadHash:
		return fmt.Sprintf("payload_hash mismatch: existing=%q expected=%q", existing.PayloadHash, expected.PayloadHash)
	case existing.ArtifactRef != expected.ArtifactRef:
		return fmt.Sprintf("artifact_ref mismatch: existing=%q expected=%q", existing.ArtifactRef, expected.ArtifactRef)
	default:
		return ""
	}
}

func compareArenaEventLogIdentity(existing, expected arenaEventLogIdentity) string {
	switch {
	case existing.AggregateType != expected.AggregateType:
		return fmt.Sprintf("aggregate_type mismatch: existing=%q expected=%q", existing.AggregateType, expected.AggregateType)
	case existing.AggregateID != expected.AggregateID:
		return fmt.Sprintf("aggregate_id mismatch: existing=%q expected=%q", existing.AggregateID, expected.AggregateID)
	case existing.StreamKey != expected.StreamKey:
		return fmt.Sprintf("stream_key mismatch: existing=%q expected=%q", existing.StreamKey, expected.StreamKey)
	case existing.StreamSeq != expected.StreamSeq:
		return fmt.Sprintf("stream_seq mismatch: existing=%d expected=%d", existing.StreamSeq, expected.StreamSeq)
	case existing.TournamentID != expected.TournamentID:
		return fmt.Sprintf("tournament_id mismatch: existing=%q expected=%q", existing.TournamentID, expected.TournamentID)
	case existing.TableID != expected.TableID:
		return fmt.Sprintf("table_id mismatch: existing=%q expected=%q", existing.TableID, expected.TableID)
	case existing.HandID != expected.HandID:
		return fmt.Sprintf("hand_id mismatch: existing=%q expected=%q", existing.HandID, expected.HandID)
	case existing.PhaseID != expected.PhaseID:
		return fmt.Sprintf("phase_id mismatch: existing=%q expected=%q", existing.PhaseID, expected.PhaseID)
	case existing.RoundNo != expected.RoundNo:
		return fmt.Sprintf("round_no mismatch: existing=%d expected=%d", existing.RoundNo, expected.RoundNo)
	case existing.BarrierID != expected.BarrierID:
		return fmt.Sprintf("barrier_id mismatch: existing=%q expected=%q", existing.BarrierID, expected.BarrierID)
	case existing.EventType != expected.EventType:
		return fmt.Sprintf("event_type mismatch: existing=%q expected=%q", existing.EventType, expected.EventType)
	case existing.EventVersion != expected.EventVersion:
		return fmt.Sprintf("event_version mismatch: existing=%d expected=%d", existing.EventVersion, expected.EventVersion)
	case existing.SchemaVersion != expected.SchemaVersion:
		return fmt.Sprintf("schema_version mismatch: existing=%d expected=%d", existing.SchemaVersion, expected.SchemaVersion)
	case existing.PolicyBundleVersion != expected.PolicyBundleVersion:
		return fmt.Sprintf("policy_bundle_version mismatch: existing=%q expected=%q", existing.PolicyBundleVersion, expected.PolicyBundleVersion)
	case existing.RNGRootSeed != expected.RNGRootSeed:
		return fmt.Sprintf("rng_root_seed mismatch: existing=%q expected=%q", existing.RNGRootSeed, expected.RNGRootSeed)
	case existing.SeedTableID != expected.SeedTableID:
		return fmt.Sprintf("seed_table_id mismatch: existing=%q expected=%q", existing.SeedTableID, expected.SeedTableID)
	case existing.SeedHandNo != expected.SeedHandNo:
		return fmt.Sprintf("seed_hand_no mismatch: existing=%d expected=%d", existing.SeedHandNo, expected.SeedHandNo)
	case existing.SeedSeatNo != expected.SeedSeatNo:
		return fmt.Sprintf("seed_seat_no mismatch: existing=%d expected=%d", existing.SeedSeatNo, expected.SeedSeatNo)
	case existing.SeedStreamName != expected.SeedStreamName:
		return fmt.Sprintf("seed_stream_name mismatch: existing=%q expected=%q", existing.SeedStreamName, expected.SeedStreamName)
	case existing.StateSeq != expected.StateSeq:
		return fmt.Sprintf("state_seq mismatch: existing=%d expected=%d", existing.StateSeq, expected.StateSeq)
	case existing.CausationID != expected.CausationID:
		return fmt.Sprintf("causation_id mismatch: existing=%q expected=%q", existing.CausationID, expected.CausationID)
	case existing.CorrelationID != expected.CorrelationID:
		return fmt.Sprintf("correlation_id mismatch: existing=%q expected=%q", existing.CorrelationID, expected.CorrelationID)
	case existing.PayloadURI != expected.PayloadURI:
		return fmt.Sprintf("payload_uri mismatch: existing=%q expected=%q", existing.PayloadURI, expected.PayloadURI)
	case existing.PayloadHash != expected.PayloadHash:
		return fmt.Sprintf("payload_hash mismatch: existing=%q expected=%q", existing.PayloadHash, expected.PayloadHash)
	case existing.ArtifactRef != expected.ArtifactRef:
		return fmt.Sprintf("artifact_ref mismatch: existing=%q expected=%q", existing.ArtifactRef, expected.ArtifactRef)
	case existing.StateHashAfter != expected.StateHashAfter:
		return fmt.Sprintf("state_hash_after mismatch: existing=%q expected=%q", existing.StateHashAfter, expected.StateHashAfter)
	default:
		return ""
	}
}

func normalizeJSON(payload json.RawMessage) []byte {
	if len(payload) == 0 {
		return []byte("{}")
	}
	return payload
}

func defaultSchemaVersion(version int) int {
	return defaultInt(version, 1)
}

func defaultInt(value, fallback int) int {
	if value == 0 {
		return fallback
	}
	return value
}

func defaultFloat(value, fallback float64) float64 {
	if value == 0 {
		return fallback
	}
	return value
}

func defaultString(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func defaultTime(value time.Time) time.Time {
	if value.IsZero() {
		return nowUTC()
	}
	return value.UTC()
}

func nowUTC() time.Time {
	return time.Now().UTC()
}

func nullTime(value *time.Time) any {
	if value == nil || value.IsZero() {
		return nil
	}
	return value.UTC()
}

func nullableString(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func nullInt(value *int) any {
	if value == nil {
		return nil
	}
	return *value
}

func nullFloat(value *float64) any {
	if value == nil {
		return nil
	}
	return *value
}
