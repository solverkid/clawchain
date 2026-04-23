# Companion-First Miner V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a durable V1 IA split: ClawChain miner client owns `Companion Home / Activities / History / Network`, operator console owns risk and settlement tooling, and stock OpenClaw surfaces host the shell.

**Architecture:** Keep the current forecast-first mining core, but stop pretending the companion shell already exists. First align docs and implementation to the real service-led miner loop, then add companion-facing read models above that truth. Browser surfaces in `website/` are repo-local reference implementations; they are not stock OpenClaw itself.

**Tech Stack:** Python (`FastAPI`, existing mining-service), Python CLI scripts in `skill/`, Next.js app-router UI in `website/`, Node `node:test` for website view-model tests, `pytest` for new Python tests.

## Authority Inputs

- Stock OpenClaw capability boundary: official OpenClaw docs and latest release only
- Product truth: `docs/PRODUCT_SPEC.md`
- Protocol truth: `docs/MINING_DESIGN.md`
- Current runtime truth: `docs/IMPLEMENTATION_STATUS_2026_04_10.md`

## Runtime Truth Check

Current truth before any companion-shell work:

- `forecast_15m` is the only full public reward-bearing lane
- `daily_anchor` is calibration-only scaffolding
- `arena_multiplier` is a read-only shared-state modifier
- current miner entry path is `setup.py -> mine.py -> status.py`
- there is no durable companion state store yet
- there is no shipped `Companion Home / Activities / History`
- `/risk` is operator-oriented and should not stay in miner primary navigation
- stock OpenClaw `/status` is not the same contract as a future ClawChain companion home command

## Known Gaps / Launch Restrictions

- `daily_anchor` still has an idempotency gap on repeated already-committed / already-revealed paths; until that is fixed or explicitly quarantined, do not describe the current loop as a fully hardened always-on companion daemon
- companion state source of truth is still target-state, not current-state
- deterministic `/pause` / `/resume` / `/brief` control must not be documented as shipped before command registration and routing exist

## Architecture Decision: Companion State Source Of Truth

- **Current truth:** `mining-service` owns miner, reward, settlement, and read-model truth today. `skill/` owns wallet/config/local log only.
- **Target-state source of truth:** if companion persistence is introduced, `mining-service` should own cross-surface companion state.
- **Local cache:** `skill/` may keep a local cache for bootstrap, offline readability, and transient runtime updates before sync, but it cannot become the browser truth.
- **Guardrail:** do not let website pages read a local-only companion object. All browser miner surfaces must consume the service envelope.

## Companion Contract To Implement

### Durable service envelope

Prefer a stable service envelope with these sub-documents:

- `CompanionProfile`
- `CompanionPreferences`
- `CompanionRuntimeSnapshot`
- `CompanionDailyBrief`
- `CompanionActivityView[]`
- `CompanionEventLog[]`
- `CompanionSyncMeta`

The first V1 slice does not need every field fully populated, but it should not invent a second incompatible shape later.

### Surface ownership

- cross-platform default miner entry: `TUI -> commands -> Control UI / WebChat`
- macOS companion glance surface: `menu bar`
- browser miner IA: `Companion Home / Activities / History / Network`
- operator-only surfaces: `Risk / Abuse Review / Settlement Ops / Arena Ops`
- Linux / Windows native companion shell: out of scope for V1

### Command contract

Canonical target-state commands:

- `/buddy`
- `/brief`
- `/activities`
- `/why`
- `/history`
- `/pause`
- `/resume`
- `/settings`

Compatibility aliases:

- `/checkin -> /brief`
- `/wake -> /resume`
- `/status -> /buddy` only if ClawChain owns a non-conflicting command namespace

Transport rule:

- these are non-stock OpenClaw extension commands
- choose one transport before implementation: plugin command registration or skill command registration with `command-dispatch: tool`
- do not treat plain script entrypoints as equivalent to shipped Gateway commands

## Phase 0 / Prerequisite Gates

Before building more companion-shell surface area:

1. **Doc truth alignment**
   - rewrite `SETUP.md`
   - rewrite `skill/SKILL.md`
   - mark current-state vs target-state in `PRODUCT_SPEC.md` / `MINING_DESIGN.md`
2. **daily_anchor idempotency decision**
   - either fix the already-committed / already-revealed path
   - or mark it as a launch-blocking known gap
3. **IA split decision**
   - miner client vs operator console vs stock OpenClaw host surfaces must be explicit
