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
    evidence_root: str | None = None


class ApplyPokerMTTResultsRequest(BaseModel):
    tournament_id: str
    rated_or_practice: str
    human_only: bool = True
    field_size: int = Field(ge=2)
    policy_bundle_version: str = "poker_mtt_v1"
    results: list[PokerMTTResultItem]


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
