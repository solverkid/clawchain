from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

import poker_mtt_results


class MiningRepository(Protocol):
    async def register_miner(self, miner: dict) -> dict: ...
    async def get_miner(self, address: str) -> dict | None: ...
    async def update_miner(self, address: str, updates: dict) -> dict: ...
    async def update_miner_cluster_identity(
        self,
        address: str,
        *,
        updated_at: datetime | str,
        economic_unit_id: str | None = None,
        ip_address: str | None = None,
        user_agent_hash: str | None = None,
    ) -> dict: ...
    async def update_miner_forecast_participation(
        self,
        address: str,
        *,
        updated_at: datetime | str,
        forecast_commits: int | None = None,
        forecast_reveals: int | None = None,
        ops_reliability: float | None = None,
        fast_task_opportunities: int | None = None,
        fast_task_misses: int | None = None,
        fast_window_start_at: datetime | str | None = None,
    ) -> dict: ...
    async def update_miner_forecast_settlement(
        self,
        address: str,
        *,
        updated_at: datetime | str,
        total_rewards: int | None = None,
        held_rewards: int | None = None,
        settled_tasks: int | None = None,
        correct_direction_count: int | None = None,
        edge_score_total: float | None = None,
        model_reliability: float | None = None,
        admission_state: str | None = None,
    ) -> dict: ...
    async def update_miner_public_ranking(
        self,
        address: str,
        *,
        public_rank: int,
        public_elo: int,
    ) -> dict: ...
    async def update_arena_miner_multiplier(
        self,
        address: str,
        *,
        arena_multiplier: float,
        updated_at: datetime | str,
    ) -> dict: ...
    async def update_poker_mtt_miner_multiplier(
        self,
        address: str,
        *,
        poker_mtt_multiplier: float,
        updated_at: datetime | str,
    ) -> dict: ...
    async def list_miners(self) -> list[dict]: ...
    async def list_miners_by_addresses(self, addresses: list[str]) -> list[dict]: ...
    async def count_active_miners(self) -> int: ...
    async def upsert_task(self, task: dict) -> dict: ...
    async def get_task(self, task_run_id: str) -> dict | None: ...
    async def list_tasks(self) -> list[dict]: ...
    async def list_due_unsettled_fast_tasks(self, now_iso: str) -> list[dict]: ...
    async def get_submission(self, task_run_id: str, miner_address: str) -> dict | None: ...
    async def save_submission(self, submission: dict) -> dict: ...
    async def list_submissions_for_task(self, task_run_id: str) -> list[dict]: ...
    async def list_submissions_for_miner(self, miner_address: str, *, limit: int | None = None) -> list[dict]: ...
    async def save_hold_entry(self, hold_entry: dict) -> dict: ...
    async def list_hold_entries_for_miner(self, miner_address: str) -> list[dict]: ...
    async def list_due_hold_entries(self, now_iso: str) -> list[dict]: ...
    async def save_reward_window(self, reward_window: dict) -> dict: ...
    async def link_reward_window_settlement_batch(
        self,
        reward_window_id: str,
        *,
        settlement_batch_id: str,
        updated_at: datetime | str,
    ) -> dict: ...
    async def get_reward_window(self, reward_window_id: str) -> dict | None: ...
    async def list_reward_windows(self) -> list[dict]: ...
    async def save_poker_mtt_budget_ledger(self, row: dict) -> dict: ...
    async def list_poker_mtt_budget_ledgers(
        self,
        *,
        budget_source_id: str | None = None,
        emission_epoch_id: str | None = None,
        reward_window_id: str | None = None,
        lane: str | None = None,
    ) -> list[dict]: ...
    async def save_settlement_batch(self, settlement_batch: dict) -> dict: ...
    async def sync_open_settlement_batch(
        self,
        settlement_batch_id: str,
        *,
        lane: str,
        window_start_at: datetime | str,
        window_end_at: datetime | str,
        reward_window_ids: list[str],
        policy_bundle_version: str,
        task_count: int,
        miner_count: int,
        total_reward_amount: int,
        updated_at: datetime | str,
        created_at: datetime | str | None = None,
    ) -> dict: ...
    async def mark_settlement_batch_anchor_ready(
        self,
        settlement_batch_id: str,
        *,
        policy_bundle_version: str,
        anchor_schema_version: str,
        canonical_root: str,
        anchor_payload_json: dict,
        anchor_payload_hash: str,
        updated_at: datetime | str,
    ) -> dict: ...
    async def mark_settlement_batch_anchor_submitted(
        self,
        settlement_batch_id: str,
        *,
        anchor_job_id: str,
        updated_at: datetime | str,
    ) -> dict: ...
    async def mark_settlement_batch_terminal(
        self,
        settlement_batch_id: str,
        *,
        state: str,
        updated_at: datetime | str,
    ) -> dict: ...
    async def cancel_settlement_batch(
        self,
        settlement_batch_id: str,
        *,
        total_reward_amount: int,
        updated_at: datetime | str,
    ) -> dict: ...
    async def get_settlement_batch(self, settlement_batch_id: str) -> dict | None: ...
    async def list_settlement_batches(self) -> list[dict]: ...
    async def save_anchor_job(self, anchor_job: dict) -> dict: ...
    async def update_anchor_job_broadcast(
        self,
        anchor_job_id: str,
        *,
        broadcast_status: str,
        broadcast_tx_hash: str | None,
        last_broadcast_at: datetime | str,
        updated_at: datetime | str,
    ) -> dict: ...
    async def update_anchor_job_confirmation(
        self,
        anchor_job_id: str,
        *,
        chain_confirmation_status: str,
        updated_at: datetime | str,
    ) -> dict: ...
    async def mark_anchor_job_terminal(
        self,
        anchor_job_id: str,
        *,
        state: str,
        updated_at: datetime | str,
        anchored_at: datetime | str | None = None,
        failure_reason: str | None = None,
        chain_confirmation_status: str | None = None,
    ) -> dict: ...
    async def get_anchor_job(self, anchor_job_id: str) -> dict | None: ...
    async def list_anchor_jobs(self) -> list[dict]: ...
    async def save_artifact(self, artifact: dict) -> dict: ...
    async def save_artifacts_bulk(self, artifacts: list[dict]) -> list[dict]: ...
    async def get_artifact(self, artifact_id: str) -> dict | None: ...
    async def list_artifacts_for_entity(self, entity_type: str, entity_id: str) -> list[dict]: ...
    async def save_risk_case(self, risk_case: dict) -> dict: ...
    async def get_risk_case(self, risk_case_id: str) -> dict | None: ...
    async def list_risk_cases(
        self,
        *,
        state: str | None = None,
        miner_address: str | None = None,
        economic_unit_id: str | None = None,
    ) -> list[dict]: ...
    async def save_arena_result(self, arena_result: dict) -> dict: ...
    async def list_arena_results_for_miner(
        self,
        miner_address: str,
        *,
        eligible_only: bool = False,
        limit: int | None = None,
    ) -> list[dict]: ...
    async def save_poker_mtt_tournament(self, tournament: dict) -> dict: ...
    async def get_poker_mtt_tournament(self, tournament_id: str) -> dict | None: ...
    async def save_poker_mtt_hand_event(self, event: dict) -> dict: ...
    async def get_poker_mtt_hand_event(self, hand_id: str) -> dict | None: ...
    async def list_poker_mtt_hand_events_for_tournament(self, tournament_id: str) -> list[dict]: ...
    async def save_poker_mtt_mq_checkpoint(self, checkpoint: dict) -> dict: ...
    async def list_poker_mtt_mq_checkpoints(self, *, tournament_id: str | None = None) -> list[dict]: ...
    async def save_poker_mtt_mq_conflict(self, conflict: dict) -> dict: ...
    async def list_poker_mtt_mq_conflicts(
        self,
        *,
        tournament_id: str | None = None,
        state: str | None = None,
    ) -> list[dict]: ...
    async def save_poker_mtt_mq_dlq(self, dlq: dict) -> dict: ...
    async def list_poker_mtt_mq_dlq(
        self,
        *,
        tournament_id: str | None = None,
        state: str | None = None,
    ) -> list[dict]: ...
    async def save_poker_mtt_hud_snapshot(self, row: dict) -> dict: ...
    async def list_poker_mtt_hud_snapshots(
        self,
        *,
        tournament_id: str | None = None,
        miner_address: str | None = None,
        hud_window: str | None = None,
    ) -> list[dict]: ...
    async def save_poker_mtt_hidden_eval_entry(self, row: dict) -> dict: ...
    async def list_poker_mtt_hidden_eval_entries_for_tournament(self, tournament_id: str) -> list[dict]: ...
    async def save_poker_mtt_rating_snapshot(self, row: dict) -> dict: ...
    async def list_poker_mtt_rating_snapshots(
        self,
        *,
        miner_address: str | None = None,
    ) -> list[dict]: ...
    async def list_latest_poker_mtt_rating_snapshots_for_miners(self, miner_addresses: list[str]) -> list[dict]: ...
    async def save_poker_mtt_multiplier_snapshot(self, row: dict) -> dict: ...
    async def list_poker_mtt_multiplier_snapshots(
        self,
        *,
        miner_address: str | None = None,
        source_result_id: str | None = None,
    ) -> list[dict]: ...
    async def save_poker_mtt_final_ranking(self, final_ranking: dict) -> dict: ...
    async def get_poker_mtt_final_ranking(self, final_ranking_id: str) -> dict | None: ...
    async def list_poker_mtt_final_rankings_by_ids(self, final_ranking_ids: list[str]) -> list[dict]: ...
    async def list_poker_mtt_final_rankings_for_tournament(self, tournament_id: str) -> list[dict]: ...
    async def list_poker_mtt_final_rankings_for_window(self, window_start_at: str, window_end_at: str) -> list[dict]: ...
    async def save_poker_mtt_result(self, poker_mtt_result: dict) -> dict: ...
    async def list_poker_mtt_results(self) -> list[dict]: ...
    async def list_poker_mtt_results_for_miner(
        self,
        miner_address: str,
        *,
        eligible_only: bool = False,
        limit: int | None = None,
    ) -> list[dict]: ...
    async def list_poker_mtt_results_for_reward_window(
        self,
        *,
        lane: str,
        window_start_at: datetime,
        window_end_at: datetime,
        include_provisional: bool,
        policy_bundle_version: str,
    ) -> list[dict]: ...
    async def load_poker_mtt_reward_window_inputs(
        self,
        *,
        lane: str,
        window_start_at: datetime,
        window_end_at: datetime,
        include_provisional: bool,
        policy_bundle_version: str,
        current_at: datetime,
    ) -> dict: ...
    async def list_poker_mtt_closed_reward_window_candidates(
        self,
        *,
        locked_after_at: datetime,
        locked_before_at: datetime,
        policy_bundle_versions: list[str],
        limit: int = 100000,
    ) -> list[dict]: ...
    async def save_poker_mtt_correction(self, correction: dict) -> dict: ...
    async def list_poker_mtt_corrections(
        self,
        *,
        target_entity_type: str | None = None,
        target_entity_id: str | None = None,
    ) -> list[dict]: ...


