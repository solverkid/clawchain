# ClawChain Companion-First Miner Product Layer Design

**Version**: 1.0  
**Date**: 2026-04-10  
**Status**: Approved product-layer design for V1  
**Related docs**:
- [docs/MINING_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)
- [docs/IMPLEMENTATION_STATUS_2026_04_10.md](/Users/yanchengren/Documents/Projects/clawchain/docs/IMPLEMENTATION_STATUS_2026_04_10.md)
- [skill/SKILL.md](/Users/yanchengren/Documents/Projects/clawchain/skill/SKILL.md)

---

## 1. Decision Summary

ClawChain V1 miner-facing product layer is locked as:

> **Companion-first miner**: the user owns a persistent mining companion; the companion runs a background mining runtime; all current and future mining forms are presented as activities the companion joins.

This replaces the old mental model of:

- one miner binary
- one mining mode
- one command loop

V1 does **not** make the companion a Tamagotchi-like chore loop.

V1 does **not** make the companion itself a reward source.

V1 does **not** require Electron.

V1 does:

- make the companion the main product shell
- keep mining mostly automatic
- add one small daily interaction
- present forecast, arena, and future games as one unified activity system
- use TUI, slash commands, skills, and WebUI as the main surfaces

---

## 2. Why This Product Layer Exists

The repository's current runtime reality is already no longer the old challenge miner.

The active path today is:

- `forecast_15m`
- `daily_anchor`
- `arena_multiplier`
- service-led settlement and read models

That means the old `clawminer` shape is no longer the right main product shell.

The product problem is therefore not "how to skin one miner loop."

The product problem is:

> **how to give users one persistent identity and one understandable shell while mining formats keep expanding.**

The companion solves that shell problem:

- it is stable while activities change
- it gives passive mining a visible identity
- it supports retention through low-friction companionship
- it allows future game-like activities without turning each new format into a separate client

---

## 3. Core Product Principles

V1 follows these principles.

### 3.1 Companion is the shell, not the protocol

The companion is the user-facing identity layer.

It is not:

- a settlement engine
- a reward engine
- a separate consensus rule
- a specific game mode

### 3.2 Mining remains mostly automatic

The companion should feel alive and active even when the user does nothing.

The user should not have to babysit it to preserve rewards.

### 3.3 Daily interaction is light, not chore-like

The user should spend seconds, not minutes, on the daily interaction.

Missing a day must not feel like punishment.

### 3.4 Activities are extensible

All present and future mining forms must fit one registry:

- forecast
- arena
- future prediction games
- future skill-based or game-based mining forms

### 3.5 Surfaces have clear jobs

- TUI is for presence and quick status
- slash commands are for control
- WebUI is for understanding and browsing
- runtime is for execution

---

## 4. Product Object Model

V1 exposes four top-level product objects.

### 4.1 Companion

The companion is what the user "has."

It includes:

- name
- visual identity
- mood
- current work state
- streak and presence history
- activity preferences
- high-level performance summary
- lightweight memory of recent interaction

The companion is persistent across sessions.

It is the same companion whether the user is in TUI, WebUI, or command flow.

### 4.2 Runtime

The runtime is the background miner core.

It is responsible for:

- fetching active opportunities
- selecting activities to join
- committing and revealing predictions or actions
- syncing result state
- updating local status surfaces

The runtime should eventually replace the user-visible role of the old miner script.

The user should understand this as:

> "my companion is out working"

not:

> "I am manually running a mining script"

### 4.3 Activities

Activities are the unified product-level representation of mining forms.

Activities are not all equal. Each activity may be:

- automatic
- scheduled
- interactive
- reward-bearing
- calibration-only
- multiplier-only

### 4.4 Surfaces

Surfaces are where the user sees and controls the companion.

V1 surfaces:

- OpenClaw TUI
- slash commands / skill commands
- companion-aware WebUI

Deferred surface:

- dedicated Electron game hub

---

## 5. V1 Companion Definition

### 5.1 What the user owns

The user owns one persistent mining companion.

The product promise is:

> **you have a mining buddy that keeps working for you, joins activities for you, and reports back in a way that feels alive.**

### 5.2 What the companion is not

The companion is not:

