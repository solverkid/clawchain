#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


DEFAULT_PATTERNS = {
    "tencent_im_external_call": [
        r"adminapisgp\.im\.qcloud\.com",
        r"DeleteGroupMember.*qcloud",
    ],
    "rocketmq_publish_failure": [
        r"create grpc conn failed",
        r"context deadline exceeded",
        r"No route info of this topic",
        r"connect: connection refused",
        r"send message failed",
        r"POKER_RECORD_TOPIC.*(failed|error|err=)",
    ],
    "operation_channel_overflow": [
        r"channle is full",
        r"channel is full",
        r"timeout with seconds:5,sendCommand",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan local poker-mtt donor logs for release-blocking side effects.",
    )
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument(
        "--allow-rocketmq-publish-failure",
        action="store_true",
        help="Report RocketMQ failures without failing the command.",
    )
    parser.add_argument(
        "--allow-operation-channel-overflow",
        action="store_true",
        help="Report donor operation-channel overflow without failing the command.",
    )
    return parser.parse_args()


def iter_lines(paths: Iterable[Path]) -> Iterable[tuple[str, int, str]]:
    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                yield str(path), line_number, line.rstrip("\n")


def scan_logs(paths: list[Path]) -> dict[str, object]:
    compiled = {
        name: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        for name, patterns in DEFAULT_PATTERNS.items()
    }
    findings: dict[str, list[dict[str, object]]] = {name: [] for name in compiled}
    line_count = 0

    for path, line_number, line in iter_lines(paths):
        line_count += 1
        for name, patterns in compiled.items():
            if any(pattern.search(line) for pattern in patterns):
                findings[name].append(
                    {
                        "path": path,
                        "line": line_number,
                        "message": line[:500],
                    }
                )

    return {
        "line_count": line_count,
        "findings": findings,
        "counts": {name: len(items) for name, items in findings.items()},
    }


def blocking_findings(summary: dict[str, object], args: argparse.Namespace) -> list[str]:
    counts = summary.get("counts") or {}
    blockers: list[str] = []

    if int(counts.get("tencent_im_external_call") or 0) > 0:
        blockers.append("tencent_im_external_call")
    if (
        int(counts.get("rocketmq_publish_failure") or 0) > 0
        and not args.allow_rocketmq_publish_failure
    ):
        blockers.append("rocketmq_publish_failure")
    if (
        int(counts.get("operation_channel_overflow") or 0) > 0
        and not args.allow_operation_channel_overflow
    ):
        blockers.append("operation_channel_overflow")
    return blockers


def main() -> int:
    args = parse_args()
    missing = [str(path) for path in args.logs if not path.exists()]
    if missing:
        print(json.dumps({"error": "missing_log_files", "paths": missing}, indent=2))
        return 2

    summary = scan_logs(args.logs)
    blockers = blocking_findings(summary, args)
    summary["blocking_findings"] = blockers
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
