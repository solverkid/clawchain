from __future__ import annotations

from copy import deepcopy
from typing import Protocol


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
    async def save_poker_mtt_result(self, poker_mtt_result: dict) -> dict: ...
    async def list_poker_mtt_results(self) -> list[dict]: ...
    async def list_poker_mtt_results_for_miner(
        self,
        miner_address: str,
        *,
        eligible_only: bool = False,
        limit: int | None = None,
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
        self._poker_mtt_results: dict[str, dict] = {}
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
