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

function unwrapEnvelope(payload) {
  if (payload && typeof payload === 'object' && payload.data && typeof payload.data === 'object') {
    return payload.data
  }
  return payload || null
}

function buildNetworkViewModel({ networkStatsResponse, leaderboardEnvelope }) {
  const leaderboard = unwrapEnvelope(leaderboardEnvelope)
  const items = (leaderboard && leaderboard.items) || []

  return {
    summary: [
      { label: 'Active miners', value: formatMetric(networkStatsResponse && networkStatsResponse.active_miners) },
      { label: 'Active fast tasks', value: formatMetric(networkStatsResponse && networkStatsResponse.active_fast_tasks) },
      { label: 'Settled fast tasks', value: formatMetric(networkStatsResponse && networkStatsResponse.settled_fast_tasks) },
      { label: 'Total rewards paid', value: formatMetric(networkStatsResponse && networkStatsResponse.total_rewards_paid) },
      { label: 'Latest reward window', value: formatMetric(networkStatsResponse && networkStatsResponse.latest_reward_window_id) },
      { label: 'Latest batch', value: formatMetric(networkStatsResponse && networkStatsResponse.latest_settlement_batch_id) },
      { label: 'Settlement state', value: formatMetric(networkStatsResponse && networkStatsResponse.latest_settlement_state) },
      { label: 'Anchor state', value: formatMetric(networkStatsResponse && networkStatsResponse.latest_anchor_job_state) },
      { label: 'Protocol', value: formatMetric(networkStatsResponse && networkStatsResponse.protocol) },
      { label: 'Server version', value: formatMetric(networkStatsResponse && networkStatsResponse.server_version) },
    ],
    leaderboard: items.map((miner) => ({
      address: miner.address,
      name: miner.name || 'anonymous miner',
      rank: miner.public_rank ? `#${miner.public_rank}` : '—',
      publicElo: formatMetric(miner.public_elo),
      rewards: formatMetric(miner.total_rewards),
      admission: formatMetric(miner.admission_state),
      risk: miner.open_risk_case_count ? `${miner.open_risk_case_count} open` : formatMetric(miner.risk_review_state),
      meta: `${formatMetric(miner.settled_tasks)} settled · model ${formatRatio(miner.model_reliability)} · ops ${formatRatio(miner.ops_reliability)} · arena ${formatRatio(miner.arena_multiplier)}`,
    })),
  }
}

module.exports = {
  buildNetworkViewModel,
}
