# Poker MTT Reward Rollout Release Review

## Purpose

Phase 3 closeout only proves local/staging production readiness. Reward-bearing rollout still requires a separate release review that binds:

- heavy-gate evidence artifacts
- same-run release pack evidence
- budget / emission / operator metadata
- chain submitter and rollback ownership

This file is the operator checklist for that review.

## Required Inputs

Heavy-gate artifacts under `artifacts/poker-mtt/phase3/`:

- `db-load-20k.log`
- `non-mock-30-finish-summary.json`
- `local-run-log-check.json`
- `settlement-anchor-query-receipt.json`

Release pack:

- `artifacts/poker-mtt/release-review/phase3-release-pack.json` for the canonical local proof, or another operator-approved pack with `phase3_release_pack_complete=true`

Rollout metadata:

- `budget_source_id`
- `emission_epoch_id`
- `epoch_cap`
- `settlement_operator_role`
- `chain_submitter`
- `fallback_tx_policy`
- `donor_runtime_version`
- `admin_auth_mode`
- `reward_bound_identity_authority`
- `monitoring_evidence_ref`
- `rollback_runbook_ref`

Recommended checked-in templates:

- [`docs/examples/poker_mtt_release_review_metadata.example.json`](/Users/yanchengren/Documents/Projects/clawchain/docs/examples/poker_mtt_release_review_metadata.example.json)
- [`docs/examples/poker_mtt_release_review_signoffs.example.json`](/Users/yanchengren/Documents/Projects/clawchain/docs/examples/poker_mtt_release_review_signoffs.example.json)
- [`docs/runbooks/poker-mtt-rollout-rollback.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/runbooks/poker-mtt-rollout-rollback.md)

## Canonical Local Materialization

When this checkout already has a donor-backed finish sample plus `db-load-20k.log`, use the canonical local materializer first:

```bash
make materialize-poker-mtt-phase3-release-artifacts
```

That command writes or refreshes:

- `artifacts/poker-mtt/phase3/non-mock-30-finish-summary.json`
- `artifacts/poker-mtt/phase3/local-run-log-check.json`
- `artifacts/poker-mtt/phase3/settlement-anchor-query-receipt.json`
- `artifacts/poker-mtt/release-review/phase3-runtime-evidence.json`
- `artifacts/poker-mtt/release-review/phase3-release-evidence.json`
- `artifacts/poker-mtt/release-review/phase3-release-pack.json`
- `artifacts/poker-mtt/release-review/release-review-bundle.json`
- `artifacts/poker-mtt/release-review/source-paths.json`

By default it also writes local-proof rollout metadata:

- `artifacts/poker-mtt/release-review/phase3-release-review-metadata.local.json`
- `artifacts/poker-mtt/release-review/phase3-release-review-signoffs.local.json`

Those local-proof metadata files are for reproducible closeout inside this checkout. Replace them with operator-approved metadata/signoffs before any real reward-bearing rollout.

## Standard Command

```bash
make build-poker-mtt-release-review-bundle \
  POKER_MTT_RELEASE_PACK=artifacts/poker-mtt/release-review/phase3-release-pack.json \
  POKER_MTT_BUDGET_SOURCE_ID=budget-2026-04 \
  POKER_MTT_EMISSION_EPOCH_ID=epoch-2026w17 \
  POKER_MTT_EMISSION_EPOCH_CAP=5000 \
  POKER_MTT_SETTLEMENT_OPERATOR_ROLE=ops-poker-mtt \
  POKER_MTT_CHAIN_SUBMITTER=claw1submitterxyz \
  POKER_MTT_FALLBACK_TX_POLICY=typed_msg_only \
  POKER_MTT_DONOR_RUNTIME_VERSION=lepoker-gameserver-dev-sha \
  POKER_MTT_ADMIN_AUTH_MODE=internal-bearer \
  POKER_MTT_REWARD_IDENTITY_AUTHORITY=clawchain_miner_binding_v1 \
  POKER_MTT_MONITORING_EVIDENCE_REF=grafana:poker-mtt-rollout-2026-04-20 \
  POKER_MTT_ROLLBACK_RUNBOOK_REF=docs/runbooks/poker-mtt-rollout-rollback.md
```

Output:

- `artifacts/poker-mtt/release-review/release-review-bundle.json`

File-based review inputs are also supported:

```bash
make build-poker-mtt-release-review-bundle \
  POKER_MTT_RELEASE_PACK=artifacts/poker-mtt/release-review/phase3-release-pack.json \
  POKER_MTT_RELEASE_METADATA_JSON=docs/examples/poker_mtt_release_review_metadata.example.json \
  POKER_MTT_RELEASE_SIGNOFFS_JSON=docs/examples/poker_mtt_release_review_signoffs.example.json
```

## Bundle Contract

The generated bundle is complete only when all of the following are true:

- `heavy_artifacts_present=true`
- `runtime_finish_complete=true`
- `log_check_clean=true`
- `settlement_query_complete=true`
- `release_pack_complete=true`
- `rollout_metadata_complete=true`
- `release_review_bundle_complete=true`

## What The Bundle Proves

- 20k reward-window load evidence exists and is attached
- 30-player donor-backed play-to-finish evidence exists and reached terminal standings
- donor local logs stayed clean enough for rollout review
- settlement anchor query receipt contains the expected chain-visible roots/metadata
- same-run runtime/MQ/projector release pack is attached and complete
- budget, operator, chain submitter, monitoring, and rollback ownership are explicit

## What It Does Not Prove

This bundle does not approve:

- high-value mainnet rollout by itself
- `x/reputation` write enablement
- new multiplier formulas or policy changes
- donor runtime version changes without rerunning heavy-gate evidence

Any of those reopen release review.
