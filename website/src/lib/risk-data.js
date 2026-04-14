function formatMetric(value, fallback = '—') {
  if (value === null || value === undefined || value === '') {
    return fallback
  }
  return String(value)
}

function buildRiskViewModel({ riskCasesResponse }) {
  const items = (riskCasesResponse && riskCasesResponse.items) || []
  const openItems = items.filter((item) => item.state === 'open')
  const reviewedItems = items.filter((item) => item.state !== 'open')
  const duplicateCount = items.filter((item) => item.case_type === 'economic_unit_duplicate').length
  const clusterCount = items.filter((item) => item.case_type === 'economic_unit_cluster').length
  const highSeverityCount = items.filter((item) => item.severity === 'high').length

  const mappedItems = items.map((item) => ({
    id: item.id,
    title: formatMetric(item.case_type),
    severity: formatMetric(item.severity),
    state: formatMetric(item.state),
    economicUnitId: formatMetric(item.economic_unit_id),
    minerAddress: formatMetric(item.miner_address),
    decision: formatMetric(item.decision),
    reviewedBy: formatMetric(item.reviewed_by),
    reviewedAt: formatMetric(item.reviewed_at),
    meta: `task ${formatMetric(item.task_run_id)} · submission ${formatMetric(item.submission_id)} · updated ${formatMetric(item.updated_at)}`,
  }))

  return {
    summary: [
      { label: 'Total cases', value: formatMetric(items.length) },
      { label: 'Open cases', value: formatMetric(openItems.length) },
      { label: 'Reviewed cases', value: formatMetric(reviewedItems.length) },
      { label: 'Duplicate cases', value: formatMetric(duplicateCount) },
      { label: 'Cluster cases', value: formatMetric(clusterCount) },
      { label: 'High severity', value: formatMetric(highSeverityCount) },
    ],
    items: mappedItems,
    openItems: mappedItems.filter((item) => item.state === 'open'),
    reviewedItems: mappedItems.filter((item) => item.state !== 'open'),
  }
}

module.exports = {
  buildRiskViewModel,
}