4. **Command transport decision**
   - choose plugin command registration vs skill command + `command-dispatch: tool`
   - verify on gateway-backed TUI plus one browser host surface
5. **UI truth cleanup**
   - fix the current dashboard field-label mismatch before promoting `/dashboard` toward `Companion Home`

---

## File Structure

### Backend / runtime state

- Modify: `mining-service/models.py`
  - Add companion-facing status fields to existing miner/domain models without renaming protocol objects.
- Modify: `mining-service/forecast_engine.py`
  - Source current work state, latest activity summaries, and companion-derived status payloads from existing forecast/daily/arena flows.
- Modify: `mining-service/server.py`
  - Extend `/v1/miners/{address}/status` to return companion-facing envelope fields.
- Modify: `mining-service/schemas.py`
  - Add any response/request schema updates needed for the status envelope.
- Modify: `mining-service/repository.py`
  - Add repository methods for storing/loading companion metadata if the service owns persistence.
- Modify: `mining-service/pg_repository.py`
  - Implement the companion metadata persistence path for Postgres-backed deployments.
- Create: `mining-service/tests/test_companion_status.py`
  - API and view-model tests for the new status envelope.

### Skill / local companion runtime

- Modify: `skill/scripts/setup.py`
  - Initialize companion identity and local companion state during first-time setup.
- Modify: `skill/scripts/mine.py`
  - Read/write companion state while the runtime loops through forecast/daily/arena work.
- Modify: `skill/scripts/status.py`
  - Print companion-first status output (`current work`, `mood`, `daily brief`, `latest activity`) instead of raw miner-only framing.
- Modify: `skill/SKILL.md`
  - Update install/runtime/docs copy to current forecast-first, companion-first, OpenClaw install semantics.
- Create: `skill/tests/test_companion_state.py`
  - Verify local companion state creation/update semantics.
- Create: `skill/tests/test_status_cli.py`
  - Verify CLI output for companion-first terminology and missing-state behavior.

### Miner client browser prototypes + operator console split

- Modify: `website/src/lib/dashboard-data.js`
  - Turn the dashboard view-model into a companion-home view-model.
- Modify: `website/src/lib/dashboard-data.test.js`
  - Cover companion state, current activity, daily brief, and reward timeline mappings.
- Modify: `website/src/app/dashboard/page.tsx`
  - Reframe dashboard as `Companion Home`.
- Create: `website/src/lib/activities-data.js`
  - Build activities page view-model from existing API responses.
- Create: `website/src/lib/activities-data.test.js`
  - Test activity card classification and display logic.
- Create: `website/src/app/activities/page.tsx`
  - New activities catalog page.
- Create: `website/src/lib/history-data.js`
  - Build history page view-model from current reward timeline / latest artifacts.
- Create: `website/src/lib/history-data.test.js`
  - Test history grouping and fallback behavior.
- Create: `website/src/app/history/page.tsx`
  - New history page.
- Modify: `website/src/app/page.tsx`
  - Replace landing-page-first framing with companion-first entry copy and current install guidance.
- Modify: `website/src/app/layout.tsx`
  - Add top-level navigation for `Companion Home`, `Activities`, `History`, `Network`.
- Modify: `website/src/app/risk/page.tsx`
  - Move the risk queue out of miner-primary IA or relocate it under an operator namespace such as `/ops/risk`.
- Modify: `website/src/lib/risk-data.js`
  - Treat risk data as operator-console data, not miner-home data.

### Docs / integration cleanup

- Modify: `SETUP.md`
  - Replace challenge-era copy and hardcoded workspace assumptions with the current supported repo-local path plus official OpenClaw bootstrap guidance.
- Modify: `docs/PRODUCT_SPEC_EN.md`
  - Add deprecation / authority notes or fully align the English summary with the current forecast-first companion direction.
- Modify: `docs/PRODUCT_SPEC.md`
  - Split current runtime truth from target-state companion UX and remove fake current commands/surfaces.
- Modify: `docs/MINING_DESIGN.md`
  - Make public miner contract vs operator integration contract explicit.
- Modify: `docs/IMPLEMENTATION_STATUS_2026_04_10.md`
  - Mark it as current runtime truth and separate public miner path from operator integration paths.

### Boundaries

- Do **not** start in `/miner/cmd/clawminer`; treat the old Go miner as legacy.
- Do **not** build Electron in this plan.
- Do **not** rename protocol `lane` objects inside backend scoring logic; add companion/activity aliases at the surface boundary only.
- Do **not** keep `Risk` in miner-primary navigation.

