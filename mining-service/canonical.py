from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Sequence


_ISO_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T.*(Z|[+-]\d{2}:\d{2})$")


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fixed_decimal(value: Decimal | int | float | str, *, places: int = 6) -> str:
    quant = Decimal("1").scaleb(-places)
    decimal_value = Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)
    return format(decimal_value, f".{places}f")


def canonicalize(value: Any) -> Any:
    if isinstance(value, datetime):
        return isoformat_z(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not canonical")
        return value
    if isinstance(value, str):
        return _canonicalize_string(value)
    if isinstance(value, dict):
        return {str(key): canonicalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, tuple):
        return [canonicalize(item) for item in value]
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def canonical_json(payload: Any) -> str:
    return json.dumps(canonicalize(payload), sort_keys=True, separators=(",", ":"))


def canonical_hash(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def hash_sequence(items: Iterable[Any]) -> str:
    return canonical_hash({"items": list(items)})


def rows_root(rows: Sequence[dict], *, sort_keys: Sequence[str]) -> str:
    normalized_rows = [canonicalize(row) for row in rows]
    if sort_keys:
        normalized_rows.sort(key=lambda row: tuple(row.get(key) for key in sort_keys))
    return hash_sequence(normalized_rows)


def _canonicalize_string(value: str) -> str:
    if not _ISO_DATETIME_RE.match(value):
        return value
    try:
        return isoformat_z(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return value
