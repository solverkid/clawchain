const test = require('node:test')
const assert = require('node:assert/strict')

const { buildNetworkViewModel } = require('./network-data')

test('buildNetworkViewModel merges stats and leaderboard items', () => {
  const viewModel = buildNetworkViewModel({
    networkStatsResponse: {
      protocol: 'clawchain-forecast-v1',
      active_miners: 24,
      active_fast_tasks: 2,
      settled_fast_tasks: 340,
      total_rewards_paid: 123456,
      latest_reward_window_id: 'rw_latest',
      latest_settlement_batch_id: 'sb_latest',
      latest_settlement_state: 'anchor_submitted',
      latest_anchor_job_state: 'broadcast_submitted',
      server_version: '1.0.0-alpha',
    },
    leaderboardEnvelope: {
      data: {
        items: [
          {
            address: 'claw1alpha',
            name: 'miner-alpha',
            public_rank: 1,
            public_elo: 1412,
            total_rewards: 9800,
            settled_tasks: 41,
            model_reliability: 1.04,
            ops_reliability: 0.97,
            arena_multiplier: 1.01,
            admission_state: 'open',
            risk_review_state: 'clear',
            open_risk_case_count: 0,
          },
          {
            address: 'claw1beta',
            name: 'miner-beta',
            public_rank: 2,
            public_elo: 1388,
            total_rewards: 9100,
            settled_tasks: 39,
            model_reliability: 1.01,
            ops_reliability: 0.95,
            arena_multiplier: 1.0,
            admission_state: 'probation',
            risk_review_state: 'review_required',
            open_risk_case_count: 1,
          },
        ],
      },
    },
  })

  assert.equal(viewModel.summary[0].value, '24')
  assert.equal(viewModel.summary[3].value, '123456')
  assert.equal(viewModel.summary[4].value, 'rw_latest')
  assert.equal(viewModel.summary[7].value, 'broadcast_submitted')
  assert.equal(viewModel.leaderboard.length, 2)
  assert.equal(viewModel.leaderboard[0].rank, '#1')
  assert.match(viewModel.leaderboard[0].meta, /41 settled/)
  assert.equal(viewModel.leaderboard[1].risk, '1 open')
  assert.equal(viewModel.leaderboard[1].admission, 'probation')
})