---

### Task 1: Add Companion State To The Mining Service

**Files:**
- Modify: `mining-service/models.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/server.py`
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Test: `mining-service/tests/test_companion_status.py`

- [ ] **Step 1: Write the failing backend tests**

```python
def test_status_envelope_includes_companion_fields():
    payload = build_status_payload(...)
    assert payload["data"]["companion"]["name"] == "Buddy"
    assert payload["data"]["companion"]["current_work"] == "working_forecast"
    assert payload["data"]["companion"]["daily_brief_status"] in {"ready", "done", "missed"}
```

- [ ] **Step 2: Run the backend tests to verify they fail**

Run: `python -m pytest mining-service/tests/test_companion_status.py -q`
Expected: FAIL because `companion` fields and/or repository hooks do not exist yet.

- [ ] **Step 3: Add companion persistence and envelope mapping**

```python
companion = {
    "name": miner_state.get("companion_name") or "ClawBuddy",
    "mood": derive_mood(...),
    "current_work": derive_current_work(...),
    "current_activity": derive_current_activity(...),
    "daily_brief_status": derive_daily_brief_status(...),
}
```

- [ ] **Step 4: Re-run the backend tests**

Run: `python -m pytest mining-service/tests/test_companion_status.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mining-service/models.py mining-service/forecast_engine.py mining-service/server.py mining-service/schemas.py mining-service/repository.py mining-service/pg_repository.py mining-service/tests/test_companion_status.py
git commit -m "feat: add companion status envelope"
```

### Task 2: Make The Skill Runtime Own Local Companion State

**Files:**
- Modify: `skill/scripts/setup.py`
- Modify: `skill/scripts/mine.py`
- Modify: `skill/scripts/status.py`
- Create: `skill/tests/test_companion_state.py`
- Create: `skill/tests/test_status_cli.py`

- [ ] **Step 1: Write failing tests for companion state creation and CLI output**

```python
def test_setup_creates_companion_state_file(tmp_path):
    state = initialize_companion_state(tmp_path)
    assert state["name"]
    assert state["daily_brief_status"] == "ready"
    assert state["preferences"]["activity_policy"] == "balanced"
    assert state["preferences"]["daily_brief_reminder"] is True

def test_status_cli_prints_companion_fields(capsys):
    render_status(...)
    out = capsys.readouterr().out
    assert "Current work" in out
    assert "Buddy mood" in out
```

- [ ] **Step 2: Run the skill tests to verify they fail**

Run: `python -m pytest skill/tests/test_companion_state.py skill/tests/test_status_cli.py -q`
Expected: FAIL because the helper/state file/output fields do not exist yet.

- [ ] **Step 3: Implement local companion state management**

```python
state = {
    "name": generated_name,
    "mood": "calm",
    "current_work": "resting",
    "daily_brief_status": "ready",
    "preferences": {
        "activity_policy": "balanced",
        "max_cpu": 50,
        "daily_brief_reminder": True,
    },
}
```

Also add sync helpers so `setup.py` pushes the initial profile to the service and `mine.py` updates the authoritative service-side state after each loop iteration.

Use one explicit service write path for this sync, for example `POST /v1/miners/{address}/companion-state` or an equivalent dedicated update route, so there is no ambiguity about where companion state crosses from local cache into the backend source of truth.

- [ ] **Step 4: Re-run the skill tests**

Run: `python -m pytest skill/tests/test_companion_state.py skill/tests/test_status_cli.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skill/scripts/setup.py skill/scripts/mine.py skill/scripts/status.py skill/tests/test_companion_state.py skill/tests/test_status_cli.py
git commit -m "feat: persist local companion state"
```

### Task 3: Add Companion Command And TUI Entry Paths

**Files:**
- Modify: `skill/SKILL.md`
- Create: `skill/scripts/companion.py`
- Create: `skill/scripts/activities.py`
- Create: `skill/scripts/brief.py`
- Create: `skill/scripts/why.py`
- Create: `skill/scripts/history.py`
- Create: `skill/scripts/pause.py`
- Create: `skill/scripts/resume.py`
- Create: `skill/scripts/settings.py`
- Create: `skill/tests/test_command_scripts.py`

- [ ] **Step 1: Write failing tests for companion command scripts**

```python
def test_companion_command_renders_current_work(capsys):
    main(...)
    out = capsys.readouterr().out
    assert "Current work" in out

def test_brief_command_updates_daily_brief_status():
    result = run_brief(...)
    assert result["daily_brief_status"] == "done"
```

