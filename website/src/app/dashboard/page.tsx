'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import dashboardData from '@/lib/dashboard-data'

const {
  DEFAULT_API_BASE_URL,
  normalizeApiBaseUrl,
  buildDashboardViewModel,
} = dashboardData

const STORAGE_KEYS = {
  apiBaseUrl: 'clawchain.dashboard.apiBaseUrl',
  minerId: 'clawchain.dashboard.minerId',
}

function MetricGrid({ title, items }: { title: string; items: Array<{ label: string; value: string }> }) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-[0_20px_80px_rgba(0,0,0,0.35)]">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <div key={item.label} className="rounded-2xl border border-white/8 bg-black/20 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-white/45">{item.label}</div>
            <div className="mt-2 text-2xl font-semibold text-white">{item.value}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

function LaneCard({
  card,
}: {
  card: null | { title: string; meta: string | null; rows: Array<{ label: string; value: string }> }
}) {
  if (!card) {
    return (
      <div className="rounded-3xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-sm text-white/45">
        No settled sample yet.
      </div>
    )
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-4">
        <div className="text-sm uppercase tracking-[0.18em] text-[#ff9d4d]">{card.title}</div>
        <div className="mt-2 text-sm text-white/55">{card.meta || 'latest settled artifact'}</div>
      </div>
      <div className="space-y-3">
        {card.rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4 border-b border-white/6 pb-3 text-sm last:border-b-0 last:pb-0">
            <span className="text-white/55">{row.label}</span>
            <span className="font-mono text-white">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_API_BASE_URL)
  const [minerId, setMinerId] = useState('')
  const [networkStats, setNetworkStats] = useState<any>(null)
  const [minerStatus, setMinerStatus] = useState<any>(null)
  const [serverTime, setServerTime] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const storedApiBaseUrl = window.localStorage.getItem(STORAGE_KEYS.apiBaseUrl)
    const storedMinerId = window.localStorage.getItem(STORAGE_KEYS.minerId)
    if (storedApiBaseUrl) {
      setApiBaseUrl(normalizeApiBaseUrl(storedApiBaseUrl))
    }
    if (storedMinerId) {
      setMinerId(storedMinerId)
    }
  }, [])

  async function loadDashboard(nextApiBaseUrl: string, nextMinerId: string) {
    const normalizedApiBaseUrl = normalizeApiBaseUrl(nextApiBaseUrl)
    setLoading(true)
    setError(null)
    try {
      const statsPromise = fetch(`${normalizedApiBaseUrl}/clawchain/stats`).then(async (response) => {
        if (!response.ok) {
          throw new Error(`stats request failed (${response.status})`)
        }
        return response.json()
      })

      const minerPromise = nextMinerId.trim()
        ? fetch(`${normalizedApiBaseUrl}/v1/miners/${encodeURIComponent(nextMinerId.trim())}/status`).then(async (response) => {
            if (!response.ok) {
              throw new Error(`miner status request failed (${response.status})`)
            }
            return response.json()
          })
        : Promise.resolve(null)

      const [statsPayload, minerPayload] = await Promise.all([statsPromise, minerPromise])
      window.localStorage.setItem(STORAGE_KEYS.apiBaseUrl, normalizedApiBaseUrl)
      window.localStorage.setItem(STORAGE_KEYS.minerId, nextMinerId.trim())
      setNetworkStats(statsPayload)
      setMinerStatus(minerPayload)
      setServerTime(minerPayload?.server_time || null)
      setApiBaseUrl(normalizedApiBaseUrl)
      setMinerId(nextMinerId.trim())
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : 'dashboard request failed'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadDashboard(apiBaseUrl, minerId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const viewModel = buildDashboardViewModel({
    minerStatusEnvelope: minerStatus,
    networkStatsResponse: networkStats,
  })

  return (
    <main className="min-h-screen bg-[#070707] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,107,0,0.16),transparent_38%),linear-gradient(180deg,rgba(255,255,255,0.02),transparent_35%)]" />
      <div className="relative mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="text-sm uppercase tracking-[0.32em] text-[#ff9d4d]">Forecast Mining Alpha</div>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight text-white md:text-6xl">
              Miner dashboard for fast lane, daily anchor, and arena multiplier.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-white/60 md:text-lg">
              This is a read-model surface for the new mining system. It does not submit forecasts. It lets a miner inspect
              current reliability, reward release, pending resolution, and arena adjustments against a live FastAPI service.
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              href="/network"
              className="rounded-full border border-white/10 px-5 py-3 text-sm font-medium text-white/70 transition hover:border-white/25 hover:text-white"
            >
              Network view
            </Link>
            <Link
              href="/risk"
              className="rounded-full border border-white/10 px-5 py-3 text-sm font-medium text-white/70 transition hover:border-white/25 hover:text-white"
            >
              Risk queue
            </Link>
            <Link
              href="/"
              className="rounded-full border border-white/10 px-5 py-3 text-sm font-medium text-white/70 transition hover:border-white/25 hover:text-white"
            >
              Back to landing
            </Link>
            <a
              href="https://github.com/0xVeryBigOrange/clawchain/blob/main/docs/MINING_DESIGN.md"
              target="_blank"
              rel="noreferrer"
              className="rounded-full bg-[#ff6b00] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#ff8b37]"
            >
              Read mining design
            </a>
          </div>
        </div>

        <section className="rounded-[2rem] border border-white/10 bg-black/35 p-6 shadow-[0_30px_120px_rgba(0,0,0,0.45)] backdrop-blur">
          <form
            className="grid gap-4 lg:grid-cols-[1.2fr,1.4fr,auto]"
            onSubmit={(event) => {
              event.preventDefault()
              void loadDashboard(apiBaseUrl, minerId)
            }}
          >
            <label className="block">
              <div className="mb-2 text-xs uppercase tracking-[0.2em] text-white/45">Mining service URL</div>
              <input
                value={apiBaseUrl}
                onChange={(event) => setApiBaseUrl(event.target.value)}
                className="w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none transition placeholder:text-white/25 focus:border-[#ff9d4d]"
                placeholder="http://127.0.0.1:1317"
              />
            </label>
            <label className="block">
              <div className="mb-2 text-xs uppercase tracking-[0.2em] text-white/45">Miner address</div>
              <input
                value={minerId}
                onChange={(event) => setMinerId(event.target.value)}
                className="w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none transition placeholder:text-white/25 focus:border-[#ff9d4d]"
                placeholder="claw1..."
              />
            </label>
            <button
              type="submit"
              className="rounded-2xl bg-[#ff6b00] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#ff8b37] disabled:cursor-not-allowed disabled:opacity-60"
              disabled={loading}
            >
              {loading ? 'Refreshing…' : 'Refresh dashboard'}
            </button>
          </form>

          <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-white/50">
            <span>Server time: {serverTime || 'not loaded yet'}</span>
            <span>Network snapshot: {networkStats ? 'live' : 'pending'}</span>
            <span>Miner snapshot: {minerStatus ? 'loaded' : 'enter miner address to load'}</span>
          </div>
          {error ? (
            <div className="mt-4 rounded-2xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
          ) : null}
        </section>

        <div className="mt-8 grid gap-6">
          <MetricGrid title="Miner summary" items={viewModel.summary} />
          <MetricGrid title="Risk, maturity, and release state" items={viewModel.health} />

          <section className="grid gap-6 xl:grid-cols-3">
            <LaneCard card={viewModel.latest.fast} />
            <LaneCard card={viewModel.latest.daily} />
            <LaneCard card={viewModel.latest.arena} />
          </section>

          <MetricGrid title="Reward timeline" items={viewModel.timeline} />
          <MetricGrid title="Settlement snapshot" items={viewModel.settlement} />
          <MetricGrid title="Network snapshot" items={viewModel.network} />
        </div>
      </div>
    </main>
  )
}
