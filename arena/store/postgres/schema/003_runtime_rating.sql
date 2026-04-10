CREATE TABLE IF NOT EXISTS arena_rating_input (
    input_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL DEFAULT '',
    entrant_id TEXT NOT NULL DEFAULT '',
    miner_address TEXT NOT NULL DEFAULT '',
    rated_or_practice TEXT NOT NULL,
    human_only BOOLEAN NOT NULL DEFAULT TRUE,
    finish_rank INTEGER NOT NULL DEFAULT 0,
    finish_percentile DOUBLE PRECISION NOT NULL DEFAULT 0,
    hands_played INTEGER NOT NULL DEFAULT 0,
    meaningful_decisions INTEGER NOT NULL DEFAULT 0,
    auto_actions INTEGER NOT NULL DEFAULT 0,
    timeout_actions INTEGER NOT NULL DEFAULT 0,
    invalid_actions INTEGER NOT NULL DEFAULT 0,
    stage_reached TEXT NOT NULL DEFAULT '',
    stack_path_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    score_components JSONB NOT NULL DEFAULT '{}'::jsonb,
    penalties JSONB NOT NULL DEFAULT '{}'::jsonb,
    tournament_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    confidence_weight DOUBLE PRECISION NOT NULL DEFAULT 0,
    field_strength_adjustment DOUBLE PRECISION NOT NULL DEFAULT 0,
    bot_adjustment DOUBLE PRECISION NOT NULL DEFAULT 0,
    time_cap_adjustment DOUBLE PRECISION NOT NULL DEFAULT 0,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arena_rating_input_tournament
    ON arena_rating_input (tournament_id, miner_address);

CREATE TABLE IF NOT EXISTS arena_collusion_metric (
    metric_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL DEFAULT '',
    miner_address TEXT NOT NULL DEFAULT '',
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rating_state_current (
    miner_address TEXT PRIMARY KEY,
    mu DOUBLE PRECISION NOT NULL DEFAULT 25,
    sigma DOUBLE PRECISION NOT NULL DEFAULT 8.333333,
    arena_reliability DOUBLE PRECISION NOT NULL DEFAULT 1,
    public_elo INTEGER NOT NULL DEFAULT 1200,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rating_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    miner_address TEXT NOT NULL DEFAULT '',
    mu DOUBLE PRECISION NOT NULL DEFAULT 25,
    sigma DOUBLE PRECISION NOT NULL DEFAULT 8.333333,
    arena_reliability DOUBLE PRECISION NOT NULL DEFAULT 1,
    public_elo INTEGER NOT NULL DEFAULT 1200,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public_ladder_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL DEFAULT '',
    miner_address TEXT NOT NULL DEFAULT '',
    public_rank INTEGER NOT NULL DEFAULT 0,
    public_elo INTEGER NOT NULL DEFAULT 1200,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_multiplier_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL DEFAULT '',
    miner_address TEXT NOT NULL DEFAULT '',
    eligible_for_multiplier BOOLEAN NOT NULL DEFAULT FALSE,
    tournament_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    confidence_weight DOUBLE PRECISION NOT NULL DEFAULT 0,
    multiplier_before DOUBLE PRECISION NOT NULL DEFAULT 1,
    multiplier_after DOUBLE PRECISION NOT NULL DEFAULT 1,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS miners (
    address TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    registration_index INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    public_key TEXT NOT NULL,
    economic_unit_id TEXT NOT NULL,
    ip_address TEXT,
    user_agent_hash TEXT,
    total_rewards BIGINT NOT NULL DEFAULT 0,
    forecast_commits INTEGER NOT NULL DEFAULT 0,
    forecast_reveals INTEGER NOT NULL DEFAULT 0,
    settled_tasks INTEGER NOT NULL DEFAULT 0,
    correct_direction_count INTEGER NOT NULL DEFAULT 0,
    edge_score_total DOUBLE PRECISION NOT NULL DEFAULT 0,
    held_rewards BIGINT NOT NULL DEFAULT 0,
    fast_task_opportunities INTEGER NOT NULL DEFAULT 0,
    fast_task_misses INTEGER NOT NULL DEFAULT 0,
    fast_window_start_at TIMESTAMPTZ,
    admission_state TEXT NOT NULL DEFAULT 'probation',
    model_reliability DOUBLE PRECISION NOT NULL DEFAULT 1,
    ops_reliability DOUBLE PRECISION NOT NULL DEFAULT 1,
    arena_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1,
    public_rank INTEGER,
    public_elo INTEGER NOT NULL DEFAULT 1200,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_result_entries (
    id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL,
    miner_address TEXT NOT NULL,
    rated_or_practice TEXT NOT NULL,
    human_only BOOLEAN NOT NULL DEFAULT TRUE,
    eligible_for_multiplier BOOLEAN NOT NULL DEFAULT FALSE,
    arena_score DOUBLE PRECISION NOT NULL,
    conservative_skill DOUBLE PRECISION,
    multiplier_after DOUBLE PRECISION NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arena_result_entries_miner
    ON arena_result_entries (miner_address, updated_at DESC);
