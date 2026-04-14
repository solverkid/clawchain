const DEFAULT_API_BASE_URL = 'http://127.0.0.1:1317'

function normalizeApiBaseUrl(value) {
  const trimmed = String(value || '').trim()
  if (!trimmed) {
    return DEFAULT_API_BASE_URL
  }
  return trimmed.replace(/\/+$/, '')
}

function unwrapEnvelope(payload) {
  if (payload && typeof payload === 'object' && payload.data && typeof payload.data === 'object') {
    return payload.data
  }
  return payload || null
}

function formatMetric(value, fallback = '—') {
  if (value === null || value === undefined || value === '') {
    return fallback
  }
  return String(value)
}

function formatRatio(value, digits = 3) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—'
  }
  return value.toFixed(digits)
}

function buildLaneCard(title, source, rows, meta) {
  if (!source) {
    return null
  }
  return {
    title,
    meta,
    rows: rows
      .map(([label, value]) => ({ label, value: formatMetric(value) }))
      .filter((item) => item.value !== '—'),
  }
}

function buildDashboardViewModel({ minerStatusEnvelope, networkStatsResponse }) {
  const miner = unwrapEnvelope(minerStatusEnvelope)
  const score = (miner && miner.score_explanation) || {}
  const timeline = (miner && miner.reward_timeline) || {}
  const fast = score.latest_fast || null
  const daily = score.latest_daily || null
  const arena = score.latest_arena || null

  return {
    serverTime: (minerStatusEnvelope && minerStatusEnvelope.server_time) || null,
    summary: [
      { label: 'Public ELO', value: formatMetric(miner && miner.public_elo) },
      { label: 'Public rank', value: miner && miner.public_rank ? `#${miner.public_rank}` : '—' },
      { label: 'Model reliability', value: formatRatio(miner && miner.model_reliability) },
      { label: 'Ops reliability', value: formatRatio(miner && miner.ops_reliability) },
      { label: 'Arena multiplier', value: formatRatio(miner && miner.arena_multiplier) },
      { label: 'Released rewards', value: formatMetric(miner && miner.total_rewards) },
    ],
    health: [
      { label: 'Admission', value: formatMetric(miner && miner.admission_state) },
      { label: 'Maturity', value: formatMetric(miner && miner.maturity_state) },
      {
        label: 'Risk review',
        value:
          miner && miner.open_risk_case_count
            ? `${miner.open_risk_case_count} open`
            : formatMetric(miner && miner.risk_review_state),
      },
      { label: 'Reward eligibility', value: formatMetric(miner && miner.reward_eligibility_status) },
      { label: 'Release ratio', value: formatRatio(miner && miner.anti_abuse_discount, 2) },
      { label: 'Held rewards', value: formatMetric(miner && miner.held_rewards) },
    ],
    latest: {
      fast: buildLaneCard(
        'Latest fast lane',
        fast,
        [
          ['Task', fast && fast.task_run_id],
          ['Prediction', fast && fast.p_yes_bps],
          ['Baseline', fast && fast.baseline_q_bps],
          ['Outcome', fast && fast.outcome],
          ['Reward', fast && fast.reward_amount],
          ['State', fast && fast.state],
        ],
        fast ? `${fast.asset} · ${fast.reward_eligibility_status}` : null
      ),
      daily: buildLaneCard(
        'Latest daily anchor',
        daily,
        [
          ['Task', daily && daily.task_run_id],
          ['Prediction', daily && daily.p_yes_bps],
          ['Outcome', daily && daily.outcome],
          ['Anchor multiplier', daily && daily.anchor_multiplier],
          ['State', daily && daily.state],
        ],
        daily ? `${daily.asset}` : null
      ),
      arena: buildLaneCard(
        'Latest arena adjustment',
        arena,
        [
          ['Tournament', arena && arena.tournament_id],
          ['Mode', arena && arena.rated_or_practice],
          ['Arena score', arena && arena.arena_score],
          ['Multiplier after', arena && arena.arena_multiplier_after],
        ],
        arena && arena.eligible_for_multiplier ? 'rated human-only' : 'not multiplier-eligible'
      ),
    },
    timeline: [
      { label: 'Released rewards', value: formatMetric(timeline.released_rewards) },
      { label: 'Held rewards', value: formatMetric(timeline.held_rewards) },
      { label: 'Open hold entries', value: formatMetric(timeline.open_hold_entry_count) },
      { label: 'Pending resolution', value: formatMetric(timeline.pending_resolution_count) },
      { label: 'Latest fast reward', value: formatMetric(timeline.latest_fast_reward_amount) },
      { label: 'Latest daily multiplier', value: formatMetric(timeline.latest_daily_anchor_multiplier) },
      { label: 'Latest arena multiplier', value: formatMetric(timeline.latest_arena_multiplier_after) },
    ],
    settlement: [
      { label: 'Latest reward window', value: formatMetric(miner && miner.latest_reward_window && miner.latest_reward_window.id) },
      { label: 'Reward window state', value: formatMetric(miner && miner.latest_reward_window && miner.latest_reward_window.state) },
      { label: 'Latest batch', value: formatMetric(miner && miner.latest_settlement_batch && miner.latest_settlement_batch.id) },
      { label: 'Batch state', value: formatMetric(miner && miner.latest_settlement_batch && miner.latest_settlement_batch.state) },
      { label: 'Anchor job', value: formatMetric(miner && miner.latest_anchor_job && miner.latest_anchor_job.id) },
      { label: 'Anchor state', value: formatMetric(miner && miner.latest_anchor_job && miner.latest_anchor_job.state) },
    ],
    network: [
      { label: 'Active miners', value: formatMetric(networkStatsResponse && networkStatsResponse.active_miners) },
      { label: 'Active fast tasks', value: formatMetric(networkStatsResponse && networkStatsResponse.active_fast_tasks) },
      { label: 'Settled fast tasks', value: formatMetric(networkStatsResponse && networkStatsResponse.settled_fast_tasks) },
      { label: 'Total rewards paid', value: formatMetric(networkStatsResponse && networkStatsResponse.total_rewards_paid) },
      { label: 'Protocol', value: formatMetric(networkStatsResponse && networkStatsResponse.protocol) },
      { label: 'Server version', value: formatMetric(networkStatsResponse && networkStatsResponse.server_version) },
    ],
  }
}

module.exports = {
  DEFAULT_API_BASE_URL,
  normalizeApiBaseUrl,
  unwrapEnvelope,
  buildDashboardViewModel,
}