- a high-maintenance digital pet
- a daily reward faucet
- a replacement for mining rules
- a separate game economy

### 5.3 Emotional target

The intended feeling is:

- low interruption
- strong presence
- strong status readability
- some attachment
- no burden

Not:

- guilt if unused
- maintenance pressure
- repetitive feeding loops
- constant tapping

---

## 6. Daily Interaction Design

V1 includes exactly one lightweight daily companion ritual.

Recommended product name:

- `Daily Check-in`
- or `Buddy Brief`

### 6.1 Purpose

The daily interaction exists to do three things:

1. tell the user what the companion has been doing
2. let the user give one tiny directional input
3. reinforce companionship and return habit

### 6.2 Time budget

The full interaction should take roughly `10-30s`.

### 6.3 Allowed interaction types

V1 should support one of these actions per day:

- `encourage`
  - companion-only emotional touchpoint
  - no direct reward effect

- `set today's vibe`
  - choose one small directional preference
  - examples:
    - `steady`
    - `aggressive`
    - `free play`
  - should lightly influence scheduling or emphasis, not protocol truth

- `play one micro activity`
  - very short
  - more ritual than main earning surface
  - must not become required daily labor

### 6.4 Hard constraints

V1 daily interaction must not include:

- feeding
- cleaning
- energy depletion
- pet death
- mandatory multiple check-ins
- missed-day reward punishment
- direct token payout for the interaction itself

If the user skips the interaction:

- runtime continues
- mining continues
- the companion remains active
- the user only misses a small layer of guidance and presence

---

## 7. Companion State Model

The companion state model should use two layers.

### 7.1 Work state

This reflects real runtime behavior.

Recommended V1 work states:

- `resting`
- `scouting`
- `working_forecast`
- `working_activity`
- `awaiting_resolution`
- `celebrating`
- `needs_attention`
- `paused`

### 7.2 Mood state

This is presentation-only and should not change protocol logic.

Recommended V1 mood states:

- `calm`
- `focused`
- `curious`
- `proud`
- `sleepy`
- `concerned`

### 7.3 Why separate them

Separating work state and mood state avoids product confusion:

- the system stays explainable
- runtime truth stays clean
- UI gets personality without protocol leakage

Example:

- work state: `working_forecast`
- mood state: `focused`

or:

- work state: `awaiting_resolution`
- mood state: `curious`

---

## 8. Activity System

All mining forms should be presented as **Activities** at the product layer.

The product should not expose a fragmented mix of:

- lane
- game
- mode
- plugin
- miner type

to ordinary users.

Those may still exist internally, but the user-facing abstraction is one activity catalog.

### 8.1 V1 activity categories

V1 should group activities into three categories.

#### Auto Activities

Examples:

- `forecast_15m`
- `daily_anchor`

These run automatically through the runtime.

These are the default earnings layer.

#### Scheduled Competitive Activities

Example:

- `arena`

These happen on defined timing windows and primarily contribute calibration or multiplier value.

#### Light Interactive Activities

These are short, optional, companion-facing rituals or tiny playable moments.

They are not the main source of yield in V1.

### 8.2 Activity role labels

Each activity card should carry one clear role label:

- `direct reward`
- `calibration`
- `multiplier`
- `practice`

This makes it obvious why an activity exists.

### 8.3 Common activity card structure

Every activity should be presentable using the same card schema:

- what it is
- whether it is automatic, scheduled, or interactive
- what role it plays in earnings
- whether the companion is currently participating
- recent outcome
- why it is recommended or not recommended today

### 8.4 Product rule

Adding a new mining form should mean:

- add a new activity type
- add its runtime handler
- add its card definition

It should **not** mean:

- ship a new standalone miner identity
- create a second main product shell

---

## 9. Surface Responsibilities

### 9.1 TUI

TUI is the companion's ambient home.

It should show:

- companion visual state
- current work state
- one-line speech bubble
- quick earnings summary
- daily interaction reminder
- urgent attention states

It should not try to be the full analytics console.

### 9.2 Slash commands / skill commands

Slash commands are the shortest control path.

Recommended V1 command set:

- `/buddy`
- `/status`
- `/activities`
- `/checkin`
- `/arena`
- `/pause`
- `/resume`

