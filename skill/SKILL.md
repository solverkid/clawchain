---
name: clawchain-miner
description: "ClawChain forecast-first miner runtime wrapper. Use it to bootstrap the current repo path with `setup.py`, run the mining loop with `mine.py`, and inspect service-backed miner status with `status.py`. This skill does not by itself provide a stock OpenClaw companion UI, menu bar app, or built-in `/buddy` command."
---

# ClawChain Miner

> **Authority:** This file is a thin wrapper around the current repo runtime path in `skill/scripts/setup.py`, `skill/scripts/mine.py`, and `skill/scripts/status.py`.
>
> **Not authoritative:** This file does not define protocol truth, token economics, or shipped companion surfaces. For current runtime truth, use [`docs/IMPLEMENTATION_STATUS_2026_04_10.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/IMPLEMENTATION_STATUS_2026_04_10.md). For protocol and settlement truth, use [`docs/MINING_DESIGN.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md).

## What This Skill Is

- A wrapper for the current forecast-first miner scripts
- A repo-local integration path for OpenClaw users
- A way to bootstrap wallet/config state, run the mining loop, and inspect status

## What This Skill Is Not

- Not a stock OpenClaw companion product layer
- Not proof that `Companion Home`, `Activities`, `History`, or `/buddy` already ship
- Not a challenge-era micro-task miner
- Not a standalone published ClawHub install contract

## Current Runtime Truth

Today the active miner path is:

- `forecast_15m` as the only full reward-bearing public lane
- `daily_anchor` as calibration-only scaffolding
- externally ingested `arena_multiplier` as a read-only modifier
- `mining-service` + Postgres as the authoritative service ledger
- `setup.py`, `mine.py`, and `status.py` as the current local entry points

The current runtime is **service-led**, not chain-led.

## Requirements

- Python 3.10+
- `requests`
- `cryptography` recommended for encrypted wallet storage
- A reachable ClawChain `mining-service` endpoint
- Optional: Codex CLI if you want `forecast_mode=codex_v1`

Notes:

- No local ClawChain testnet node is required for the current forecast-first miner path.
- No LLM API key is required for the default `heuristic_v1` path.

## Current Runtime Entry Path

1. Run `python3 scripts/setup.py`
   - generate or load a local wallet
   - register the miner against the service
   - persist `miner_address`, `forecast_mode`, and runtime config
2. Run `python3 scripts/mine.py`
   - fetch active tasks from the mining service
   - prioritize active `daily_anchor`
   - then process capped `forecast_15m` tasks
   - commit, reveal, and append local mining logs
3. Run `python3 scripts/status.py`
   - inspect service-backed miner status
   - inspect released/held rewards, latest settlement snapshot, and local reveal logs

Path note:

- inside the mounted skill directory the files appear as `scripts/...`
- in the repo root the same files are `skill/scripts/...`

## Effective Config Fields

Current effective fields in `scripts/config.json` include:

- `rpc_url`
- `miner_name`
- `wallet_path`
- `forecast_mode`
- `codex_binary`
- `codex_model`
- `codex_timeout_seconds`
- `request_timeout_seconds`
- `min_commit_time_remaining_seconds`
- `parallel_tasks`
- `max_tasks_per_run`
- `miner_address`

Some legacy-looking fields such as `auto_mine` and `log_dir` may still exist in the file, but they are not the main source of truth for companion UX or a durable control plane.

## Current Commands

```bash
python3 scripts/setup.py
python3 scripts/mine.py
python3 scripts/status.py
python3 scripts/doctor.py
```

`status.py` is the current supported status entry point. Do not document `status.py --chain` or challenge-era routes; those are stale.

## Optional Cron Wrapper

`openclaw cron` is only an optional scheduler wrapper around the current script flow. It does **not** create a persistent companion runtime by itself.

If you use cron, point it at the documented script entry path and treat it as a wrapper around `mine.py`, not as proof that ClawChain already has a full buddy-native control plane.

## OpenClaw Integration Boundary

OpenClaw provides the host platform:

- Gateway
- TUI
- Control UI / WebChat
- skills / plugins / slash-command infrastructure
- cron / heartbeat / background-task primitives

ClawChain still has to define and implement its own custom miner surfaces:

- `Companion Home`
- `Activities`
- `History`
- deterministic companion control verbs such as `/buddy`, `/pause`, `/resume`

Those are target surfaces, not stock OpenClaw defaults today.

`doctor.py` remains a pre-flight helper. It does not define companion command availability, browser IA, or product-contract truth.

## Known Gaps

- The current repo does not yet ship a durable companion state store
- The current repo does not yet ship `Companion Home`, `Activities`, or `History`
- The current miner loop still has a `daily_anchor` idempotency gap on repeated already-submitted / already-revealed paths; do not describe the current loop as a fully hardened always-on daemon until that gap is closed

## 中文说明

这是当前 ClawChain forecast-first 矿工路径的 skill 包装层，不是旧 challenge miner，也不是已经完成的 companion 产品层。

当前建议的使用方式：

1. `python3 scripts/setup.py`
2. `python3 scripts/mine.py`
3. `python3 scripts/status.py`

当前系统真实结构是：

- `forecast_15m` 公开主赛道
- `daily_anchor` 校准赛道
- `arena_multiplier` 外部写回修正因子
- `mining-service + Postgres` 服务化结算

如果需要完整产品/协议文档，请优先看：

- [`docs/IMPLEMENTATION_STATUS_2026_04_10.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/IMPLEMENTATION_STATUS_2026_04_10.md)
- [`docs/PRODUCT_SPEC.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/PRODUCT_SPEC.md)
- [`docs/MINING_DESIGN.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)
