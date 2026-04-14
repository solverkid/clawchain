const test = require('node:test')
const assert = require('node:assert/strict')

const {
  DEFAULT_API_BASE_URL,
  normalizeApiBaseUrl,
  buildDashboardViewModel,
} = require('./dashboard-data')

test('normalizeApiBaseUrl trims whitespace and trailing slash', () => {
  assert.equal(DEFAULT_API_BASE_URL, 'http://127.0.0.1:1317')
  assert.equal(normalizeApiBaseUrl(' http://127.0.0.1:1317/ '), 'http://127.0.0.1:1317')
  assert.equal(normalizeApiBaseUrl(''), DEFAULT_API_BASE_URL)
})

test('buildDashboardViewModel unwraps envelopes into dashboard cards', () => {
  const viewModel = buildDashboardViewModel({
    minerStatusEnvelope: {
      data: {
        miner_id: 'claw1miner',
        public_rank: 7,
        public_elo: 1326,
        model_reliability: 1.03,
        ops_reliability: 0.94,
        arena_multiplier: 1.012,
        anti_abuse_discount: 0.2,
        admission_state: 'probation',
        maturity_state: 'pending_resolution',
        risk_review_state: 'review_required',
        open_risk_case_count: 2,
        held_rewards: 1800,
        total_rewards: 4200,
        reward_eligibility_status: 'eligible',
        score_explanation: {
          latest_fast: {
            task_run_id: 'tr_fast_1',
            asset: 'BTCUSDT',
            reward_amount: 2400,
            outcome: 1,
            baseline_q_bps: 5400,
            p_yes_bps: 6100,
            state: 'resolved',
          },
          latest_daily: {
            task_run_id: 'tr_daily_1',
            asset: 'BTC',
            anchor_multiplier: 1.014,
            state: 'resolved',
          },
          latest_arena: {
            tournament_id: 'arena-1',
            rated_or_practice: 'rated',
            arena_multiplier_after: 1.012,
          },
        },
        reward_timeline: {
          released_rewards: 4200,
          held_rewards: 1800,
          open_hold_entry_count: 3,
          pending_resolution_count: 1,
          latest_fast_reward_amount: 2400,
          latest_daily_anchor_multiplier: 1.014,
          latest_arena_multiplier_after: 1.012,
        },
        latest_reward_window: {
          id: 'rw_1',
          state: 'settled',
        },
        latest_settlement_batch: {
          id: 'sb_1',
          state: 'anchored',
        },
        latest_anchor_job: {
          id: 'aj_1',
          state: 'anchored',
        },
      },
      server_time: '2026-04-10T12:00:00Z',
    },
    networkStatsResponse: {
      protocol: 'clawchain-forecast-v1',
      active_miners: 12,
      active_fast_tasks: 2,
      settled_fast_tasks: 128,
      total_rewards_paid: 543210,
    },
  })

  assert.equal(viewModel.summary[0].label, 'Public ELO')
  assert.equal(viewModel.summary[0].value, '1326')
  assert.equal(viewModel.summary[1].value, '#7')
  assert.equal(viewModel.health[0].label, 'Admission')
  assert.equal(viewModel.health[0].value, 'probation')
  assert.equal(viewModel.health[2].value, '2 open')
  assert.equal(viewModel.latest.fast.title, 'Latest fast lane')
  assert.match(viewModel.latest.fast.meta, /BTCUSDT/)
  assert.equal(viewModel.timeline[1].value, '1800')
  assert.equal(viewModel.settlement[0].value, 'rw_1')
  assert.equal(viewModel.settlement[3].value, 'anchored')
  assert.equal(viewModel.network[0].value, '12')
  assert.equal(viewModel.serverTime, '2026-04-10T12:00:00Z')
})
