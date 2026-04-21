# Poker MTT Reward Rollout Rollback Runbook

## Scope

This runbook covers rollback for the reward-bearing Poker MTT rollout after Phase 3 evidence is assembled and before or during reward emission.

Use it when any of these are true:

- donor-backed runtime evidence drifts from the approved release pack
- local run log checks show Tencent IM calls, RocketMQ publish failures, or operation-channel overflow
- reward window roots, settlement roots, or chain confirmation receipts mismatch the approved artifact set
- operator metadata, budget source, or submitter ownership is wrong for the current epoch

## Immediate Actions

1. Stop new reward-bearing rollout activity.
2. Freeze the approved artifact set under `artifacts/poker-mtt/phase3/` and `artifacts/poker-mtt/release-review/`.
3. Record the affected IDs:
   - `runtime_tournament_id`
   - `reward_window_id`
   - `settlement_batch_id`
   - `anchor_job_id`
   - `payload_hash`
4. Do not regenerate rankings or reward rows from ad hoc inputs.

## Disable Paths

1. Disable Poker MTT reward-window creation in the active mining-service config.
2. Disable settlement anchoring for the affected rollout window.
3. Stop any operator job that would submit or re-submit the same settlement batch.
4. Keep read-only inspection paths available.

## Triage Matrix

### Case 1: Runtime Or Log Safety Failure

- Treat the release pack as invalid.
- Do not emit rewards from that pack.
- Preserve:
  - `non-mock-30-finish-summary.json`
  - `local-run-log-check.json`
  - `phase3-release-pack.json`
- Re-run donor-backed validation only after the root cause is fixed.

### Case 2: Reward Window Or Settlement Root Drift

- Do not mutate the approved artifact files in place.
- Compare:
  - `final_ranking_root`
  - `reward_window_ids_root`
  - `task_run_ids_root`
  - `miner_reward_rows_root`
  - `canonical_root`
  - `anchor_payload_hash`
- If any approved root differs from the recomputed root, mark the rollout failed and rebuild a new release pack from the same canonical ranking source or from a new approved runtime sample.

### Case 3: Batch Submitted But Not Chain-Confirmed

- Do not create a second batch with different roots.
- Inspect the existing `anchor_job_id` and confirmation receipt first.
- If chain state is still pending, keep the batch frozen and continue confirmation checks.
- If chain state is invalid or mismatched, mark the anchor job failed and create a fresh batch only after operator signoff.

### Case 4: Metadata Or Ownership Error

- Invalidate the release review bundle.
- Regenerate `metadata.json` and the release review bundle.
- Do not rely on the old `payload_hash`.

## Recovery Path

1. Rebuild the evidence that failed.
2. Recreate the canonical release pack.
3. Re-run `build_release_review_bundle.py`.
4. Re-approve budget source, submitter, monitoring, and rollback ownership.
5. Only then re-enable reward-bearing rollout.

## Required Evidence For Re-Enable

- clean `local-run-log-check.json`
- valid `settlement-anchor-query-receipt.json`
- `phase3-release-pack.json` with `phase3_release_pack_complete=true`
- release review bundle with `release_review_bundle_complete=true`

## Notes

- Do not use donor reference repositories as runtime dependencies in rollback.
- Do not manually edit approved roots inside artifact JSON.
- Prefer fail-closed. If the artifact chain is ambiguous, keep rewards disabled.
