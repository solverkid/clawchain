# Poker MTT Payout-Grade Ranking Spec

**日期**: 2026-04-19
**状态**: Implementation spec for payout-grade unique ranking
**适用范围**: ClawChain `poker mtt` final ranking, reward projection, reward windows, settlement anchoring
**参考代码**: `lepoker-gameserver`, `lepoker-auth`, current ClawChain `pokermtt/ranking` and `mining-service`

---

## 1. Executive Summary

The current donor-compatible ranking path is good enough to prove that a 30-player local MTT can finish, but it is not yet payout-grade.

The reason is precise: donor MTT ranking can produce tied display placements for eliminated players. That is valid for UI and donor parity, but it is unsafe as the direct reward rank because `poker_mtt_result_entries.final_rank`, reward-window rows, settlement roots, and future reputation deltas need a single unique ordering.

ClawChain therefore uses this contract:

- `rank`: payout-grade final rank. It is unique, contiguous, and reward-bearing only when `rank_state = ranked`.
- `display_rank`: donor-compatible standing rank. It may tie and may skip numbers.
- `source_rank`: raw donor internal rank from Redis died JSON or live zset-derived rank evidence.
- `rank_basis` / `rank_tiebreaker`: explicit evidence of why a row received that unique payout rank.

Live ranking is never a payout input. It is a player-facing and operator-facing read model only. Payout consumes a locked final-ranking artifact after stable snapshot, registration/waitlist merge, evidence readiness, hidden eval readiness, identity checks, and projection validation.

---

## 2. Evidence Base

This spec is based on:

- GitNexus repo contexts for `clawchain`, `lepoker-gameserver`, and `lepoker-auth`.
- GitNexus symbol context:
  - `lepoker-gameserver` `calculateMTTRanking`
  - `lepoker-gameserver` `getMTTRanking`
  - `lepoker-auth` `RankingService.getMttRankingFromRedis`
  - `lepoker-auth` `MttService.saveMTTRankingInfo`
- Six read-only subagent reviews of donor runtime ranking, auth ranking persistence, MQ/hand-history evidence, payout-grade policy, current ClawChain code, and spec/test gaps.
- Current clean 30-player donor-real local run at `artifacts/poker-mtt/deep-real-auth-20260419T091505Z`.

The local 30-player run finished with:

- `alive=1`
- `died=29`
- `pending=0`
- `standings_count=30`
- all 30 players received `currentMTTRanking`

But the same run also showed duplicate donor display ranks in the completed standings. That means finish completeness passed, while payout-grade rank uniqueness still needed a separate contract.

---

## 3. Donor Ranking Model

### 3.1 Redis Keys

`lepoker-gameserver` writes MTT ranking to Redis:

- `rankingNotDiedScore:%s:%s`
  - sorted set
  - member: `userID:entryNumber`
  - score: current `EndChip`
- `rankingUserInfo:%s:%s`
  - hash
  - field: `userID:entryNumber`
  - value: live snapshot or died snapshot JSON
- `rankingUserDiedInfo:%s:%s`
  - list
  - value: died JSON with donor internal `rank`
  - inserted with `LPush`, so the list head is the best/latest eliminated row

`lepoker-auth` reads the same keys in `RankingService.getMttRankingFromRedis()` and later persists the final JSON in `mtt_ranking.ranking_info`.

### 3.2 Live Ranking

`lepoker-gameserver.getMTTRanking()` returns the current player's live rank using Redis `ZRevRank` on `rankingNotDiedScore`.

Important caveats:

- Redis `ZRevRank` is zero-based.
- Equal chip stacks are tie-broken by Redis/member ordering, not tournament elimination evidence.
- The live rank only covers survivors in the zset.
- It is asynchronous relative to hand settlement and stand-up processing.

ClawChain policy:

- Live ranking may be displayed or logged.
- Live ranking may be used for recovery and health checks.
- Live ranking must not enter reward projection or settlement.

### 3.3 Donor Final Ranking

`lepoker-gameserver.calculateMTTRanking()` buffers death events, sorts by:

1. `DiedTime ASC`
2. `StartChip ASC`

The donor tie definition is:

```text
DiedTime equal AND StartChip equal => same donor internal rank
```

Then `noticeDiedRank()` walks the died list from best/latest to worst/earliest and converts donor internal rank groups into user-facing placements after the current alive count.

This preserves real donor semantics, but it can produce tied display ranks. `lepoker-auth` then trusts that donor rank grouping and persists it. `MttService.saveMTTRankingInfo()` pays winners by `rank <= prizePoolSize`, which can include multiple players at a tied boundary. That is acceptable for donor's own product rules, but not safe for ClawChain settlement roots unless the tie policy is explicit.

---

## 4. ClawChain Rank Types

