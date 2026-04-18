from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RegisterMinerRequest(BaseModel):
    address: str
    name: str = "miner"
    public_key: str
    miner_version: str = "0.4.0"
    economic_unit_id: str | None = None


class CommitRequest(BaseModel):
    request_id: str
    task_run_id: str
    miner_id: str
    economic_unit_id: str | None = None
    commit_hash: str
    nonce: str
    client_version: str = "skill-v0.4.0"
    signature: str


class RevealRequest(BaseModel):
    request_id: str
    task_run_id: str
    miner_id: str
    economic_unit_id: str | None = None
    p_yes_bps: int = Field(ge=0, le=10000)
    nonce: str
    schema_version: str = "v1"
    signature: str


class ArenaResultItem(BaseModel):
    miner_id: str
    arena_score: float = Field(ge=-1.0, le=1.0)


class ApplyArenaResultsRequest(BaseModel):
    tournament_id: str
    rated_or_practice: str
    human_only: bool = True
    results: list[ArenaResultItem]


class PokerMTTResultItem(BaseModel):
    miner_id: str
    final_rank: int = Field(ge=1)
    tournament_result_score: float = Field(ge=-1.0, le=1.0)
    hidden_eval_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    consistency_input_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    evaluation_state: str = "provisional"
    economic_unit_id: str | None = None
    entry_number: int | None = Field(default=None, ge=0)
    reentry_count: int = Field(default=1, ge=1)
    final_ranking_id: str | None = None
    standing_snapshot_id: str | None = None
    standing_snapshot_hash: str | None = None
    evidence_root: str | None = None
    evidence_state: str = "pending"
    locked_at: datetime | None = None
    anchor_state: str = "unanchored"
    anchor_payload_hash: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    no_multiplier_reason: str | None = None


class ApplyPokerMTTResultsRequest(BaseModel):
    tournament_id: str
    rated_or_practice: str
    human_only: bool = True
    field_size: int = Field(ge=2)
    policy_bundle_version: str = "poker_mtt_v1"
    results: list[PokerMTTResultItem]


class PokerMTTHandCompletedEventRequest(BaseModel):
    schema_version: str
    event_type: str
    event_id: str
    source: dict = Field(default_factory=dict)
    identity: dict
    checksum: str
    canonicalization: dict = Field(default_factory=dict)
    payload: dict
    version: int | None = None


class PokerMTTHiddenEvalEntry(BaseModel):
    miner_address: str
    final_ranking_id: str
    hidden_eval_score: float = Field(ge=-10.0, le=10.0)
    score_components_json: dict = Field(default_factory=dict)
    evidence_root: str
    seed_assignment_id: str | None = None
    baseline_sample_id: str | None = None
    visibility_state: str | None = None


class FinalizePokerMTTHiddenEvalRequest(BaseModel):
    tournament_id: str
    policy_bundle_version: str = "poker_mtt_v1"
    seed_assignment_id: str
    baseline_sample_id: str | None = None
    entries: list[PokerMTTHiddenEvalEntry]


class BuildPokerMTTRatingSnapshotRequest(BaseModel):
    miner_address: str
    window_start_at: datetime
    window_end_at: datetime
    public_rating: float
    public_rank: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    policy_bundle_version: str = "poker_mtt_v1"


class PokerMTTFinalRankingRow(BaseModel):
    id: str
    tournament_id: str
    source_mtt_id: str
    source_user_id: str | None = None
    miner_address: str | None = None
    economic_unit_id: str | None = None
    member_id: str
    entry_number: int = Field(ge=0)
    reentry_count: int = Field(default=1, ge=1)
    rank: int | None = Field(default=None, ge=1)
    rank_state: str
    chip: float = 0.0
    chip_delta: float = 0.0
    died_time: str | None = None
    waiting_or_no_show: bool = False
    bounty: float = 0.0
    defeat_num: int = Field(default=0, ge=0)
    field_size_policy: str
    standing_snapshot_id: str
    standing_snapshot_hash: str
    evidence_root: str | None = None
    evidence_state: str = "pending"
    policy_bundle_version: str
    snapshot_found: bool = True
    status: str
    player_name: str | None = None
    room_id: str | None = None
    start_chip: float = 0.0
    stand_up_status: str | None = None
    source_rank: str | None = None
    source_rank_numeric: bool = False
    zset_score: float | None = None
    locked_at: datetime | None = None
    anchorable_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ApplyPokerMTTFinalRankingProjectionRequest(BaseModel):
    schema_version: str
    projection_id: str
    tournament_id: str
    source_mtt_id: str
    rated_or_practice: str
    human_only: bool = True
    field_size: int = Field(ge=2)
    policy_bundle_version: str = "poker_mtt_v1"
    standing_snapshot_id: str
    standing_snapshot_hash: str
    final_ranking_root: str
    locked_at: datetime
    rows: list[PokerMTTFinalRankingRow]


class BuildPokerMTTRewardWindowRequest(BaseModel):
    lane: str
    window_start_at: datetime
    window_end_at: datetime
    reward_pool_amount: int = Field(default=0, ge=0)
    include_provisional: bool = True
    policy_bundle_version: str | None = None
    reward_window_id: str | None = None


class RiskDecisionOverrideRequest(BaseModel):
    decision: str
    reason: str
    operator_id: str = "operator"
    authority_level: str = "operator"
