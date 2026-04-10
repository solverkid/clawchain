CREATE TABLE IF NOT EXISTS arena_lobby_projection (
    tournament_id TEXT PRIMARY KEY,
    state_seq BIGINT NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_live_table_projection (
    table_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL DEFAULT '',
    state_seq BIGINT NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arena_live_table_projection_tournament
    ON arena_live_table_projection (tournament_id);

CREATE TABLE IF NOT EXISTS arena_standing_projection (
    tournament_id TEXT PRIMARY KEY,
    state_seq BIGINT NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_postgame_projection (
    tournament_id TEXT PRIMARY KEY,
    state_seq BIGINT NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    state_hash TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outbox_event (
    event_id TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    stream_key TEXT NOT NULL,
    lane TEXT NOT NULL DEFAULT 'arena',
    season_id TEXT NOT NULL DEFAULT '',
    reward_window_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL DEFAULT 1,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    causation_id TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    producer TEXT NOT NULL DEFAULT 'arenad',
    visibility TEXT NOT NULL DEFAULT 'internal',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_uri TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    payload_hash TEXT NOT NULL,
    artifact_ref TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_outbox_event_stream
    ON outbox_event (stream_key, occurred_at);

CREATE TABLE IF NOT EXISTS outbox_dispatch (
    dispatch_id TEXT PRIMARY KEY,
    outbox_event_id TEXT NOT NULL REFERENCES outbox_event (event_id),
    consumer_name TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    next_attempt_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_outbox_dispatch_consumer
    ON outbox_dispatch (outbox_event_id, consumer_name);

CREATE TABLE IF NOT EXISTS projector_cursor (
    projector_name TEXT PRIMARY KEY,
    last_event_id TEXT NOT NULL DEFAULT '',
    last_stream_key TEXT NOT NULL DEFAULT '',
    last_stream_seq BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dead_letter_event (
    dead_letter_id TEXT PRIMARY KEY,
    outbox_event_id TEXT NOT NULL DEFAULT '',
    projector_name TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1,
    policy_bundle_version TEXT NOT NULL DEFAULT 'v1',
    payload_hash TEXT NOT NULL DEFAULT '',
    artifact_ref TEXT NOT NULL DEFAULT '',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dead_letter_event_projector
    ON dead_letter_event (projector_name, occurred_at);