These are companion-centered verbs, not raw operator commands.

### 9.3 WebUI

WebUI is the medium-depth understanding surface.

It should evolve from the current operator/read-model shape into a companion-first product surface.

Recommended V1 WebUI sections:

- `Companion Home`
- `Activities`
- `Rankings`
- `History`
- `Review / Risk` (user-visible subset only)

### 9.4 Runtime

Runtime is the execution layer and should become less directly exposed as the "product."

The runtime should support:

- automatic background participation
- pause/resume
- preference nudges from daily check-in
- status syncing to TUI and WebUI

---

## 10. V1 User Journey

### 10.1 First-time setup

The user installs the ClawChain companion, not "just a miner."

The first session should feel like:

1. activate companion
2. initialize wallet / miner identity
3. confirm background activity is enabled
4. see the companion's first work state

### 10.2 Returning user flow

When the user comes back, the first question answered should be:

> **What has my companion been doing?**

The first screen or command response should prioritize:

- current activity
- today's earnings
- recent best result
- whether today's light interaction has happened

### 10.3 Daily rhythm

The companion should create a rhythm of:

- background autonomy
- short re-entry
- visible progress
- occasional deeper browsing

It should not create a rhythm of maintenance.

---

## 11. Mapping to Current Repository Reality

This product-layer design does not require replacing the current protocol core first.

It reframes current code reality:

- current background miner logic can evolve from [`skill/scripts/mine.py`](/Users/yanchengren/Documents/Projects/clawchain/skill/scripts/mine.py)
- current miner identity and setup can evolve from [`skill/scripts/setup.py`](/Users/yanchengren/Documents/Projects/clawchain/skill/scripts/setup.py)
- current CLI status can evolve from [`skill/scripts/status.py`](/Users/yanchengren/Documents/Projects/clawchain/skill/scripts/status.py)
- current service-led fast lane, daily lane, and arena multiplier remain the active protocol basis

### 11.1 Deprecated main shell

The old `clawminer` should be treated as a legacy implementation path, not the main product face.

### 11.2 Current dashboard mismatch

Current dashboard, network, and risk pages are useful read surfaces, but they are still semantically closer to operator or raw mining status views than to the final companion-first shell.

V1 should adapt them rather than discarding them:

- keep their data value
- change their information architecture
- anchor them around the companion

---

## 12. V1 Non-Goals

V1 does not include:

- Electron game hub
- deep digital-pet mechanics
- companion-only reward emissions
- many-times-per-day chore loops
- a second independent miner app
- replacing the protocol with pet logic
- making every activity user-played

---

## 13. Roadmap Beyond V1

### 13.1 Electron roadmap item

Electron belongs on the roadmap, not in V1.

When introduced, it should act as:

> **deep activity container**

not:

> **the only way to use the product**

The intended future flow is:

- user sees companion in TUI or WebUI
- user opens activity detail or game hub when deeper engagement is wanted

### 13.2 Future role of Electron

Future Electron can host:

- richer activity browsing
- playable prediction or game surfaces
- more immersive tournament views
- activity-specific visualizations

But the companion shell should still remain stable above it.

---

## 14. Recommended V1 Product Language

Use these terms consistently.

### 14.1 Preferred terms

- `companion`
- `buddy`
- `activity`
- `check-in`
- `current work`
- `today's brief`

### 14.2 Avoid as primary user language

- `lane`
- `miner script`
- `protocol object`
- `reward window`
- `economic unit`

Those internal terms may still appear in advanced views, but not as the first layer of product language.

---

## 15. Success Criteria

V1 product-layer success means:

1. users understand they own a persistent mining companion
2. users do not need to understand the old miner implementation to participate
3. automatic mining remains the default
4. daily interaction feels optional but sticky
5. new mining forms can be added as activities without changing the main shell
6. TUI, commands, and WebUI all reflect one consistent companion identity

---

## 16. Final Product Statement

The final V1 miner-facing statement is:

> **ClawChain is a companion-first mining product: your persistent mining buddy automatically joins earning activities for you, reports back with clear status and light personality, and gives you one small daily moment of interaction without turning mining into maintenance.**