- [ ] **Step 2: Run the command-script tests to verify they fail**

Run: `python -m pytest skill/tests/test_command_scripts.py -q`
Expected: FAIL because the companion entry scripts do not exist yet.

- [ ] **Step 3: Implement companion command wrappers and wire the skill contract**

```python
# companion.py
if __name__ == "__main__":
    render_companion_home(...)
```

Update `skill/SKILL.md` so the documented entry points expose companion-centered verbs and note that deterministic control should later be routed through plugin/tool-dispatch if required at launch.
Do not mark them as real Gateway commands until the chosen transport is registered and tested.

Make the command ownership explicit in the skill contract:

- `/buddy` -> `skill/scripts/companion.py`
- `/activities` -> `skill/scripts/activities.py`
- `/brief` -> `skill/scripts/brief.py`
- `/why` -> `skill/scripts/why.py`
- `/history` -> `skill/scripts/history.py`
- `/pause` -> `skill/scripts/pause.py`
- `/resume` -> `skill/scripts/resume.py`
- `/settings` -> `skill/scripts/settings.py`

Compatibility aliases after registration rules are settled:

- `/checkin -> /brief`
- `/wake -> /resume`
- do not claim `/status -> /buddy` unless the stock OpenClaw `/status` conflict is resolved

- [ ] **Step 4: Re-run the command-script tests**

Run: `python -m pytest skill/tests/test_command_scripts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skill/SKILL.md skill/scripts/companion.py skill/scripts/activities.py skill/scripts/brief.py skill/scripts/why.py skill/scripts/history.py skill/scripts/pause.py skill/scripts/resume.py skill/scripts/settings.py skill/tests/test_command_scripts.py
git commit -m "feat: add companion command entrypoints"
```

### Task 4: Convert The Dashboard Into Companion Home

**Files:**
- Modify: `website/src/lib/dashboard-data.js`
- Modify: `website/src/lib/dashboard-data.test.js`
- Modify: `website/src/app/dashboard/page.tsx`
- Modify: `website/src/app/layout.tsx`

- [ ] **Step 1: Write the failing dashboard view-model assertions**

```javascript
test('buildDashboardViewModel exposes companion home sections', () => {
  const vm = buildDashboardViewModel({ minerStatusEnvelope, networkStatsResponse })
  assert.equal(vm.companion.name, 'ClawBuddy')
  assert.equal(vm.companion.currentWork, 'working_forecast')
  assert.equal(vm.dailyBrief.status, 'ready')
  assert.equal(vm.explanation.fast.baseline, '5400')
  assert.equal(vm.explanation.fast.prediction, '6100')
  assert.equal(vm.explanation.fast.outcome, '1')
  assert.equal(vm.timeline.latestArenaMultiplier, '1.012')
})
```

- [ ] **Step 2: Run the website dashboard test to verify it fails**

Run: `node --test website/src/lib/dashboard-data.test.js`
Expected: FAIL because the new companion fields are not part of the view-model yet.

- [ ] **Step 3: Implement companion-home mapping and page copy**

```javascript
return {
  companion: { name, mood, currentWork, currentActivity },
  dailyBrief: { status, reminder },
  explanation: { fast, daily, arena },
  rewards: [...],
  review: [...],
}
```

- [ ] **Step 4: Re-run the dashboard test**

Run: `node --test website/src/lib/dashboard-data.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add website/src/lib/dashboard-data.js website/src/lib/dashboard-data.test.js website/src/app/dashboard/page.tsx website/src/app/layout.tsx
git commit -m "feat: ship companion home dashboard"
```

### Task 5: Add Activities And History Surfaces

**Files:**
- Create: `website/src/lib/activities-data.js`
- Create: `website/src/lib/activities-data.test.js`
- Create: `website/src/app/activities/page.tsx`
- Create: `website/src/lib/history-data.js`
- Create: `website/src/lib/history-data.test.js`
- Create: `website/src/app/history/page.tsx`
- Modify: `website/src/app/page.tsx`

- [ ] **Step 1: Write failing tests for activities and history view-models**

