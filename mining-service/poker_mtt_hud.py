from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from canonical import canonical_hash, canonicalize, rows_root


HUD_MANIFEST_SCHEMA_VERSION = "poker_mtt.hud_manifest.v1"
SHORT_TERM_HUD_MANIFEST_KIND = "poker_mtt_short_term_hud_manifest"
HUD_ROW_SORT_KEYS = ("tournament_id", "miner_address")


@dataclass(frozen=True, slots=True)
class HUDProjectionSettings:
    enabled: bool = False
    window: str = "short_term"


@dataclass(frozen=True, slots=True)
class HUDProjectionResult:
    state: str
    projected_rows: list[dict] | None = None
    reason: str | None = None


class InMemoryHUDHotStore:
    def __init__(self) -> None:
        self._projected_hand_checksums: dict[str, str] = {}
        self._rows_by_tournament_and_miner: dict[tuple[str, str], dict] = {}

    def project_hand(self, event: dict, *, settings: HUDProjectionSettings | None = None) -> HUDProjectionResult:
        settings = settings or HUDProjectionSettings()
        if not settings.enabled:
            return HUDProjectionResult(state="disabled", reason="hud_projection_disabled")
        tournament_id = event.get("identity", {}).get("tournament_id")
        hand_id = event.get("identity", {}).get("hand_id")
        checksum = event.get("checksum")
        if not tournament_id or not hand_id or not checksum:
            raise ValueError("invalid hand event for hud projection")

        existing_checksum = self._projected_hand_checksums.get(hand_id)
        if existing_checksum == checksum:
            return HUDProjectionResult(state="duplicate", projected_rows=self.snapshot_rows(tournament_id=tournament_id))
        if existing_checksum and existing_checksum != checksum:
            return HUDProjectionResult(state="conflict", reason="hand_checksum_mismatch")

        players = _players_from_event(event)
        preflop_actions = _preflop_actions_from_event(event)
        for miner_address, source_user_id in players.items():
            row = self._rows_by_tournament_and_miner.setdefault(
                (tournament_id, miner_address),
                {
                    "tournament_id": tournament_id,
                    "miner_address": miner_address,
                    "source_user_id": source_user_id,
                    "hud_window": settings.window,
                    "hands_seen": 0,
                    "vpip_count": 0,
                    "pfr_count": 0,
                    "three_bet_count": 0,
                },
            )
            row["hands_seen"] += 1
            player_preflop_actions = preflop_actions.get(miner_address, [])
            if any(_action_name(action) in {"bet", "call", "raise"} for action in player_preflop_actions):
                row["vpip_count"] += 1
            if any(_action_name(action) == "raise" and int(action.get("raise_number", 1) or 1) == 1 for action in player_preflop_actions):
                row["pfr_count"] += 1
            if any(_action_name(action) == "raise" and int(action.get("raise_number", 0) or 0) >= 3 for action in player_preflop_actions):
                row["three_bet_count"] += 1

        self._projected_hand_checksums[hand_id] = checksum
        return HUDProjectionResult(state="projected", projected_rows=self.snapshot_rows(tournament_id=tournament_id))

    def snapshot_rows(self, *, tournament_id: str) -> list[dict]:
        rows = [
            deepcopy(row)
            for (row_tournament_id, _miner_address), row in self._rows_by_tournament_and_miner.items()
            if row_tournament_id == tournament_id
        ]
        return sorted(rows, key=lambda row: (row["tournament_id"], row["miner_address"]))


def build_hud_manifest(
    *,
    tournament_id: str,
    rows: Sequence[dict],
    policy_bundle_version: str,
    generated_at: datetime | str,
    kind: str = SHORT_TERM_HUD_MANIFEST_KIND,
) -> dict:
    normalized_rows = [canonicalize(row) for row in rows]
    manifest = {
        "schema_version": HUD_MANIFEST_SCHEMA_VERSION,
        "kind": kind,
        "tournament_id": tournament_id,
        "policy_bundle_version": policy_bundle_version,
        "generated_at": canonicalize(generated_at),
        "row_count": len(normalized_rows),
        "row_sort_keys": list(HUD_ROW_SORT_KEYS),
        "rows_root": rows_root(normalized_rows, sort_keys=HUD_ROW_SORT_KEYS),
    }
    manifest["manifest_root"] = canonical_hash(manifest)
    return manifest


def _players_from_event(event: dict) -> dict[str, str | None]:
    players = {}
    for player in event.get("payload", {}).get("players", []):
        miner_address = player.get("miner_address")
        if miner_address:
            players[miner_address] = player.get("source_user_id")
    for action in event.get("payload", {}).get("actions", []):
        miner_address = action.get("miner_address")
        if miner_address:
            players.setdefault(miner_address, action.get("source_user_id"))
    return players


def _preflop_actions_from_event(event: dict) -> dict[str, list[dict]]:
    actions_by_miner: dict[str, list[dict]] = {}
    for action in event.get("payload", {}).get("actions", []):
        if str(action.get("street", "")).lower() != "preflop":
            continue
        miner_address = action.get("miner_address")
        if not miner_address:
            continue
        actions_by_miner.setdefault(miner_address, []).append(action)
    return actions_by_miner


def _action_name(action: dict) -> str:
    return str(action.get("action") or action.get("type") or "").lower()
