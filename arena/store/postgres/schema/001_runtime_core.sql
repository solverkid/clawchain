CREATE TABLE IF NOT EXISTS arena_wave (
    wave_id TEXT PRIMARY KEY,
    rated_or_practice TEXT NOT NULL,
    wave_state TEXT NOT NULL,
    registration_open_at TIMESTAMPTZ NOT NULL,
    registration_close_at TIMESTAMPTZ NOT NULL,
    scheduled_start_at TIMESTAMPTZ NOT NULL,
    target_shard_size INTEGER NOT NULL DEFAULT 0,
    soft_min_entrants INTEGER NOT NULL DEFAULT 0,
    soft_max_entrants INTEGER NOT NULL DEFAULT 0,
    hard_max_entrants INTEGER NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_tournament (
    tournament_id TEXT PRIMARY KEY,
    wave_id TEXT NOT NULL REFERENCES arena_wave (wave_id),
    rated_or_practice TEXT NOT NULL,
    tournament_state TEXT NOT NULL,
    exhibition BOOLEAN NOT NULL DEFAULT FALSE,
    no_multiplier BOOLEAN NOT NULL DEFAULT FALSE,
    cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    voided BOOLEAN NOT NULL DEFAULT FALSE,
    human_only BOOLEAN NOT NULL DEFAULT TRUE,
    integrity_hold BOOLEAN NOT NULL DEFAULT FALSE,
    seating_republish_count INTEGER NOT NULL DEFAULT 0,
    current_round_no INTEGER NOT NULL DEFAULT 0,
    current_level_no INTEGER NOT NULL DEFAULT 0,
    players_registered INTEGER NOT NULL DEFAULT 0,
    players_confirmed INTEGER NOT NULL DEFAULT 0,
    players_remaining INTEGER NOT NULL DEFAULT 0,
    active_table_count INTEGER NOT NULL DEFAULT 0,
    final_table_table_id TEXT NOT NULL DEFAULT '',
    rng_root_seed TEXT NOT NULL,
    time_cap_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_entrant (
    entrant_id TEXT PRIMARY KEY,
    wave_id TEXT NOT NULL REFERENCES arena_wave (wave_id),
    tournament_id TEXT,
    miner_id TEXT NOT NULL DEFAULT '',
    economic_unit_id TEXT NOT NULL DEFAULT '',
    seat_alias TEXT NOT NULL DEFAULT '',
    registration_state TEXT NOT NULL,
    table_id TEXT,
    seat_id TEXT,
    finish_rank INTEGER NOT NULL DEFAULT 0,
    stage_reached TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_entrant_wave_miner
    ON arena_entrant (wave_id, miner_id);

CREATE TABLE IF NOT EXISTS arena_waitlist (
    waitlist_entry_id TEXT PRIMARY KEY,
    wave_id TEXT NOT NULL REFERENCES arena_wave (wave_id),
    entrant_id TEXT NOT NULL REFERENCES arena_entrant (entrant_id),
    miner_id TEXT NOT NULL DEFAULT '',
    registration_state TEXT NOT NULL,
    waitlist_position INTEGER NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_waitlist_wave_position
    ON arena_waitlist (wave_id, waitlist_position);

CREATE TABLE IF NOT EXISTS arena_prestart_check (
    prestart_check_id TEXT PRIMARY KEY,
    wave_id TEXT NOT NULL REFERENCES arena_wave (wave_id),
    entrant_id TEXT NOT NULL REFERENCES arena_entrant (entrant_id),
    check_type TEXT NOT NULL,
    check_status TEXT NOT NULL,
    reason_code TEXT NOT NULL DEFAULT '',
    checked_at TIMESTAMPTZ NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_prestart_check_entrant_type
    ON arena_prestart_check (entrant_id, check_type);

CREATE TABLE IF NOT EXISTS arena_shard_assignment (
    shard_assignment_id TEXT PRIMARY KEY,
    wave_id TEXT NOT NULL REFERENCES arena_wave (wave_id),
    tournament_id TEXT REFERENCES arena_tournament (tournament_id),
    entrant_id TEXT NOT NULL REFERENCES arena_entrant (entrant_id),
    shard_no INTEGER NOT NULL DEFAULT 0,
    table_no INTEGER NOT NULL DEFAULT 0,
    seat_draw_token TEXT NOT NULL DEFAULT '',
    assignment_state TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_shard_assignment_entrant
    ON arena_shard_assignment (entrant_id);

CREATE TABLE IF NOT EXISTS arena_level (
    level_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    level_no INTEGER NOT NULL DEFAULT 0,
    small_blind BIGINT NOT NULL DEFAULT 0,
    big_blind BIGINT NOT NULL DEFAULT 0,
    ante BIGINT NOT NULL DEFAULT 0,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_level_tournament_level_no
    ON arena_level (tournament_id, level_no);

CREATE TABLE IF NOT EXISTS arena_table (
    table_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    table_state TEXT NOT NULL,
    table_no INTEGER NOT NULL,
    round_no INTEGER NOT NULL DEFAULT 0,
    current_hand_id TEXT NOT NULL DEFAULT '',
    button_seat_no INTEGER NOT NULL DEFAULT 0,
    acting_seat_no INTEGER NOT NULL DEFAULT 0,
    current_to_call BIGINT NOT NULL DEFAULT 0,
    min_raise_size BIGINT NOT NULL DEFAULT 0,
    pot_main BIGINT NOT NULL DEFAULT 0,
    state_seq BIGINT NOT NULL DEFAULT 0,
    level_no INTEGER NOT NULL DEFAULT 0,
    is_final_table BOOLEAN NOT NULL DEFAULT FALSE,
    paused_for_rebalance BOOLEAN NOT NULL DEFAULT FALSE,
    rng_root_seed TEXT NOT NULL DEFAULT '',
    seed_table_id TEXT NOT NULL DEFAULT '',
    seed_hand_no INTEGER NOT NULL DEFAULT 0,
    seed_seat_no INTEGER NOT NULL DEFAULT 0,
    seed_stream_name TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_table_tournament_table_no
    ON arena_table (tournament_id, table_no);

CREATE TABLE IF NOT EXISTS arena_hand (
    hand_id TEXT PRIMARY KEY,
    table_id TEXT NOT NULL REFERENCES arena_table (table_id),
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    round_no INTEGER NOT NULL DEFAULT 0,
    level_no INTEGER NOT NULL DEFAULT 0,
    hand_state TEXT NOT NULL,
    hand_started_at TIMESTAMPTZ NOT NULL,
    hand_closed_at TIMESTAMPTZ,
    button_seat_no INTEGER NOT NULL DEFAULT 0,
    active_seat_count INTEGER NOT NULL DEFAULT 0,
    pot_main BIGINT NOT NULL DEFAULT 0,
    winner_count INTEGER NOT NULL DEFAULT 0,
    time_cap_forced_last_hand BOOLEAN NOT NULL DEFAULT FALSE,
    rng_root_seed TEXT NOT NULL DEFAULT '',
    seed_table_id TEXT NOT NULL DEFAULT '',
    seed_hand_no INTEGER NOT NULL DEFAULT 0,
    seed_seat_no INTEGER NOT NULL DEFAULT 0,
    seed_stream_name TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_hand_table_round
    ON arena_hand (table_id, round_no);

CREATE TABLE IF NOT EXISTS arena_phase (
    phase_id TEXT PRIMARY KEY,
    hand_id TEXT NOT NULL REFERENCES arena_hand (hand_id),
    table_id TEXT NOT NULL REFERENCES arena_table (table_id),
    phase_type TEXT NOT NULL,
    phase_state TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    deadline_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    rng_root_seed TEXT NOT NULL DEFAULT '',
    seed_table_id TEXT NOT NULL DEFAULT '',
    seed_hand_no INTEGER NOT NULL DEFAULT 0,
    seed_seat_no INTEGER NOT NULL DEFAULT 0,
    seed_stream_name TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_phase_hand_type
    ON arena_phase (hand_id, phase_type);

CREATE TABLE IF NOT EXISTS arena_seat (
    seat_id TEXT PRIMARY KEY,
    table_id TEXT NOT NULL REFERENCES arena_table (table_id),
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    entrant_id TEXT REFERENCES arena_entrant (entrant_id),
    seat_no INTEGER NOT NULL DEFAULT 0,
    seat_alias TEXT NOT NULL DEFAULT '',
    miner_id TEXT NOT NULL DEFAULT '',
    seat_state TEXT NOT NULL,
    stack BIGINT NOT NULL DEFAULT 0,
    timeout_streak INTEGER NOT NULL DEFAULT 0,
    sit_out_warning_count INTEGER NOT NULL DEFAULT 0,
    last_forced_blind_round INTEGER NOT NULL DEFAULT 0,
    last_manual_action_at TIMESTAMPTZ,
    tournament_seat_draw_token TEXT NOT NULL DEFAULT '',
    admin_status_overlay TEXT NOT NULL DEFAULT '',
    removed_reason TEXT NOT NULL DEFAULT '',
    rng_root_seed TEXT NOT NULL DEFAULT '',
    seed_table_id TEXT NOT NULL DEFAULT '',
    seed_hand_no INTEGER NOT NULL DEFAULT 0,
    seed_seat_no INTEGER NOT NULL DEFAULT 0,
    seed_stream_name TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_seat_table_no
    ON arena_seat (table_id, seat_no);

CREATE TABLE IF NOT EXISTS arena_alias_map (
    alias_map_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    table_id TEXT REFERENCES arena_table (table_id),
    seat_id TEXT REFERENCES arena_seat (seat_id),
    entrant_id TEXT REFERENCES arena_entrant (entrant_id),
    seat_alias TEXT NOT NULL,
    miner_id TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_alias_map_tournament_alias
    ON arena_alias_map (tournament_id, seat_alias);

CREATE TABLE IF NOT EXISTS arena_reseat_event (
    reseat_event_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    from_table_id TEXT REFERENCES arena_table (table_id),
    to_table_id TEXT REFERENCES arena_table (table_id),
    seat_id TEXT REFERENCES arena_seat (seat_id),
    entrant_id TEXT REFERENCES arena_entrant (entrant_id),
    round_no INTEGER NOT NULL DEFAULT 0,
    caused_by_barrier_id TEXT NOT NULL DEFAULT '',
    occurred_at TIMESTAMPTZ NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arena_reseat_event_tournament_round
    ON arena_reseat_event (tournament_id, round_no);

CREATE TABLE IF NOT EXISTS arena_elimination_event (
    elimination_event_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    table_id TEXT REFERENCES arena_table (table_id),
    hand_id TEXT REFERENCES arena_hand (hand_id),
    seat_id TEXT REFERENCES arena_seat (seat_id),
    entrant_id TEXT REFERENCES arena_entrant (entrant_id),
    finish_rank INTEGER NOT NULL DEFAULT 0,
    stage_reached TEXT NOT NULL DEFAULT '',
    occurred_at TIMESTAMPTZ NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_elimination_event_entrant
    ON arena_elimination_event (entrant_id);

CREATE TABLE IF NOT EXISTS arena_event_log (
    event_id TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    stream_key TEXT NOT NULL,
    stream_seq BIGINT NOT NULL,
    tournament_id TEXT NOT NULL DEFAULT '',
    table_id TEXT NOT NULL DEFAULT '',
    hand_id TEXT NOT NULL DEFAULT '',
    phase_id TEXT NOT NULL DEFAULT '',
    round_no INTEGER NOT NULL DEFAULT 0,
    barrier_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL DEFAULT 1,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL,
    rng_root_seed TEXT NOT NULL DEFAULT '',
    seed_table_id TEXT NOT NULL DEFAULT '',
    seed_hand_no INTEGER NOT NULL DEFAULT 0,
    seed_seat_no INTEGER NOT NULL DEFAULT 0,
    seed_stream_name TEXT NOT NULL DEFAULT '',
    state_seq BIGINT NOT NULL DEFAULT 0,
    causation_id TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_uri TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    state_hash_after TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_event_log_stream
    ON arena_event_log (stream_key, stream_seq);

CREATE INDEX IF NOT EXISTS idx_arena_event_log_tournament
    ON arena_event_log (tournament_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_arena_event_log_table
    ON arena_event_log (table_id, occurred_at);

CREATE TABLE IF NOT EXISTS submission_ledger (
    request_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL DEFAULT '',
    table_id TEXT NOT NULL DEFAULT '',
    hand_id TEXT NOT NULL DEFAULT '',
    phase_id TEXT NOT NULL DEFAULT '',
    seat_id TEXT NOT NULL DEFAULT '',
    seat_alias TEXT NOT NULL DEFAULT '',
    miner_id TEXT NOT NULL DEFAULT '',
    expected_state_seq BIGINT NOT NULL DEFAULT 0,
    validation_status TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload_artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_action (
    request_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL DEFAULT '',
    table_id TEXT NOT NULL DEFAULT '',
    hand_id TEXT NOT NULL DEFAULT '',
    phase_id TEXT NOT NULL DEFAULT '',
    seat_id TEXT NOT NULL DEFAULT '',
    seat_alias TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL DEFAULT '',
    action_amount_bucket BIGINT NOT NULL DEFAULT 0,
    action_seq INTEGER NOT NULL DEFAULT 0,
    expected_state_seq BIGINT NOT NULL DEFAULT 0,
    accepted_state_seq BIGINT NOT NULL DEFAULT 0,
    validation_status TEXT NOT NULL DEFAULT '',
    result_event_id TEXT NOT NULL DEFAULT '',
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    error_code TEXT NOT NULL DEFAULT '',
    duplicate_of_request_id TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_action_hand_phase_action_seq
    ON arena_action (hand_id, seat_id, phase_id, action_seq);

CREATE INDEX IF NOT EXISTS idx_arena_action_tournament_received
    ON arena_action (tournament_id, received_at);

CREATE TABLE IF NOT EXISTS arena_action_deadline (
    deadline_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL DEFAULT '',
    table_id TEXT NOT NULL DEFAULT '',
    hand_id TEXT NOT NULL DEFAULT '',
    phase_id TEXT NOT NULL DEFAULT '',
    seat_id TEXT NOT NULL DEFAULT '',
    deadline_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    opened_by_event_id TEXT NOT NULL DEFAULT '',
    resolved_by_event_id TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_action_deadline_open
    ON arena_action_deadline (table_id, hand_id, phase_id, seat_id)
    WHERE status = 'open';

CREATE TABLE IF NOT EXISTS arena_round_barrier (
    barrier_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL DEFAULT '',
    round_no INTEGER NOT NULL DEFAULT 0,
    expected_table_count INTEGER NOT NULL DEFAULT 0,
    received_hand_close_count INTEGER NOT NULL DEFAULT 0,
    barrier_state TEXT NOT NULL DEFAULT '',
    pending_reseat_plan_ref TEXT NOT NULL DEFAULT '',
    pending_level_no INTEGER NOT NULL DEFAULT 0,
    terminate_after_current_round BOOLEAN NOT NULL DEFAULT FALSE,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_round_barrier_tournament_round
    ON arena_round_barrier (tournament_id, round_no);

CREATE TABLE IF NOT EXISTS arena_operator_intervention (
    intervention_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL DEFAULT '',
    table_id TEXT NOT NULL DEFAULT '',
    seat_id TEXT NOT NULL DEFAULT '',
    miner_id TEXT NOT NULL DEFAULT '',
    intervention_type TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT '',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_at_safe_point BOOLEAN NOT NULL DEFAULT FALSE,
    reason_code TEXT NOT NULL DEFAULT '',
    reason_detail TEXT NOT NULL DEFAULT '',
    created_event_id TEXT NOT NULL DEFAULT '',
    resolved_event_id TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_tournament_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    stream_key TEXT NOT NULL,
    stream_seq BIGINT NOT NULL,
    state_seq BIGINT NOT NULL DEFAULT 0,
    rng_root_seed TEXT NOT NULL DEFAULT '',
    seed_table_id TEXT NOT NULL DEFAULT '',
    seed_hand_no INTEGER NOT NULL DEFAULT 0,
    seed_seat_no INTEGER NOT NULL DEFAULT 0,
    seed_stream_name TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arena_tournament_snapshot_tournament_seq
    ON arena_tournament_snapshot (tournament_id, stream_seq DESC);

CREATE TABLE IF NOT EXISTS arena_table_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    table_id TEXT NOT NULL REFERENCES arena_table (table_id),
    stream_key TEXT NOT NULL,
    stream_seq BIGINT NOT NULL,
    state_seq BIGINT NOT NULL DEFAULT 0,
    rng_root_seed TEXT NOT NULL DEFAULT '',
    seed_table_id TEXT NOT NULL DEFAULT '',
    seed_hand_no INTEGER NOT NULL DEFAULT 0,
    seed_seat_no INTEGER NOT NULL DEFAULT 0,
    seed_stream_name TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arena_table_snapshot_table_seq
    ON arena_table_snapshot (table_id, stream_seq DESC);

CREATE TABLE IF NOT EXISTS arena_hand_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    table_id TEXT NOT NULL REFERENCES arena_table (table_id),
    hand_id TEXT NOT NULL,
    stream_key TEXT NOT NULL,
    stream_seq BIGINT NOT NULL,
    state_seq BIGINT NOT NULL DEFAULT 0,
    rng_root_seed TEXT NOT NULL DEFAULT '',
    seed_table_id TEXT NOT NULL DEFAULT '',
    seed_hand_no INTEGER NOT NULL DEFAULT 0,
    seed_seat_no INTEGER NOT NULL DEFAULT 0,
    seed_stream_name TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arena_hand_snapshot_hand_seq
    ON arena_hand_snapshot (hand_id, stream_seq DESC);

CREATE TABLE IF NOT EXISTS arena_standing_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL REFERENCES arena_tournament (tournament_id),
    stream_key TEXT NOT NULL,
    stream_seq BIGINT NOT NULL,
    state_seq BIGINT NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arena_standing_snapshot_tournament_seq
    ON arena_standing_snapshot (tournament_id, stream_seq DESC);