class FakeRepository:
    def __init__(self):
        self._miners: dict[str, dict] = {}
        self._tasks: dict[str, dict] = {}
        self._submissions: dict[tuple[str, str], dict] = {}
        self._hold_entries: dict[str, dict] = {}
        self._reward_windows: dict[str, dict] = {}
        self._poker_mtt_budget_ledgers: dict[str, dict] = {}
        self._settlement_batches: dict[str, dict] = {}
        self._anchor_jobs: dict[str, dict] = {}
        self._artifacts: dict[str, dict] = {}
        self._risk_cases: dict[str, dict] = {}
        self._arena_results: dict[str, dict] = {}
        self._poker_mtt_tournaments: dict[str, dict] = {}
        self._poker_mtt_hand_events: dict[str, dict] = {}
        self._poker_mtt_mq_checkpoints: dict[str, dict] = {}
        self._poker_mtt_mq_conflicts: dict[str, dict] = {}
        self._poker_mtt_mq_dlq: dict[str, dict] = {}
        self._poker_mtt_hud_snapshots: dict[str, dict] = {}
        self._poker_mtt_hidden_eval_entries: dict[str, dict] = {}
        self._poker_mtt_rating_snapshots: dict[str, dict] = {}
        self._poker_mtt_multiplier_snapshots: dict[str, dict] = {}
        self._poker_mtt_final_rankings: dict[str, dict] = {}
        self._poker_mtt_results: dict[str, dict] = {}
        self._poker_mtt_corrections: dict[str, dict] = {}
        self._request_index: dict[str, dict] = {}

    async def register_miner(self, miner: dict) -> dict:
        if miner["address"] in self._miners:
            raise ValueError("miner already registered")
        self._miners[miner["address"]] = deepcopy(miner)
        return deepcopy(self._miners[miner["address"]])

    async def get_miner(self, address: str) -> dict | None:
        miner = self._miners.get(address)
        return deepcopy(miner) if miner else None

    async def update_miner(self, address: str, updates: dict) -> dict:
        miner = self._miners.get(address)
        if miner is None:
            raise ValueError("miner not found")
        miner.update(deepcopy(updates))
        return deepcopy(miner)

    async def update_miner_cluster_identity(
        self,
        address: str,
        *,
        updated_at: datetime | str,
        economic_unit_id: str | None = None,
        ip_address: str | None = None,
        user_agent_hash: str | None = None,
    ) -> dict:
        updates = {"updated_at": updated_at}
        if economic_unit_id is not None:
            updates["economic_unit_id"] = economic_unit_id
        if ip_address is not None:
            updates["ip_address"] = ip_address
        if user_agent_hash is not None:
            updates["user_agent_hash"] = user_agent_hash
        return await self.update_miner(address, updates)

    async def update_miner_forecast_participation(
        self,
        address: str,
        *,
        updated_at: datetime | str,
        forecast_commits: int | None = None,
        forecast_reveals: int | None = None,
        ops_reliability: float | None = None,
        fast_task_opportunities: int | None = None,
        fast_task_misses: int | None = None,
        fast_window_start_at: datetime | str | None = None,
    ) -> dict:
        updates = {"updated_at": updated_at}
        if forecast_commits is not None:
            updates["forecast_commits"] = forecast_commits
        if forecast_reveals is not None:
            updates["forecast_reveals"] = forecast_reveals
        if ops_reliability is not None:
            updates["ops_reliability"] = ops_reliability
        if fast_task_opportunities is not None:
            updates["fast_task_opportunities"] = fast_task_opportunities
        if fast_task_misses is not None:
            updates["fast_task_misses"] = fast_task_misses
        if fast_window_start_at is not None:
            updates["fast_window_start_at"] = fast_window_start_at
        return await self.update_miner(address, updates)

    async def update_miner_forecast_settlement(
        self,
        address: str,
        *,
        updated_at: datetime | str,
        total_rewards: int | None = None,
        held_rewards: int | None = None,
        settled_tasks: int | None = None,
        correct_direction_count: int | None = None,
        edge_score_total: float | None = None,
        model_reliability: float | None = None,
        admission_state: str | None = None,
    ) -> dict:
        updates = {"updated_at": updated_at}
        if total_rewards is not None:
            updates["total_rewards"] = total_rewards
        if held_rewards is not None:
            updates["held_rewards"] = held_rewards
        if settled_tasks is not None:
            updates["settled_tasks"] = settled_tasks
        if correct_direction_count is not None:
            updates["correct_direction_count"] = correct_direction_count
        if edge_score_total is not None:
            updates["edge_score_total"] = edge_score_total
        if model_reliability is not None:
            updates["model_reliability"] = model_reliability
        if admission_state is not None:
            updates["admission_state"] = admission_state
        return await self.update_miner(address, updates)

    async def update_miner_public_ranking(
        self,
        address: str,
        *,
        public_rank: int,
        public_elo: int,
    ) -> dict:
        return await self.update_miner(
            address,
            {
                "public_rank": public_rank,
                "public_elo": public_elo,
            },
        )

    async def update_arena_miner_multiplier(
        self,
        address: str,
        *,
        arena_multiplier: float,
        updated_at: datetime | str,
    ) -> dict:
        return await self.update_miner(
            address,
            {
                "arena_multiplier": arena_multiplier,
                "updated_at": updated_at,
            },
        )

    async def update_poker_mtt_miner_multiplier(
        self,
        address: str,
        *,
        poker_mtt_multiplier: float,
        updated_at: datetime | str,
    ) -> dict:
        return await self.update_miner(
            address,
            {
                "poker_mtt_multiplier": poker_mtt_multiplier,
                "updated_at": updated_at,
            },
        )

    async def list_miners(self) -> list[dict]:
        return [deepcopy(m) for m in self._miners.values()]

    async def list_miners_by_addresses(self, addresses: list[str]) -> list[dict]:
        address_set = set(addresses)
        items = [deepcopy(miner) for address, miner in self._miners.items() if address in address_set]
        items.sort(key=lambda miner: miner.get("address") or "")
        return items

    async def count_active_miners(self) -> int:
        return sum(1 for miner in self._miners.values() if miner.get("status") == "active")

    async def upsert_task(self, task: dict) -> dict:
        existing = self._tasks.get(task["task_run_id"])
        merged = deepcopy(existing) if existing else {}
        merged.update(deepcopy(task))
        self._tasks[task["task_run_id"]] = merged
        return deepcopy(merged)

    async def get_task(self, task_run_id: str) -> dict | None:
        task = self._tasks.get(task_run_id)
        return deepcopy(task) if task else None

    async def list_tasks(self) -> list[dict]:
        return [deepcopy(task) for task in self._tasks.values()]

    async def list_due_unsettled_fast_tasks(self, now_iso: str) -> list[dict]:
        tasks = []
        for task in self._tasks.values():
            if task["lane"] != "forecast_15m":
                continue
            if task.get("state") in {"settled", "resolved"}:
                continue
            if task["resolve_at"] <= now_iso:
                tasks.append(deepcopy(task))
        return tasks

    async def get_submission(self, task_run_id: str, miner_address: str) -> dict | None:
        submission = self._submissions.get((task_run_id, miner_address))
        return deepcopy(submission) if submission else None

    async def save_submission(self, submission: dict) -> dict:
        key = (submission["task_run_id"], submission["miner_address"])
        for request_id_key in ("commit_request_id", "reveal_request_id"):
            request_id = submission.get(request_id_key)
            if request_id:
                existing = self._request_index.get(request_id)
                if existing:
                    existing_key = (existing["task_run_id"], existing["miner_address"])
                    if existing_key != key:
                        return deepcopy(existing)

        current = deepcopy(self._submissions.get(key, {}))
        current.update(deepcopy(submission))
        self._submissions[key] = current

        for request_id_key in ("commit_request_id", "reveal_request_id"):
            request_id = current.get(request_id_key)
            if request_id:
                self._request_index[request_id] = deepcopy(current)

        return deepcopy(current)

    async def list_submissions_for_task(self, task_run_id: str) -> list[dict]:
        return [
            deepcopy(submission)
            for (task_id, _), submission in self._submissions.items()
            if task_id == task_run_id
        ]

    async def list_submissions_for_miner(self, miner_address: str, *, limit: int | None = None) -> list[dict]:
        items = [
            deepcopy(submission)
            for (_, address), submission in self._submissions.items()
            if address == miner_address
        ]
        items.sort(
            key=lambda item: (
                item.get("accepted_reveal_at") or "",
                item.get("updated_at") or "",
                item.get("id") or "",
            ),
            reverse=True,
        )
        if limit is not None:
            items = items[:limit]
        return items

    async def save_hold_entry(self, hold_entry: dict) -> dict:
        current = deepcopy(self._hold_entries.get(hold_entry["id"], {}))
        current.update(deepcopy(hold_entry))
        self._hold_entries[hold_entry["id"]] = current
        return deepcopy(current)

    async def list_hold_entries_for_miner(self, miner_address: str) -> list[dict]:
        return [
            deepcopy(entry)
            for entry in self._hold_entries.values()
            if entry["miner_address"] == miner_address
        ]

    async def list_due_hold_entries(self, now_iso: str) -> list[dict]:
        due = []
        for entry in self._hold_entries.values():
            if entry.get("state") != "held":
                continue
            if entry["release_after"] <= now_iso:
                due.append(deepcopy(entry))
        return due

    async def save_reward_window(self, reward_window: dict) -> dict:
        current = deepcopy(self._reward_windows.get(reward_window["id"], {}))
        current.update(deepcopy(reward_window))
        self._reward_windows[reward_window["id"]] = current
        return deepcopy(current)

    async def link_reward_window_settlement_batch(
        self,
        reward_window_id: str,
        *,
        settlement_batch_id: str,
        updated_at: datetime | str,
    ) -> dict:
        if reward_window_id not in self._reward_windows:
            raise ValueError(f"reward window not found: {reward_window_id}")
        return await self.save_reward_window(
            {
                "id": reward_window_id,
                "settlement_batch_id": settlement_batch_id,
                "updated_at": updated_at,
            }
        )

    async def get_reward_window(self, reward_window_id: str) -> dict | None:
        reward_window = self._reward_windows.get(reward_window_id)
        return deepcopy(reward_window) if reward_window else None

    async def list_reward_windows(self) -> list[dict]:
        items = [deepcopy(window) for window in self._reward_windows.values()]
        items.sort(
            key=lambda item: (
                item.get("window_end_at") or "",
                item.get("updated_at") or "",
                item.get("id") or "",
            ),
            reverse=True,
        )
        return items

    async def save_poker_mtt_budget_ledger(self, row: dict) -> dict:
        ledger = _normalize_poker_mtt_budget_ledger(row)
        current = deepcopy(self._poker_mtt_budget_ledgers.get(ledger["id"], {}))
        current.update(deepcopy(ledger))
        self._poker_mtt_budget_ledgers[ledger["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_budget_ledgers(
        self,
        *,
        budget_source_id: str | None = None,
        emission_epoch_id: str | None = None,
        reward_window_id: str | None = None,
        lane: str | None = None,
    ) -> list[dict]:
        items = [deepcopy(row) for row in self._poker_mtt_budget_ledgers.values()]
        if budget_source_id is not None:
            items = [item for item in items if item.get("budget_source_id") == budget_source_id]
        if emission_epoch_id is not None:
            items = [item for item in items if item.get("emission_epoch_id") == emission_epoch_id]
        if reward_window_id is not None:
            items = [item for item in items if item.get("reward_window_id") == reward_window_id]
        if lane is not None:
            items = [item for item in items if item.get("lane") == lane]
        items.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or ""))
        return items

    async def save_settlement_batch(self, settlement_batch: dict) -> dict:
        current = deepcopy(self._settlement_batches.get(settlement_batch["id"], {}))
        current.update(deepcopy(settlement_batch))
        self._settlement_batches[settlement_batch["id"]] = current
        return deepcopy(current)

    async def sync_open_settlement_batch(
        self,
        settlement_batch_id: str,
        *,
        lane: str,
        window_start_at: datetime | str,
        window_end_at: datetime | str,
        reward_window_ids: list[str],
        policy_bundle_version: str,
        task_count: int,
        miner_count: int,
        total_reward_amount: int,
        updated_at: datetime | str,
        created_at: datetime | str | None = None,
    ) -> dict:
        payload = {
            "id": settlement_batch_id,
            "lane": lane,
            "state": "open",
            "window_start_at": window_start_at,
            "window_end_at": window_end_at,
            "reward_window_ids": reward_window_ids,
            "policy_bundle_version": policy_bundle_version,
            "task_count": task_count,
            "miner_count": miner_count,
            "total_reward_amount": total_reward_amount,
            "updated_at": updated_at,
        }
        if created_at is not None:
            payload.update(
                {
                    "anchor_job_id": None,
                    "anchor_schema_version": None,
                    "canonical_root": None,
                    "anchor_payload_json": None,
                    "anchor_payload_hash": None,
                    "created_at": created_at,
                }
            )
        return await self.save_settlement_batch(payload)

    async def mark_settlement_batch_anchor_ready(
        self,
        settlement_batch_id: str,
        *,
        policy_bundle_version: str,
        anchor_schema_version: str,
        canonical_root: str,
        anchor_payload_json: dict,
        anchor_payload_hash: str,
        updated_at: datetime | str,
    ) -> dict:
        if settlement_batch_id not in self._settlement_batches:
            raise ValueError(f"settlement batch not found: {settlement_batch_id}")
        return await self.save_settlement_batch(
            {
                "id": settlement_batch_id,
                "state": "anchor_ready",
                "anchor_job_id": None,
                "policy_bundle_version": policy_bundle_version,
                "anchor_schema_version": anchor_schema_version,
                "canonical_root": canonical_root,
                "anchor_payload_json": anchor_payload_json,
                "anchor_payload_hash": anchor_payload_hash,
                "updated_at": updated_at,
            }
        )

    async def mark_settlement_batch_anchor_submitted(
        self,
        settlement_batch_id: str,
        *,
        anchor_job_id: str,
        updated_at: datetime | str,
    ) -> dict:
        if settlement_batch_id not in self._settlement_batches:
            raise ValueError(f"settlement batch not found: {settlement_batch_id}")
        return await self.save_settlement_batch(
            {
                "id": settlement_batch_id,
                "state": "anchor_submitted",
                "anchor_job_id": anchor_job_id,
                "updated_at": updated_at,
            }
        )

    async def mark_settlement_batch_terminal(
        self,
        settlement_batch_id: str,
        *,
        state: str,
        updated_at: datetime | str,
    ) -> dict:
        if settlement_batch_id not in self._settlement_batches:
            raise ValueError(f"settlement batch not found: {settlement_batch_id}")
        return await self.save_settlement_batch(
            {
                "id": settlement_batch_id,
                "state": state,
                "updated_at": updated_at,
            }
        )

    async def cancel_settlement_batch(
        self,
        settlement_batch_id: str,
        *,
        total_reward_amount: int,
        updated_at: datetime | str,
    ) -> dict:
        if settlement_batch_id not in self._settlement_batches:
            raise ValueError(f"settlement batch not found: {settlement_batch_id}")
        return await self.save_settlement_batch(
            {
                "id": settlement_batch_id,
                "state": "cancelled",
                "total_reward_amount": total_reward_amount,
                "anchor_job_id": None,
                "anchor_schema_version": None,
                "canonical_root": None,
                "anchor_payload_json": None,
                "anchor_payload_hash": None,
                "updated_at": updated_at,
            }
        )

    async def get_settlement_batch(self, settlement_batch_id: str) -> dict | None:
        settlement_batch = self._settlement_batches.get(settlement_batch_id)
        return deepcopy(settlement_batch) if settlement_batch else None

    async def list_settlement_batches(self) -> list[dict]:
        items = [deepcopy(batch) for batch in self._settlement_batches.values()]
        items.sort(
            key=lambda item: (
                item.get("window_end_at") or "",
                item.get("updated_at") or "",
                item.get("id") or "",
            ),
            reverse=True,
        )
        return items

    async def save_anchor_job(self, anchor_job: dict) -> dict:
        current = deepcopy(self._anchor_jobs.get(anchor_job["id"], {}))
        current.update(deepcopy(anchor_job))
        self._anchor_jobs[anchor_job["id"]] = current
        return deepcopy(current)

    async def update_anchor_job_broadcast(
        self,
        anchor_job_id: str,
        *,
        broadcast_status: str,
        broadcast_tx_hash: str | None,
        last_broadcast_at: datetime | str,
        updated_at: datetime | str,
    ) -> dict:
        if anchor_job_id not in self._anchor_jobs:
            raise ValueError(f"anchor job not found: {anchor_job_id}")
        return await self.save_anchor_job(
            {
                "id": anchor_job_id,
                "state": "anchor_submitted",
                "broadcast_status": broadcast_status,
                "broadcast_tx_hash": broadcast_tx_hash,
                "last_broadcast_at": last_broadcast_at,
                "updated_at": updated_at,
            }
        )

    async def update_anchor_job_confirmation(
        self,
        anchor_job_id: str,
        *,
        chain_confirmation_status: str,
        updated_at: datetime | str,
    ) -> dict:
        if anchor_job_id not in self._anchor_jobs:
            raise ValueError(f"anchor job not found: {anchor_job_id}")
        return await self.save_anchor_job(
            {
                "id": anchor_job_id,
                "chain_confirmation_status": chain_confirmation_status,
                "updated_at": updated_at,
            }
        )

    async def mark_anchor_job_terminal(
        self,
        anchor_job_id: str,
        *,
        state: str,
        updated_at: datetime | str,
        anchored_at: datetime | str | None = None,
        failure_reason: str | None = None,
        chain_confirmation_status: str | None = None,
    ) -> dict:
        if anchor_job_id not in self._anchor_jobs:
            raise ValueError(f"anchor job not found: {anchor_job_id}")
        updates: dict = {
            "id": anchor_job_id,
            "state": state,
            "updated_at": updated_at,
            "failure_reason": failure_reason,
        }
        if anchored_at is not None:
            updates["anchored_at"] = anchored_at
        if chain_confirmation_status is not None:
            updates["chain_confirmation_status"] = chain_confirmation_status
        return await self.save_anchor_job(updates)

    async def get_anchor_job(self, anchor_job_id: str) -> dict | None:
        anchor_job = self._anchor_jobs.get(anchor_job_id)
        return deepcopy(anchor_job) if anchor_job else None

    async def list_anchor_jobs(self) -> list[dict]:
        items = [deepcopy(job) for job in self._anchor_jobs.values()]
        items.sort(
            key=lambda item: (
                item.get("updated_at") or "",
                item.get("created_at") or "",
                item.get("id") or "",
            ),
            reverse=True,
        )
        return items

    async def save_artifact(self, artifact: dict) -> dict:
        current = deepcopy(self._artifacts.get(artifact["id"], {}))
        current.update(deepcopy(artifact))
        self._artifacts[artifact["id"]] = current
        return deepcopy(current)

    async def save_artifacts_bulk(self, artifacts: list[dict]) -> list[dict]:
        saved = []
        for artifact in artifacts:
            existing = self._artifacts.get(artifact["id"])
            if existing and _artifact_payload_unchanged(existing, artifact):
                row = deepcopy(existing)
                row["_write_state"] = "unchanged"
                saved.append(row)
                continue
            current = deepcopy(existing or {})
            current.update(deepcopy(artifact))
            self._artifacts[artifact["id"]] = current
            row = deepcopy(current)
            row["_write_state"] = "upserted"
            saved.append(row)
        return saved

    async def get_artifact(self, artifact_id: str) -> dict | None:
        artifact = self._artifacts.get(artifact_id)
        return deepcopy(artifact) if artifact else None

    async def list_artifacts_for_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        items = [
            deepcopy(artifact)
            for artifact in self._artifacts.values()
            if artifact.get("entity_type") == entity_type and artifact.get("entity_id") == entity_id
        ]
        items.sort(
            key=lambda item: (
                item.get("updated_at") or "",
                item.get("created_at") or "",
                item.get("id") or "",
            ),
            reverse=True,
        )
        return items

    async def save_risk_case(self, risk_case: dict) -> dict:
        current = deepcopy(self._risk_cases.get(risk_case["id"], {}))
        current.update(deepcopy(risk_case))
        self._risk_cases[risk_case["id"]] = current
        return deepcopy(current)

    async def get_risk_case(self, risk_case_id: str) -> dict | None:
        risk_case = self._risk_cases.get(risk_case_id)
        return deepcopy(risk_case) if risk_case else None

    async def list_risk_cases(
        self,
        *,
        state: str | None = None,
        miner_address: str | None = None,
        economic_unit_id: str | None = None,
    ) -> list[dict]:
        cases = [deepcopy(case) for case in self._risk_cases.values()]
        if state is not None:
            cases = [case for case in cases if case.get("state") == state]
        if miner_address is not None:
            cases = [case for case in cases if case.get("miner_address") == miner_address]
        if economic_unit_id is not None:
            cases = [case for case in cases if case.get("economic_unit_id") == economic_unit_id]
        cases.sort(key=lambda item: (item.get("updated_at"), item.get("id")), reverse=True)
        return cases

    async def save_arena_result(self, arena_result: dict) -> dict:
        current = deepcopy(self._arena_results.get(arena_result["id"], {}))
        current.update(deepcopy(arena_result))
        self._arena_results[arena_result["id"]] = current
        return deepcopy(current)

    async def list_arena_results_for_miner(
        self,
        miner_address: str,
        *,
        eligible_only: bool = False,
        limit: int | None = None,
    ) -> list[dict]:
        items = [
            deepcopy(entry)
            for entry in self._arena_results.values()
            if entry["miner_address"] == miner_address
        ]
        if eligible_only:
            items = [entry for entry in items if entry.get("eligible_for_multiplier") is True]
        items.sort(key=lambda item: (item.get("updated_at"), item.get("id")), reverse=True)
        if limit is not None:
            items = items[:limit]
        return items

    async def save_poker_mtt_tournament(self, tournament: dict) -> dict:
        current = deepcopy(self._poker_mtt_tournaments.get(tournament["id"], {}))
        current.update(deepcopy(tournament))
        self._poker_mtt_tournaments[tournament["id"]] = current
        return deepcopy(current)

    async def get_poker_mtt_tournament(self, tournament_id: str) -> dict | None:
        tournament = self._poker_mtt_tournaments.get(tournament_id)
        return deepcopy(tournament) if tournament else None

    async def save_poker_mtt_hand_event(self, event: dict) -> dict:
        row = _normalize_poker_mtt_hand_event(event)
        existing = self._poker_mtt_hand_events.get(row["hand_id"])
        if existing is None:
            if row.get("version") is None:
                return {
                    **deepcopy(row),
                    "state": "conflict",
                    "ingest_state": "conflict",
                    "conflict_reason": "missing_version_without_existing_event",
                }
            self._poker_mtt_hand_events[row["hand_id"]] = deepcopy(row)
            return {**deepcopy(row), "state": "inserted"}

        version = row.get("version")
        if version is None:
            if row["checksum"] == existing.get("checksum"):
                return {**deepcopy(existing), "state": "duplicate"}
            return {
                **deepcopy(row),
                "state": "conflict",
                "ingest_state": "conflict",
                "conflict_reason": "missing_version_checksum_mismatch",
                "previous_event": deepcopy(existing),
            }

        existing_version = existing.get("version")
        if existing_version is not None and version < existing_version:
            return {**deepcopy(row), "state": "stale", "previous_event": deepcopy(existing)}
        if existing_version == version:
            if row["checksum"] == existing.get("checksum"):
                return {**deepcopy(existing), "state": "duplicate"}
            return {
                **deepcopy(row),
                "state": "conflict",
                "ingest_state": "conflict",
                "conflict_reason": "same_version_checksum_mismatch",
                "previous_event": deepcopy(existing),
            }

        updated = deepcopy(row)
        updated["created_at"] = existing.get("created_at") or updated.get("created_at")
        self._poker_mtt_hand_events[row["hand_id"]] = updated
        return {**deepcopy(updated), "state": "updated", "previous_event": deepcopy(existing)}

    async def get_poker_mtt_hand_event(self, hand_id: str) -> dict | None:
        event = self._poker_mtt_hand_events.get(hand_id)
        return deepcopy(event) if event else None

    async def list_poker_mtt_hand_events_for_tournament(self, tournament_id: str) -> list[dict]:
        items = [
            deepcopy(event)
            for event in self._poker_mtt_hand_events.values()
            if event.get("tournament_id") == tournament_id
        ]
        items.sort(key=lambda item: (item.get("table_id") or "", item.get("hand_no") or 0, item.get("hand_id") or ""))
        return items

    async def save_poker_mtt_mq_checkpoint(self, checkpoint: dict) -> dict:
        current = deepcopy(self._poker_mtt_mq_checkpoints.get(checkpoint["id"], {}))
        current.update(deepcopy(checkpoint))
        self._poker_mtt_mq_checkpoints[checkpoint["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_mq_checkpoints(self, *, tournament_id: str | None = None) -> list[dict]:
        items = [deepcopy(row) for row in self._poker_mtt_mq_checkpoints.values()]
        if tournament_id is not None:
            items = [row for row in items if row.get("tournament_id") == tournament_id]
        items.sort(key=lambda row: (row.get("topic") or "", row.get("consumer_group") or "", row.get("queue") or ""))
        return items

    async def save_poker_mtt_mq_conflict(self, conflict: dict) -> dict:
        current = deepcopy(self._poker_mtt_mq_conflicts.get(conflict["id"], {}))
        current.update(deepcopy(conflict))
        self._poker_mtt_mq_conflicts[conflict["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_mq_conflicts(
        self,
        *,
        tournament_id: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        items = [deepcopy(row) for row in self._poker_mtt_mq_conflicts.values()]
        if tournament_id is not None:
            items = [row for row in items if row.get("tournament_id") == tournament_id]
        if state is not None:
            items = [row for row in items if row.get("state") == state]
        items.sort(key=lambda row: (row.get("created_at") or "", row.get("id") or ""))
        return items

    async def save_poker_mtt_mq_dlq(self, dlq: dict) -> dict:
        current = deepcopy(self._poker_mtt_mq_dlq.get(dlq["id"], {}))
        current.update(deepcopy(dlq))
        self._poker_mtt_mq_dlq[dlq["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_mq_dlq(
        self,
        *,
        tournament_id: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        items = [deepcopy(row) for row in self._poker_mtt_mq_dlq.values()]
        if tournament_id is not None:
            items = [row for row in items if row.get("tournament_id") == tournament_id]
        if state is not None:
            items = [row for row in items if row.get("state") == state]
        items.sort(key=lambda row: (row.get("created_at") or "", row.get("id") or ""))
        return items

    async def save_poker_mtt_hud_snapshot(self, row: dict) -> dict:
        snapshot = _normalize_poker_mtt_hud_snapshot(row)
        current = deepcopy(self._poker_mtt_hud_snapshots.get(snapshot["id"], {}))
        current.update(deepcopy(snapshot))
        self._poker_mtt_hud_snapshots[snapshot["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_hud_snapshots(
        self,
        *,
        tournament_id: str | None = None,
        miner_address: str | None = None,
        hud_window: str | None = None,
    ) -> list[dict]:
        items = [deepcopy(snapshot) for snapshot in self._poker_mtt_hud_snapshots.values()]
        if tournament_id is not None:
            items = [item for item in items if item.get("tournament_id") == tournament_id]
        if miner_address is not None:
            items = [item for item in items if item.get("miner_address") == miner_address]
        if hud_window is not None:
            items = [item for item in items if item.get("hud_window") == hud_window]
        items.sort(key=lambda item: (item.get("updated_at") or "", item.get("id") or ""), reverse=True)
        return items

    async def save_poker_mtt_hidden_eval_entry(self, row: dict) -> dict:
        entry = _normalize_poker_mtt_hidden_eval_entry(row)
        current = deepcopy(self._poker_mtt_hidden_eval_entries.get(entry["id"], {}))
        current.update(deepcopy(entry))
        self._poker_mtt_hidden_eval_entries[entry["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_hidden_eval_entries_for_tournament(self, tournament_id: str) -> list[dict]:
        items = [
            deepcopy(entry)
            for entry in self._poker_mtt_hidden_eval_entries.values()
            if entry.get("tournament_id") == tournament_id
        ]
        items.sort(key=lambda item: (item.get("miner_address") or "", item.get("final_ranking_id") or ""))
        return items

    async def save_poker_mtt_rating_snapshot(self, row: dict) -> dict:
        snapshot = _normalize_poker_mtt_rating_snapshot(row)
        current = deepcopy(self._poker_mtt_rating_snapshots.get(snapshot["id"], {}))
        current.update(deepcopy(snapshot))
        self._poker_mtt_rating_snapshots[snapshot["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_rating_snapshots(
        self,
        *,
        miner_address: str | None = None,
    ) -> list[dict]:
        items = [deepcopy(snapshot) for snapshot in self._poker_mtt_rating_snapshots.values()]
        if miner_address is not None:
            items = [item for item in items if item.get("miner_address") == miner_address]
        items.sort(key=lambda item: (item.get("window_end_at") or "", item.get("id") or ""), reverse=True)
        return items

    async def list_latest_poker_mtt_rating_snapshots_for_miners(self, miner_addresses: list[str]) -> list[dict]:
        miner_set = set(miner_addresses)
        latest_by_miner: dict[str, dict] = {}
        for snapshot in self._poker_mtt_rating_snapshots.values():
            miner_address = snapshot.get("miner_address")
            if miner_address not in miner_set:
                continue
            current = latest_by_miner.get(miner_address)
            if current is None or (
                snapshot.get("window_end_at") or "",
                snapshot.get("id") or "",
            ) > (
                current.get("window_end_at") or "",
                current.get("id") or "",
            ):
                latest_by_miner[miner_address] = snapshot
        items = [deepcopy(row) for row in latest_by_miner.values()]
        items.sort(key=lambda item: (item.get("miner_address") or "", item.get("id") or ""))
        return items

    async def save_poker_mtt_multiplier_snapshot(self, row: dict) -> dict:
        snapshot = _normalize_poker_mtt_multiplier_snapshot(row)
        current = deepcopy(self._poker_mtt_multiplier_snapshots.get(snapshot["id"], {}))
        current.update(deepcopy(snapshot))
        self._poker_mtt_multiplier_snapshots[snapshot["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_multiplier_snapshots(
        self,
        *,
        miner_address: str | None = None,
        source_result_id: str | None = None,
    ) -> list[dict]:
        items = [deepcopy(snapshot) for snapshot in self._poker_mtt_multiplier_snapshots.values()]
        if miner_address is not None:
            items = [item for item in items if item.get("miner_address") == miner_address]
        if source_result_id is not None:
            items = [item for item in items if item.get("source_result_id") == source_result_id]
        items.sort(key=lambda item: (item.get("updated_at") or "", item.get("id") or ""), reverse=True)
        return items

    async def save_poker_mtt_final_ranking(self, final_ranking: dict) -> dict:
        current = deepcopy(self._poker_mtt_final_rankings.get(final_ranking["id"], {}))
        current.update(deepcopy(final_ranking))
        self._poker_mtt_final_rankings[final_ranking["id"]] = current
        return deepcopy(current)

    async def get_poker_mtt_final_ranking(self, final_ranking_id: str) -> dict | None:
        final_ranking = self._poker_mtt_final_rankings.get(final_ranking_id)
        return deepcopy(final_ranking) if final_ranking else None

    async def list_poker_mtt_final_rankings_by_ids(self, final_ranking_ids: list[str]) -> list[dict]:
        final_ranking_id_set = set(final_ranking_ids)
        items = [
            deepcopy(row)
            for final_ranking_id, row in self._poker_mtt_final_rankings.items()
            if final_ranking_id in final_ranking_id_set
        ]
        items.sort(key=lambda item: item.get("id") or "")
        return items

    async def list_poker_mtt_final_rankings_for_tournament(self, tournament_id: str) -> list[dict]:
        items = [
            deepcopy(row)
            for row in self._poker_mtt_final_rankings.values()
            if row.get("tournament_id") == tournament_id
        ]
        items.sort(
            key=lambda item: (
                item.get("rank") is None,
                item.get("rank") if item.get("rank") is not None else 10**12,
                item.get("id") or "",
            )
        )
        return items

    async def list_poker_mtt_final_rankings_for_window(self, window_start_at: str, window_end_at: str) -> list[dict]:
        items = [
            deepcopy(row)
            for row in self._poker_mtt_final_rankings.values()
            if window_start_at <= (row.get("created_at") or "") < window_end_at
        ]
        items.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or ""))
        return items

    async def save_poker_mtt_result(self, poker_mtt_result: dict) -> dict:
        current = deepcopy(self._poker_mtt_results.get(poker_mtt_result["id"], {}))
        current.update(deepcopy(poker_mtt_result))
        self._poker_mtt_results[poker_mtt_result["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_results(self) -> list[dict]:
        items = [deepcopy(entry) for entry in self._poker_mtt_results.values()]
        items.sort(key=lambda item: (item.get("updated_at"), item.get("id")), reverse=True)
        return items

    async def list_poker_mtt_results_for_miner(
        self,
        miner_address: str,
        *,
        eligible_only: bool = False,
        limit: int | None = None,
    ) -> list[dict]:
        items = [
            deepcopy(entry)
            for entry in self._poker_mtt_results.values()
            if entry["miner_address"] == miner_address
        ]
        if eligible_only:
            items = [entry for entry in items if entry.get("eligible_for_multiplier") is True]
        items.sort(key=lambda item: (item.get("updated_at"), item.get("id")), reverse=True)
        if limit is not None:
            items = items[:limit]
        return items

    async def list_poker_mtt_results_for_reward_window(
        self,
        *,
        lane: str,
        window_start_at: datetime,
        window_end_at: datetime,
        include_provisional: bool,
        policy_bundle_version: str,
    ) -> list[dict]:
        window_start = _utc_iso(window_start_at)
        window_end = _utc_iso(window_end_at)
        items = []
        for entry in self._poker_mtt_results.values():
            locked_at = entry.get("locked_at")
            if not locked_at or not (window_start <= _utc_iso(locked_at) < window_end):
                continue
            if entry.get("rated_or_practice") != "rated":
                continue
            if entry.get("human_only") is not True:
                continue
            evaluation_state = entry.get("evaluation_state")
            if evaluation_state != "final" and not (
                include_provisional and evaluation_state == "provisional"
            ):
                continue
            if not poker_mtt_results.result_policy_matches_reward_window(
                result_policy_bundle_version=entry.get("evaluation_version"),
                reward_policy_bundle_version=policy_bundle_version,
            ):
                continue
            if entry.get("evidence_state") not in poker_mtt_results.REWARD_READY_EVIDENCE_STATES:
                continue
            if not entry.get("final_ranking_id") or not entry.get("standing_snapshot_id") or not entry.get("evidence_root"):
                continue
            if entry.get("rank_state") != "ranked":
                continue
            if entry.get("no_multiplier_reason") is not None:
                continue
            if entry.get("eligible_for_multiplier") is not True:
                continue
            items.append(deepcopy(entry))
        items.sort(key=lambda item: (_utc_iso(item.get("locked_at")), item.get("id") or ""))
        return items

    async def load_poker_mtt_reward_window_inputs(
        self,
        *,
        lane: str,
        window_start_at: datetime,
        window_end_at: datetime,
        include_provisional: bool,
        policy_bundle_version: str,
        current_at: datetime,
    ) -> dict:
        results = await self._list_poker_mtt_results_for_reward_window_untracked(
            lane=lane,
            window_start_at=window_start_at,
            window_end_at=window_end_at,
            include_provisional=include_provisional,
            policy_bundle_version=policy_bundle_version,
        )
        final_ranking_ids = sorted({row["final_ranking_id"] for row in results if row.get("final_ranking_id")})
        miner_addresses = sorted({row["miner_address"] for row in results if row.get("miner_address")})
        latest_rating_by_miner: dict[str, dict] = {}
        miner_set = set(miner_addresses)
        for snapshot in self._poker_mtt_rating_snapshots.values():
            miner_address = snapshot.get("miner_address")
            if miner_address not in miner_set:
                continue
            current = latest_rating_by_miner.get(miner_address)
            if current is None or (
                snapshot.get("window_end_at") or "",
                snapshot.get("id") or "",
            ) > (
                current.get("window_end_at") or "",
                current.get("id") or "",
            ):
                latest_rating_by_miner[miner_address] = snapshot
        window_start_iso = _utc_iso(window_start_at)
        window_end_iso = _utc_iso(window_end_at)
        multiplier_snapshots_by_miner: dict[str, list[dict]] = {}
        for snapshot in self._poker_mtt_multiplier_snapshots.values():
            miner_address = snapshot.get("miner_address")
            if miner_address not in miner_set:
                continue
            effective_start = snapshot.get("effective_window_start_at")
            effective_end = snapshot.get("effective_window_end_at")
            if not effective_start or not effective_end:
                continue
            if effective_start >= window_end_iso or effective_end <= window_start_iso:
                continue
            multiplier_snapshots_by_miner.setdefault(miner_address, []).append(deepcopy(snapshot))
        for rows in multiplier_snapshots_by_miner.values():
            rows.sort(
                key=lambda item: (
                    item.get("effective_window_start_at") or "",
                    item.get("updated_at") or "",
                    item.get("id") or "",
                )
            )
        return {
            "results": results,
            "final_rankings_by_id": {
                final_ranking_id: deepcopy(self._poker_mtt_final_rankings[final_ranking_id])
                for final_ranking_id in final_ranking_ids
                if final_ranking_id in self._poker_mtt_final_rankings
            },
            "miners_by_address": {
                miner_address: deepcopy(self._miners[miner_address])
                for miner_address in miner_addresses
                if miner_address in self._miners
            },
            "rating_snapshots_by_miner": {
                miner_address: deepcopy(row)
                for miner_address, row in latest_rating_by_miner.items()
            },
            "multiplier_snapshots_by_miner": multiplier_snapshots_by_miner,
        }

    async def list_poker_mtt_closed_reward_window_candidates(
        self,
        *,
        locked_after_at: datetime,
        locked_before_at: datetime,
        policy_bundle_versions: list[str],
        limit: int = 100000,
    ) -> list[dict]:
        locked_after = _utc_iso(locked_after_at)
        locked_before = _utc_iso(locked_before_at)
        compatible_versions = set()
        for policy_bundle_version in policy_bundle_versions:
            compatible_versions.update(poker_mtt_results.compatible_result_policy_versions(policy_bundle_version))
        items = []
        for entry in self._poker_mtt_results.values():
            locked_at = entry.get("locked_at")
            if not locked_at or not (locked_after <= _utc_iso(locked_at) < locked_before):
                continue
            if entry.get("rated_or_practice") != "rated":
                continue
            if entry.get("human_only") is not True:
                continue
            if entry.get("evaluation_version") not in compatible_versions:
                continue
            if entry.get("evidence_state") not in poker_mtt_results.REWARD_READY_EVIDENCE_STATES:
                continue
            if not entry.get("final_ranking_id") or not entry.get("standing_snapshot_id") or not entry.get("evidence_root"):
                continue
            if entry.get("no_multiplier_reason") is not None:
                continue
            if entry.get("eligible_for_multiplier") is not True:
                continue
            items.append(deepcopy(entry))
        items.sort(key=lambda item: (_utc_iso(item.get("locked_at")), item.get("id") or ""))
        return items[:limit]

    async def _list_poker_mtt_results_for_reward_window_untracked(
        self,
        *,
        lane: str,
        window_start_at: datetime,
        window_end_at: datetime,
        include_provisional: bool,
        policy_bundle_version: str,
    ) -> list[dict]:
        window_start = _utc_iso(window_start_at)
        window_end = _utc_iso(window_end_at)
        items = []
        for entry in self._poker_mtt_results.values():
            locked_at = entry.get("locked_at")
            if not locked_at or not (window_start <= _utc_iso(locked_at) < window_end):
                continue
            if entry.get("rated_or_practice") != "rated":
                continue
            if entry.get("human_only") is not True:
                continue
            evaluation_state = entry.get("evaluation_state")
            if evaluation_state != "final" and not (
                include_provisional and evaluation_state == "provisional"
            ):
                continue
            if not poker_mtt_results.result_policy_matches_reward_window(
                result_policy_bundle_version=entry.get("evaluation_version"),
                reward_policy_bundle_version=policy_bundle_version,
            ):
                continue
            if entry.get("evidence_state") not in poker_mtt_results.REWARD_READY_EVIDENCE_STATES:
                continue
            if not entry.get("final_ranking_id") or not entry.get("standing_snapshot_id") or not entry.get("evidence_root"):
                continue
            if entry.get("rank_state") != "ranked":
                continue
            if entry.get("no_multiplier_reason") is not None:
                continue
            if entry.get("eligible_for_multiplier") is not True:
                continue
            items.append(deepcopy(entry))
        items.sort(key=lambda item: (_utc_iso(item.get("locked_at")), item.get("id") or ""))
        return items

    async def save_poker_mtt_correction(self, correction: dict) -> dict:
        current = deepcopy(self._poker_mtt_corrections.get(correction["id"], {}))
        current.update(deepcopy(correction))
        self._poker_mtt_corrections[correction["id"]] = current
        return deepcopy(current)

    async def list_poker_mtt_corrections(
        self,
        *,
        target_entity_type: str | None = None,
        target_entity_id: str | None = None,
    ) -> list[dict]:
        items = [deepcopy(correction) for correction in self._poker_mtt_corrections.values()]
        if target_entity_type is not None:
            items = [item for item in items if item.get("target_entity_type") == target_entity_type]
        if target_entity_id is not None:
            items = [item for item in items if item.get("target_entity_id") == target_entity_id]
        items.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or ""))
        return items


def _normalize_poker_mtt_hand_event(event: dict) -> dict:
    identity = event.get("identity") or {}
    hand_id = identity.get("hand_id") or event.get("hand_id")
    if not hand_id:
        raise ValueError("missing poker mtt hand_id")
    row = {
        "hand_id": hand_id,
        "tournament_id": identity.get("tournament_id") or event.get("tournament_id"),
        "table_id": identity.get("table_id") or event.get("table_id"),
        "hand_no": identity.get("hand_no") if identity.get("hand_no") is not None else event.get("hand_no"),
        "version": event.get("version"),
        "checksum": event["checksum"],
        "event_id": event.get("event_id"),
        "source_json": deepcopy(event.get("source_json") or event.get("source") or {}),
        "payload_json": deepcopy(event.get("payload_json") or event.get("payload") or {}),
        "ingest_state": event.get("ingest_state") or "inserted",
        "conflict_reason": event.get("conflict_reason"),
    }
    for field in ("created_at", "updated_at"):
        if field in event:
            row[field] = deepcopy(event[field])
    return row


def _utc_iso(value) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


def _artifact_payload_unchanged(existing: dict, candidate: dict) -> bool:
    return (
        existing.get("kind") == candidate.get("kind")
        and existing.get("entity_type") == candidate.get("entity_type")
        and existing.get("entity_id") == candidate.get("entity_id")
        and existing.get("payload_hash") == candidate.get("payload_hash")
        and existing.get("payload_json") == candidate.get("payload_json")
    )


def _normalize_poker_mtt_hud_snapshot(row: dict) -> dict:
    hud_window = row.get("hud_window") or "short_term"
    tournament_id = row.get("tournament_id") or ""
    miner_address = row.get("miner_address")
    if not miner_address:
        raise ValueError("missing poker mtt hud miner_address")
    snapshot_id = row.get("id") or f"poker_mtt_hud:{hud_window}:{tournament_id}:{miner_address}"
    base_fields = {
        "id",
        "tournament_id",
        "miner_address",
        "source_user_id",
        "hud_window",
        "hands_seen",
        "metrics_json",
        "policy_bundle_version",
        "manifest_root",
        "created_at",
        "updated_at",
    }
    metrics = deepcopy(row.get("metrics_json") or {})
    for key, value in row.items():
        if key not in base_fields:
            metrics[key] = deepcopy(value)
    return {
        "id": snapshot_id,
        "tournament_id": tournament_id,
        "miner_address": miner_address,
        "source_user_id": row.get("source_user_id"),
        "hud_window": hud_window,
        "hands_seen": int(row.get("hands_seen") or metrics.get("hands_seen") or 0),
        "metrics_json": metrics,
        "policy_bundle_version": row.get("policy_bundle_version") or "poker_mtt_v1",
        "manifest_root": row.get("manifest_root"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _normalize_poker_mtt_hidden_eval_entry(row: dict) -> dict:
    tournament_id = row.get("tournament_id")
    miner_address = row.get("miner_address")
    final_ranking_id = row.get("final_ranking_id")
    if not tournament_id:
        raise ValueError("missing poker mtt hidden eval tournament_id")
    if not miner_address:
        raise ValueError("missing poker mtt hidden eval miner_address")
    if not final_ranking_id:
        raise ValueError("missing poker mtt hidden eval final_ranking_id")
    return {
        "id": row.get("id") or f"poker_mtt_hidden_eval:{tournament_id}:{miner_address}:{final_ranking_id}",
        "tournament_id": tournament_id,
        "miner_address": miner_address,
        "final_ranking_id": final_ranking_id,
        "seed_assignment_id": row.get("seed_assignment_id"),
        "baseline_sample_id": row.get("baseline_sample_id"),
        "hidden_eval_score": float(row.get("hidden_eval_score") or 0.0),
        "score_components_json": deepcopy(row.get("score_components_json") or {}),
        "evidence_root": row.get("evidence_root"),
        "manifest_root": row.get("manifest_root"),
        "policy_bundle_version": row.get("policy_bundle_version") or "poker_mtt_v1",
        "visibility_state": row.get("visibility_state") or "service_internal",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _normalize_poker_mtt_rating_snapshot(row: dict) -> dict:
    miner_address = row.get("miner_address")
    if not miner_address:
        raise ValueError("missing poker mtt rating miner_address")
    window_start_at = row.get("window_start_at")
    window_end_at = row.get("window_end_at")
    if not window_start_at or not window_end_at:
        raise ValueError("missing poker mtt rating window")
    snapshot_id = row.get("id") or f"poker_mtt_rating:{miner_address}:{window_start_at}:{window_end_at}"
    return {
        "id": snapshot_id,
        "miner_address": miner_address,
        "window_start_at": row["window_start_at"],
        "window_end_at": row["window_end_at"],
        "public_rating": float(row.get("public_rating") or 0.0),
        "public_rank": row.get("public_rank"),
        "confidence": float(row.get("confidence") or 0.0),
        "policy_bundle_version": row.get("policy_bundle_version") or "poker_mtt_v1",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _normalize_poker_mtt_multiplier_snapshot(row: dict) -> dict:
    miner_address = row.get("miner_address")
    source_result_id = row.get("source_result_id")
    if not miner_address:
        raise ValueError("missing poker mtt multiplier miner_address")
    if not source_result_id:
        raise ValueError("missing poker mtt multiplier source_result_id")
    return {
        "id": row.get("id") or f"poker_mtt_multiplier:{source_result_id}",
        "miner_address": miner_address,
        "source_result_id": source_result_id,
        "multiplier_before": float(row.get("multiplier_before") or 1.0),
        "multiplier_after": float(row.get("multiplier_after") or 1.0),
        "rolling_score": row.get("rolling_score"),
        "effective_window_start_at": row.get("effective_window_start_at"),
        "effective_window_end_at": row.get("effective_window_end_at"),
        "policy_bundle_version": row.get("policy_bundle_version") or "poker_mtt_v1",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _normalize_poker_mtt_budget_ledger(row: dict) -> dict:
    budget_source_id = row.get("budget_source_id")
    emission_epoch_id = row.get("emission_epoch_id")
    reward_window_id = row.get("reward_window_id")
    if not budget_source_id:
        raise ValueError("missing poker mtt budget_source_id")
    if not emission_epoch_id:
        raise ValueError("missing poker mtt emission_epoch_id")
    if not reward_window_id:
        raise ValueError("missing poker mtt budget reward_window_id")
    requested_amount = int(row.get("requested_amount") or 0)
    approved_amount = int(row.get("approved_amount") or 0)
    paid_amount = int(row.get("paid_amount") or 0)
    forfeited_amount = int(row.get("forfeited_amount") or 0)
    rolled_amount = int(row.get("rolled_amount") or 0)
    return {
        "id": row.get("id") or f"poker_mtt_budget:{budget_source_id}:{emission_epoch_id}:{reward_window_id}",
        "budget_source_id": budget_source_id,
        "emission_epoch_id": emission_epoch_id,
        "lane": row.get("lane") or "poker_mtt_daily",
        "reward_window_id": reward_window_id,
        "settlement_batch_id": row.get("settlement_batch_id"),
        "window_start_at": row.get("window_start_at"),
        "window_end_at": row.get("window_end_at"),
        "requested_amount": requested_amount,
        "approved_amount": approved_amount,
        "paid_amount": paid_amount,
        "forfeited_amount": forfeited_amount,
        "rolled_amount": rolled_amount,
        "state": row.get("state") or "reserved",
        "policy_bundle_version": row.get("policy_bundle_version") or "poker_mtt_v1",
        "budget_root": row.get("budget_root"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