```javascript
test('buildActivitiesViewModel classifies forecast/daily/arena roles', () => {
  const vm = buildActivitiesViewModel(sampleStatus)
  assert.equal(vm.cards[0].role, 'direct reward')
  assert.equal(vm.cards[1].role, 'calibration')
  assert.equal(vm.cards[2].role, 'multiplier')
})

test('buildHistoryViewModel keeps explanation and maturity fields visible', () => {
  const vm = buildHistoryViewModel(sampleStatus)
  assert.equal(vm.rows[0].baseline, '5400')
  assert.equal(vm.rows[0].prediction, '6100')
  assert.equal(vm.rows[0].maturityState, 'pending_resolution')
})
```

- [ ] **Step 2: Run the new website tests to verify they fail**

Run: `node --test website/src/lib/activities-data.test.js website/src/lib/history-data.test.js`
Expected: FAIL because the files and builders do not exist yet.

- [ ] **Step 3: Implement the new pages and builders**

```javascript
{
  title: 'Forecast Activity',
  mode: 'automatic',
  role: 'direct reward',
  status: 'active',
}
```

- [ ] **Step 4: Re-run the activities/history tests**

Run: `node --test website/src/lib/activities-data.test.js website/src/lib/history-data.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add website/src/lib/activities-data.js website/src/lib/activities-data.test.js website/src/app/activities/page.tsx website/src/lib/history-data.js website/src/lib/history-data.test.js website/src/app/history/page.tsx website/src/app/page.tsx
git commit -m "feat: add activities and history surfaces"
```

### Task 6: Update OpenClaw Integration Docs And Surface Contracts

**Files:**
- Modify: `skill/SKILL.md`
- Modify: `SETUP.md`
- Modify: `docs/PRODUCT_SPEC_EN.md`
- Modify: `docs/PRODUCT_SPEC.md`
- Modify: `docs/MINING_DESIGN.md`

- [ ] **Step 1: Write a docs checklist as the failing acceptance test**

```text
- install flow uses `openclaw onboard --install-daemon`
- install flow uses `openclaw skills install` or plugin install guidance
- docs say companion state is external to session transcript
- docs say Control UI / WebChat, not generic WebUI
- docs say deterministic commands require plugin/tool-dispatch
```

- [ ] **Step 2: Manually verify the checklist fails against the current docs**

Run: `rg -n "openclaw init|~/.openclaw/workspace/skills|WebUI|session transcript|command-dispatch" SETUP.md skill/SKILL.md docs/PRODUCT_SPEC_EN.md docs/PRODUCT_SPEC.md docs/MINING_DESIGN.md`
Expected: matches show outdated wording that must be removed or rewritten.

- [ ] **Step 3: Update install and surface contract docs**

```markdown
- Companion identity is persisted outside chat session history.
- Control UI / WebChat is the authenticated browser surface.
- Deterministic control verbs should use plugin commands or tool-dispatch.
```

- [ ] **Step 4: Re-run the docs grep check**

Run: `rg -n "openclaw init|~/.openclaw/workspace/skills|WebUI" SETUP.md skill/SKILL.md docs/PRODUCT_SPEC_EN.md`
Expected: no stale install/UI wording remains, or only intentional historical references remain.

- [ ] **Step 5: Commit**

```bash
git add skill/SKILL.md SETUP.md docs/PRODUCT_SPEC_EN.md docs/PRODUCT_SPEC.md docs/MINING_DESIGN.md
git commit -m "docs: align companion shell with openclaw surfaces"
```

---

## Verification Checklist

- `python -m pytest mining-service/tests/test_companion_status.py -q`
- `python -m pytest skill/tests/test_companion_state.py skill/tests/test_status_cli.py -q`
- `python -m pytest skill/tests/test_command_scripts.py -q`
- `node --test website/src/lib/dashboard-data.test.js website/src/lib/activities-data.test.js website/src/lib/history-data.test.js`
- Manual smoke:
  - run `python3 skill/scripts/setup.py`
  - run `python3 skill/scripts/mine.py`
  - run `python3 skill/scripts/status.py`
  - run `python3 skill/scripts/companion.py`
  - run `python3 skill/scripts/activities.py`
  - open the website dashboard and confirm it reads as `Companion Home`
  - open `/activities` and `/history` and confirm explanation fields remain visible

---

## Notes

- Keep protocol naming (`lane`, `baseline_q`, `reward_window`) inside backend/scoring internals.
- Translate to `activity`, `current work`, `daily brief`, and `buddy` only at the surface boundary.
- If V1 launch requires deterministic `/pause` and `/resume`, schedule a follow-up plugin task immediately after Task 5 instead of trying to fake it with plain skills.
- Verification for Task 3 must exercise the chosen command transport on gateway-backed surfaces, not only local script execution.