| Field | Meaning | Ties Allowed | Reward Input |
|---|---|---:|---:|
| `rank` | Payout-grade final rank | No | Yes |
| `display_rank` | Donor-compatible standing rank | Yes | No |
| `source_rank` | Raw donor internal rank text | Yes | No |
| `source_rank_numeric` | Whether `source_rank` parsed as a number | N/A | No |
| `rank_state` | Whether row is rewardable, waiting/no-show, duplicate, unresolved, or voided | N/A | Gate only |
| `rank_basis` | Evidence class used for rank | N/A | Audit |
| `rank_tiebreaker` | Deterministic tie-break policy used | N/A | Audit |

The `rank` field is intentionally reused as payout rank because existing reward projection already uses `rank` -> `final_rank`. Donor/display parity moves to `display_rank` and `source_rank`.

---

## 5. Unique Ranking Policy

### 5.1 Current Product Scope

ClawChain Poker MTT v1 has no re-entry and no re-join reward semantics.

The canonical entry identity is still shaped like donor:

```text
member_id = source_user_id + ":1"
entry_number = 1
reentry_count = 1
```

If a donor snapshot still contains duplicate entries for one economic unit, finalizer archives the non-canonical rows as `duplicate_entry_collapsed` and removes their payout rank.

### 5.2 Survivors

Survivors always outrank eliminated players.

Natural finish should have exactly one survivor:

```text
survivor rank = 1
```

If a future time-cap or operator-ended tournament has multiple survivors, survivor order is:

```text
final chip DESC
member_id ASC deterministic fallback
```

Equal chip survivors still receive unique payout ranks. The equality is recorded in `rank_tiebreaker`, not expressed as duplicate payout rank.

### 5.3 Eliminated Players

Eliminated players keep donor display semantics but receive unique payout ranks.

Primary group order:

```text
donor display rank ASC
```

Within a tied donor display group:

```text
start_chip DESC
member_id ASC
```

This maps donor's same-hand/same-time intuition into payout-grade order:

- later/better donor display group ranks better
- if donor says two bustouts are tied, higher start-of-hand chip ranks better
- if start chips are also equal, deterministic member order breaks the tie

The `display_rank` remains tied so audits can see the donor group that created the edge case.

### 5.4 Unresolved, Waiting, No-Show, Voided, Duplicate Rows

Rows with these states do not consume payout rank:

- `waiting_no_show`
- `unresolved_snapshot`
- `duplicate_entry_collapsed`
- `voided`

They may stay in the final archive for evidence completeness, but reward projection must not treat them as payout candidates.

### 5.5 Timeout, Fold, Disconnect, Kick

These are behavior/evidence events, not direct ranking events.

- Fold with chips remaining: no rank change.
- Timeout auto-check/fold with chips remaining: no rank change.
- Repeated timeout causing away/kick: rank changes only if it creates a real elimination or disqualification event.
- Disconnect/reconnect: no rank change unless it leads to timeout or operator intervention.
- Operator disqualification: archive row with unique placement only if required for audit, but `rank_state` must be non-rewardable unless a separate policy allows payout.

---

## 6. Required Invariants

Payout-grade finalization must enforce:

1. Every `rank_state = ranked` row has a non-null `rank`.
2. Ranked rows have ranks exactly equal to `1..N`, where `N` is the count of ranked rows after duplicate economic-unit collapse.
3. No two ranked rows share the same `rank`.
4. Non-ranked rows do not carry payout rank.
5. `display_rank` may tie but is never used in scoring.
6. `rank` must be one-based.
7. A final-ranking projection request with duplicate or non-contiguous payout ranks is rejected before saving/projecting.
8. Persisted final-ranking rows are revalidated before reward projection, even if they bypassed the API schema.
9. Reward windows only consume projected results that came from valid ranked final rows.
10. Settlement anchors only consume locked/anchorable reward windows.

---

## 7. Edge-Case Matrix

