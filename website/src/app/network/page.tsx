'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import dashboardData from '@/lib/dashboard-data'
import networkData from '@/lib/network-data'

const { DEFAULT_API_BASE_URL, normalizeApiBaseUrl } = dashboardData
const { buildNetworkViewModel } = networkData

const STORAGE_KEY = 'clawchain.dashboard.apiBaseUrl'

type LeaderboardRow = {
  address: string
  name: string
  rank: string
  publicElo: string
  rewards: string
  admission: string
  risk: string
  meta: string
}

function SummaryGrid({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-[0_20px_80px_rgba(0,0,0,0.35)]">
      <div className="mb-5 text-lg font-semibold text-white">Network snapshot</div>
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

export default function NetworkPage() {
  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_API_BASE_URL)
  const [leaderboardPayload, setLeaderboardPayload] = useState<any>(null)
  const [networkStats, setNetworkStats] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function loadNetwork(nextApiBaseUrl: string) {
    const normalizedApiBaseUrl = normalizeApiBaseUrl(nextApiBaseUrl)
    setLoading(true)
    setError(null)
    try {
      const [statsPayload, leaderboard] = await Promise.all([
        fetch(`${normalizedApiBaseUrl}/clawchain/stats`).then(async (response) => {
          if (!response.ok) {
            throw new Error(`stats request failed (${response.status})`)
          }
          return response.json()
        }),
        fetch(`${normalizedApiBaseUrl}/v1/leaderboard`).then(async (response) => {
          if (!response.ok) {
            throw new Error(`leaderboard request failed (${response.status})`)
          }
          return response.json()
        }),
      ])

      window.localStorage.setItem(STORAGE_KEY, normalizedApiBaseUrl)
      setApiBaseUrl(normalizedApiBaseUrl)
      setNetworkStats(statsPayload)
      setLeaderboardPayload(leaderboard)
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'network request failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    const initialBaseUrl = stored ? normalizeApiBaseUrl(stored) : DEFAULT_API_BASE_URL
    setApiBaseUrl(initialBaseUrl)
    void loadNetwork(initialBaseUrl)
  }, [])

  const viewModel = buildNetworkViewModel({
    networkStatsResponse: networkStats,
    leaderboardEnvelope: leaderboardPayload,
  })
  const leaderboard = viewModel.leaderboard as LeaderboardRow[]

  return (
    <main className="min-h-screen bg-[#060606] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,107,0,0.18),transparent_30%),linear-gradient(180deg,rgba(255,255,255,0.02),transparent_36%)]" />
      <div className="relative mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="text-sm uppercase tracking-[0.32em] text-[#ff9d4d]">Public Network Surface</div>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight text-white md:text-6xl">
              See the network state and who is actually ranking at the top.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-white/60 md:text-lg">
              This is the public read-model for the forecast mining alpha. It shows network health and the current top miners
              without exposing internal anti-abuse state beyond what the product should surface publicly.
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              href="/dashboard"
              className="rounded-full border border-white/10 px-5 py-3 text-sm font-medium text-white/70 transition hover:border-white/25 hover:text-white"
            >
              Miner dashboard
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
              Landing page
            </Link>
          </div>
        </div>

        <section className="rounded-[2rem] border border-white/10 bg-black/35 p-6 shadow-[0_30px_120px_rgba(0,0,0,0.45)] backdrop-blur">
          <form
            className="grid gap-4 lg:grid-cols-[1fr,auto]"
            onSubmit={(event) => {
              event.preventDefault()
              void loadNetwork(apiBaseUrl)
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
            <button
              type="submit"
              className="rounded-2xl bg-[#ff6b00] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#ff8b37] disabled:cursor-not-allowed disabled:opacity-60"
              disabled={loading}
            >
              {loading ? 'Refreshing…' : 'Refresh network'}
            </button>
          </form>
          {error ? (
            <div className="mt-4 rounded-2xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
          ) : null}
        </section>

        <div className="mt-8 grid gap-6">
          <SummaryGrid items={viewModel.summary} />

          <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-[0_20px_80px_rgba(0,0,0,0.35)]">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Top miners</h2>
              <div className="text-sm text-white/45">Public rank, reliability, rewards, and visible risk state</div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full border-separate border-spacing-y-3">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-[0.18em] text-white/40">
                    <th className="px-4 py-2">Rank</th>
                    <th className="px-4 py-2">Miner</th>
                    <th className="px-4 py-2">Public ELO</th>
                    <th className="px-4 py-2">Rewards</th>
                    <th className="px-4 py-2">Admission</th>
                    <th className="px-4 py-2">Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboard.length ? (
                    leaderboard.map((miner: LeaderboardRow) => (
                      <tr key={miner.address} className="rounded-2xl bg-black/25 text-sm text-white">
                        <td className="rounded-l-2xl px-4 py-4 font-semibold text-[#ff9d4d]">{miner.rank}</td>
                        <td className="px-4 py-4">
                          <div className="font-medium">{miner.name}</div>
                          <div className="mt-1 font-mono text-xs text-white/45">{miner.address}</div>
                          <div className="mt-2 text-xs text-white/50">{miner.meta}</div>
                        </td>
                        <td className="px-4 py-4 font-mono">{miner.publicElo}</td>
                        <td className="px-4 py-4 font-mono">{miner.rewards}</td>
                        <td className="px-4 py-4">{miner.admission}</td>
                        <td className="rounded-r-2xl px-4 py-4">{miner.risk}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6} className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-white/45">
                        No public miners yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </main>
  )
}
