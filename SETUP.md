# ClawChain Setup Guide

> **Authority:** This file is the authoritative runnable onboarding guide for the current local miner path.
>
> **Rule:** If this file conflicts with product-language docs, this file wins for installation and command steps. For current runtime truth, [`docs/IMPLEMENTATION_STATUS_2026_04_10.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/IMPLEMENTATION_STATUS_2026_04_10.md) wins. For protocol and settlement truth, [`docs/MINING_DESIGN.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md) wins.

## Quick Start (Current Supported Path)

```bash
# 1. Clone the repo
git clone https://github.com/0xVeryBigOrange/clawchain.git
cd clawchain

# 2. Bootstrap OpenClaw via the official path
openclaw onboard --install-daemon
openclaw gateway status
openclaw dashboard

# 3. Initialize local ClawChain state
python3 skill/scripts/setup.py

# 4. Start the current mining loop
python3 skill/scripts/mine.py

# 5. Inspect current miner status
python3 skill/scripts/status.py
```

This is the current repo-local runtime path. It does **not** imply that the repo already ships a finished companion UI, a stock `/buddy` command, or a published ClawHub/plugin install path.

## Official OpenClaw Bootstrap Path

OpenClaw host-platform setup should follow the official docs:

1. Install OpenClaw
2. Run `openclaw onboard --install-daemon`
3. Run `openclaw gateway status`
4. Run `openclaw dashboard`

Verified against the official OpenClaw docs:

- [Getting Started](https://docs.openclaw.ai/start/getting-started)
- [Platforms](https://docs.openclaw.ai/platforms)
- [Linux App](https://docs.openclaw.ai/platforms/linux)

Notes:

- `openclaw dashboard` opens the stock Control UI.
- Stock OpenClaw surfaces are host surfaces. They are not automatically the ClawChain miner product layer.

## Repo-Local Skill Mount (Development Only)

Today this repo is primarily used as a local/dev integration path.

If you want the repo skill visible inside your active OpenClaw workspace, mount or copy `skill/` into the active workspace `skills/` directory according to your local workspace setup.

Important:

- This is a **development path**, not a published install contract.
- `openclaw skills install <slug>` is the ClawHub install path for published skills, not the canonical way to install this repo-local directory.
- Path note: in the repo root, commands use `skill/scripts/...`; if you mount `skill/` into an OpenClaw workspace as a skill directory, the same files appear as `scripts/...`.

## Future Published Install Path

These are target-state distribution paths, not current guarantees:

- published ClawHub skill
- published OpenClaw plugin / bundle
- custom Control UI / companion browser module

Until those ship, the supported path is the repo-local script flow documented above.

## Supported Platform Matrix

| Platform | Current ClawChain recommendation | Notes |
|---|---|---|
| macOS | OpenClaw Gateway + stock Control UI/WebChat/TUI + repo-local ClawChain scripts | OpenClaw has a native menu bar app on macOS, but ClawChain-specific companion UX still needs custom work |
| Linux | OpenClaw Gateway + stock Control UI/TUI + repo-local ClawChain scripts | Official OpenClaw Gateway is fully supported; native Linux companion apps are still planned upstream |
| WSL2 | Same as Linux | Preferred over native Windows for the full Gateway/tooling path |
| Native Windows | Not the recommended primary path for this repo today | Use WSL2 unless you have a specific reason not to |

## Requirements

- Python 3.10+
- `requests`
- `cryptography` recommended for encrypted wallet storage
- A reachable ClawChain mining-service endpoint
- Optional: Codex CLI if you want `forecast_mode=codex_v1`

No local ClawChain testnet node is required for the current forecast-first miner path.

## Wallet And Local State

Current `setup.py` behavior:

- generates or loads a local secp256k1 private key
- stores the wallet by default at `~/.clawchain/wallet.json`
- registers the miner against the mining service
- writes back runtime config such as `miner_address` and `forecast_mode`

Important boundaries:

- This is **not** a BIP-39 mnemonic / seed-phrase wallet flow today.
- Do not document or depend on `claw wallet ...` commands; those do not currently exist in this repo.

## State Ownership

| State category | Current authority | Notes |
|---|---|---|
| miner / task / reward / settlement truth | `mining-service + Postgres` | Browser truth should come from the service |
| wallet / config / local log | local files under `~/.clawchain/` and repo skill config | Local helper state, not protocol authority |
| companion shell identity | not shipped yet | Do not assume session transcript or plugin cache is already the authority |

## Effective Runtime Config

Current effective fields in [`skill/scripts/config.json`](/Users/yanchengren/Documents/Projects/clawchain/skill/scripts/config.json):

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

Current default file:

```json
{
  "rpc_url": "http://127.0.0.1:1317",
  "wallet_path": "~/.clawchain/wallet.json",
  "forecast_mode": "codex_v1"
}
```

`forecast_mode` is the active miner-mode switch. The old `solver_mode` language is stale.

## Current Runtime Flow

Today the active miner path is:

1. `python3 skill/scripts/setup.py`
2. `python3 skill/scripts/mine.py`
3. `python3 skill/scripts/status.py`

Under the hood:

- the mining service publishes active tasks
- the local miner loop prioritizes `daily_anchor`
- then processes capped `forecast_15m` tasks
- the client performs commit/reveal
- settlement, reward windows, and anchor progression stay service-side

This is a **service-led forecast-first** runtime. It is not the old challenge/PoA miner.

## Optional Forecast Modes

### `heuristic_v1`

- default low-dependency forecast path
- does not require Codex CLI

### `codex_v1`

- uses the local Codex CLI path
- requires the configured `codex` binary and model
- usually benefits from a larger commit safety window

If you do not need model-assisted forecasting, prefer `heuristic_v1`.

## Current Status Surfaces

Current runnable status entry points are:

- `python3 skill/scripts/status.py`
- repo website read surfaces:
  - `/dashboard`
  - `/network`
  - `/risk` (operator-oriented, not miner-primary)

Current stock OpenClaw host surfaces are:

- TUI
- Control UI / WebChat
- macOS menu bar status on macOS

Those host surfaces do **not** mean that `Companion Home`, `Activities`, or `History` already exist as finished ClawChain UI.

## Known Gaps

- No durable companion state store yet
- No shipped `Companion Home / Activities / History` surface yet
- Current `daily_anchor` path still has an idempotency gap on repeated already-submitted / already-revealed responses; do not describe the current loop as a fully hardened always-on companion daemon until that gap is closed
- `arena_multiplier` is read-only from the miner client perspective
- Poker MTT is still operator-gated and should not be described here as a default public miner activity

## Verification

Useful checks:

```bash
openclaw gateway status
python3 skill/scripts/doctor.py
python3 skill/scripts/status.py --json
```

`doctor.py` is a pre-flight helper. It is useful for connectivity/runtime checks, but it is not an authority for companion command availability or browser IA truth.

If the service is running and the miner is registered, `status.py` should return a service-backed status envelope plus recent local mining records.

## Related Documents

- [`docs/IMPLEMENTATION_STATUS_2026_04_10.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/IMPLEMENTATION_STATUS_2026_04_10.md)
- [`docs/PRODUCT_SPEC.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/PRODUCT_SPEC.md)
- [`docs/MINING_DESIGN.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)
- [`docs/superpowers/specs/2026-04-10-companion-miner-product-layer-design.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/superpowers/specs/2026-04-10-companion-miner-product-layer-design.md)
