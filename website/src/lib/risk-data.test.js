const test = require('node:test')
const assert = require('node:assert/strict')

const { buildRiskViewModel } = require('./risk-data')

test('buildRiskViewModel summarizes open risk cases by type and severity', () => {
  const viewModel = buildRiskViewModel({
    riskCasesResponse: {
      items: [
        {
          id: 'rc_1',
          case_type: 'economic_unit_cluster',
          severity: 'medium',
          state: 'open',
          economic_unit_id: 'eu:a',
          miner_address: 'claw1alpha',
          task_run_id: null,
          submission_id: null,
          updated_at: '2026-04-10T01:00:00Z',
        },
        {
          id: 'rc_2',
          case_type: 'economic_unit_duplicate',
          severity: 'high',
          state: 'open',
          economic_unit_id: 'eu:a',
          miner_address: 'claw1beta',
          task_run_id: 'tr_fast_1',
          submission_id: 'sub_1',
          updated_at: '2026-04-10T01:05:00Z',
        },
        {
          id: 'rc_3',
          case_type: 'economic_unit_duplicate',
          severity: 'medium',
          state: 'cleared',
          economic_unit_id: 'eu:b',
          miner_address: 'claw1gamma',
          task_run_id: 'tr_fast_2',
          submission_id: 'sub_2',
          decision: 'clear',
          reviewed_by: 'ops-1',
          reviewed_at: '2026-04-10T01:15:00Z',
          updated_at: '2026-04-10T01:10:00Z',
        },
      ],
    },
  })

  assert.equal(viewModel.summary[0].value, '3')
  assert.equal(viewModel.summary[1].value, '2')
  assert.equal(viewModel.summary[2].value, '1')
  assert.equal(viewModel.summary[5].value, '1')
  assert.equal(viewModel.items[0].title, 'economic_unit_cluster')
  assert.equal(viewModel.items[1].severity, 'high')
  assert.equal(viewModel.reviewedItems[0].decision, 'clear')
  assert.match(viewModel.items[1].meta, /tr_fast_1/)
})