| ID | Scenario | Expected ClawChain Behavior |
|---|---|---|
| R01 | Normal heads-up finish | One survivor rank `1`, one eliminated rank `2` |
| R02 | 30 players finish, donor display ranks tie | `rank` unique `1..30`, `display_rank` may duplicate |
| R03 | Equal alive chips in live zset | Unique live display order for UI; not payout input |
| R04 | Equal alive chips at time-cap finish | Unique payout rank by chip/member fallback, tiebreaker recorded |
| R05 | Same-hand busts with different start chips | Higher `start_chip` receives better payout rank inside donor display group |
| R06 | Same-hand busts with equal start chips | Unique payout rank by deterministic member fallback |
| R07 | Same second busts from different tables | Donor display may tie; payout rank unique by group policy |
| R08 | Died list has duplicate entrant | Keep canonical row, mark duplicate non-rewardable |
| R09 | Alive zset and died list both contain same member | Canonical ranked row only; stale duplicate ignored or collapsed |
| R10 | Snapshot exists but player absent from alive/died | Archive as pending/unresolved or waiting/no-show; no payout rank |
| R11 | Registered but never joined | Archive as `waiting_no_show`; no payout rank |
| R12 | Waiting user absent from runtime Redis | Registration source adds archive row; no payout rank |
| R13 | Died entry rank is non-numeric | `unresolved_snapshot`; no payout rank |
| R14 | Died entry missing snapshot | Recover member identity from died JSON; mark degraded snapshot evidence |
| R15 | `miner_address` missing | Ranking archive may exist; payout projection rejects missing miner |
| R16 | `economic_unit_id` duplicate | One canonical row stays ranked; others become `duplicate_entry_collapsed` |
| R17 | `field_size` smaller than ranked rows | Projection rejects inconsistent payload |
| R18 | `field_size` larger than final rows with missing entrants | Finalizer barrier rejects when expected count configured |
| R19 | Timeout no-action but player survives | Behavior evidence only; rank unchanged |
| R20 | Timeout leads to auto-fold and bust | Rank by resulting elimination, not timeout timestamp alone |
| R21 | Player all-in with zero stack mid-hand | Still alive until hand settlement/stand-up processing |
| R22 | Final winner donor stand-up uses `now + 2` | ClawChain assigns winner from survivor state, not donor timestamp hack |
| R23 | Same projection id/root replay | Idempotent no-op |
| R24 | Same projection id with changed root | Conflict |
| R25 | Persisted DB rows contain duplicate ranks | Service projection rejects before creating results |
| R26 | API payload contains duplicate ranks | FastAPI schema rejects before save |
| R27 | API payload skips a rank | FastAPI schema rejects before save |
| R28 | Non-ranked row carries `rank` | Schema/service rejects or strips before projection |
| R29 | Public ELO differs from final order | Final rank unchanged |
| R30 | Hand history unavailable | Ranking may archive, but evidence state blocks reward eligibility |
| R31 | Hidden eval missing | Result projection creates audit-only row; no multiplier/reward lock |
| R32 | Local synthetic auth identity | Can play local harness; reward projection/window rejects |
| R33 | Re-entry appears despite v1 no-reentry policy | Collapse by economic unit and mark non-canonical entries non-rewardable |
| R34 | Same display-rank tie crosses paid boundary | Unique payout rank decides window order; display tie is audit-only |
| R35 | Late correction changes final ordering | Append/supersede correction path; never mutate anchored root silently |

---

## 8. Implementation Contract

### 8.1 Go Finalizer

The Go finalizer must:

- Decode donor Redis live/died/user snapshots.
- Merge registration/waitlist/no-show rows.
- Build donor-compatible `display_rank`.
- Build unique payout `rank`.
- Collapse duplicate economic units before validation.
- Remove payout rank from non-ranked rows.
- Validate rank uniqueness and contiguity.
- Include `display_rank`, `rank_basis`, and `rank_tiebreaker` in canonical rows and projector payloads.

### 8.2 Redis Standings Helper

`scripts/poker_mtt/complete_standings.py` must:

- Preserve donor `display_rank`.
- Add unique payout `rank` for alive/died rows.
- Leave pending rows with null payout rank.
- Emit enough metadata to diagnose ties: `died_rank_internal`, `start_chip`, `zset_score`.

### 8.3 Mining-Service API

`ApplyPokerMTTFinalRankingProjectionRequest` must fail closed:

- duplicate ranked payout ranks -> reject
- skipped payout ranks -> reject
- ranked row without rank -> reject
- non-ranked row with payout rank -> reject
- `field_size < ranked_count` -> reject

### 8.4 Mining-Service Projection

`ForecastMiningService.project_poker_mtt_final_rankings()` must revalidate persisted rows after canonical economic-unit collapse, because rows can enter through repository methods, migrations, or admin tooling.

This protects the actual reward path even if the API validation is bypassed.

---

## 9. Test Requirements

Required tests:

- Go finalizer assigns unique payout ranks for tied donor died display group.
- Go finalizer preserves tied `display_rank` while making `rank` unique.
- Go finalizer removes payout rank from unresolved, waiting/no-show, and duplicate-collapsed rows.
- Go finalizer rejects non-contiguous ranked rows at the barrier.
- Python Redis standings helper emits duplicate `display_rank` but unique `rank`.
- FastAPI/Pydantic projection request rejects duplicate payout ranks.
- FastAPI/Pydantic projection request rejects non-contiguous payout ranks.
- Forecast service rejects persisted duplicate ranks before result projection.
- Existing cross-language Go -> Python fixture includes rank evidence fields.
- Phase 3 20k reward-window path asserts unique final ranks before window selection.

---

## 10. Answer To Current Ranking Question

Current final ranking is complete enough to prove the donor runtime finished. It is not yet correct enough for rewards because donor display ranks can tie.

Current real-time ranking is processed correctly for its donor purpose: survivor UI ranking via Redis zset. It is not a payout source and should not be made one.

The fix is not to remove donor semantics. The fix is to separate them:

- preserve donor display ranks for audit and replay
- assign ClawChain payout ranks uniquely and contiguously
- enforce this invariant in both the finalizer and the reward projection service

