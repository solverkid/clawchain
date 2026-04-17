from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

import poker_mtt_results


class MiningRepository(Protocol):
    async def register_miner(self, miner: dict) -> dict: ...
    async def get_miner(self, address: str) -> dict | None: ...
    async def update_miner(self, address: str, updates: dict) -> dict: ...
    async def list_miners(self) -> list[dict]: ...
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
    async def get_reward_window(self, reward_window_id: str) -> dict | None: ...
    async def list_reward_windows(self) -> list[dict]: ...
    async def save_settlement_batch(self, settlement_batch: dict) -> dict: ...
    async def get_settlement_batch(self, settlement_batch_id: str) -> dict | None: ...
    async def list_settlement_batches(self) -> list[dict]: ...
    async def save_anchor_job(self, anchor_job: dict) -> dict: ...
    async def get_anchor_job(self, anchor_job_id: str) -> dict | None: ...
    async def list_anchor_jobs(self) -> list[dict]: ...
    async def save_artifact(self, artifact: dict) -> dict: ...
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
    async def save_poker_mtt_multiplier_snapshot(self, row: dict) -> dict: ...
    async def list_poker_mtt_multiplier_snapshots(
        self,
        *,
        miner_address: str | None = None,
        source_result_id: str | None = None,
    ) -> list[dict]: ...
    async def save_poker_mtt_final_ranking(self, final_ranking: dict) -> dict: ...
    async def get_poker_mtt_final_ranking(self, final_ranking_id: str) -> dict | None: ...
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
        self._settlement_batches: dict[str, dict] = {}
        self._anchor_jobs: dict[str, dict] = {}
        self._artifacts: dict[str, dict] = {}
        self._risk_cases: dict[str, dict] = {}
        self._arena_results: dict[str, dict] = {}
        self._poker_mtt_tournaments: dict[str, dict] = {}
        self._poker_mtt_hand_events: dict[str, dict] = {}
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
        miner = self._miners[address]
        miner.update(deepcopy(updates))
        return deepcopy(miner)

    async def list_miners(self) -> list[dict]:
        return [deepcopy(m) for m in self._miners.values()]

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

    async def save_settlement_batch(self, settlement_batch: dict) -> dict:
        current = deepcopy(self._settlement_batches.get(settlement_batch["id"], {}))
        current.update(deepcopy(settlement_batch))
        self._settlement_batches[settlement_batch["id"]] = current
        return deepcopy(current)

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
            if entry.get("evaluation_state") != "final":
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
        "policy_bundle_version": row.get("policy_bundle_version") or "poker_mtt_v1",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
