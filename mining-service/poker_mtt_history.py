from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from canonical import canonical_hash


HAND_COMPLETED_SCHEMA_VERSION = "poker_mtt.hand_completed.v1"
HAND_COMPLETED_EVENT_TYPE = "poker_mtt.hand_completed"


@dataclass(frozen=True, slots=True)
class HandHistoryIngestResult:
    state: str
    event: dict | None = None
    previous_event: dict | None = None
    reason: str | None = None


class HandHistoryHotStore(Protocol):
    def get(self, hand_id: str) -> dict | None: ...
    def ingest(self, event: dict) -> HandHistoryIngestResult: ...


class InMemoryHandHistoryHotStore:
    def __init__(self) -> None:
        self._events_by_hand_id: dict[str, dict] = {}

    def get(self, hand_id: str) -> dict | None:
        event = self._events_by_hand_id.get(hand_id)
        return deepcopy(event) if event else None

    def ingest(self, event: dict) -> HandHistoryIngestResult:
        _validate_hand_completed_event(event)
        hand_id = event["identity"]["hand_id"]
        existing = self._events_by_hand_id.get(hand_id)
        if existing is None:
            if event.get("version") is None:
                return HandHistoryIngestResult(
                    state="conflict",
                    event=deepcopy(event),
                    reason="missing_version_without_existing_event",
                )
            self._events_by_hand_id[hand_id] = deepcopy(event)
            return HandHistoryIngestResult(state="inserted", event=deepcopy(event))

        version = event.get("version")
        if version is None:
            if event["checksum"] == existing.get("checksum"):
                return HandHistoryIngestResult(
                    state="duplicate",
                    event=deepcopy(existing),
                    previous_event=deepcopy(existing),
                )
            return HandHistoryIngestResult(
                state="conflict",
                event=deepcopy(event),
                previous_event=deepcopy(existing),
                reason="missing_version_checksum_mismatch",
            )

        existing_version = existing.get("version")
        if existing_version is not None and version < existing_version:
            return HandHistoryIngestResult(state="stale", event=deepcopy(event), previous_event=deepcopy(existing))
        if existing_version == version:
            if event["checksum"] == existing.get("checksum"):
                return HandHistoryIngestResult(
                    state="duplicate",
                    event=deepcopy(existing),
                    previous_event=deepcopy(existing),
                )
            return HandHistoryIngestResult(
                state="conflict",
                event=deepcopy(event),
                previous_event=deepcopy(existing),
                reason="same_version_checksum_mismatch",
            )

        self._events_by_hand_id[hand_id] = deepcopy(event)
        return HandHistoryIngestResult(state="updated", event=deepcopy(event), previous_event=deepcopy(existing))


def build_hand_completed_event(
    *,
    tournament_id: str,
    table_id: str,
    hand_no: int,
    version: int | None,
    payload: dict,
    source: dict,
) -> dict:
    hand_id = f"{tournament_id}:{table_id}:{hand_no}"
    payload_hash = canonical_hash(payload)
    version_suffix = version if version is not None else "unknown"
    event_id = (
        f"poker_mtt.hand:{tournament_id}:{table_id}:{hand_no}:"
        f"v{version_suffix}:{payload_hash.removeprefix('sha256:')[:12]}"
    )
    event = {
        "schema_version": HAND_COMPLETED_SCHEMA_VERSION,
        "event_type": HAND_COMPLETED_EVENT_TYPE,
        "event_id": event_id,
        "source": deepcopy(source),
        "identity": {
            "tournament_id": tournament_id,
            "table_id": table_id,
            "hand_no": hand_no,
            "hand_id": hand_id,
        },
        "checksum": payload_hash,
        "canonicalization": {
            "algorithm": "json-sort-keys-no-whitespace-utc-fixed-decimal-v1",
            "payload_hash": payload_hash,
        },
        "payload": deepcopy(payload),
    }
    if version is not None:
        event["version"] = version
    return event


def _validate_hand_completed_event(event: dict) -> None:
    if event.get("schema_version") != HAND_COMPLETED_SCHEMA_VERSION:
        raise ValueError("invalid hand completed schema_version")
    if event.get("event_type") != HAND_COMPLETED_EVENT_TYPE:
        raise ValueError("invalid hand completed event_type")
    if not event.get("checksum"):
        raise ValueError("missing hand completed checksum")
    identity = event.get("identity") or {}
    for key in ("tournament_id", "table_id", "hand_no", "hand_id"):
        if key not in identity:
            raise ValueError(f"missing hand identity field: {key}")
