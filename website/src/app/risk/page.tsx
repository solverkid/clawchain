'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import dashboardData from '@/lib/dashboard-data'
import riskData from '@/lib/risk-data'

const { DEFAULT_API_BASE_URL, normalizeApiBaseUrl } = dashboardData
const { buildRiskViewModel } = riskData

const STORAGE_KEY = 'clawchain.dashboard.apiBaseUrl'

type RiskRow = {
  id: string
  title: string
  severity: string
  state: string
  economicUnitId: string
  minerAddress: string
  decision: string
  reviewedBy: string
  reviewedAt: string
  meta: string
}

function SummaryGrid({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-[0_20px_80px_rgba(0,0,0,0.35)]">
      <div className="mb-5 text-lg font-semibold text-white">Risk queue snapshot</div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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

export default function RiskPage() {
  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_API_BASE_URL)
  const [riskPayload, setRiskPayload] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function loadRisk(nextApiBaseUrl: string) {
    const normalizedApiBaseUrl = normalizeApiBaseUrl(nextApiBaseUrl)
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`${normalizedApiBaseUrl}/admin/risk-cases`)
      if (!response.ok) {
        throw new Error(`risk queue request failed (${response.status})`)
      }
      const payload = await response.json()
      window.localStorage.setItem(STORAGE_KEY, normalizedApiBaseUrl)
      setApiBaseUrl(normalizedApiBaseUrl)
      setRiskPayload(payload)
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'risk queue request failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    const initialBaseUrl = stored ? normalizeApiBaseUrl(stored) : DEFAULT_API_BASE_URL
    setApiBaseUrl(initialBaseUrl)
    void loadRisk(initialBaseUrl)
  }, [])

  const viewModel = buildRiskViewModel({ riskCasesResponse: riskPayload })
  const openItems = viewModel.openItems as RiskRow[]
  const reviewedItems = viewModel.reviewedItems as RiskRow[]

  return (
    <main className="min-h-screen bg-[#050505] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,107,0,0.15),transparent_28%),linear-gradient(180deg,rgba(255,255,255,0.02),transparent_36%)]" />
      <div className="relative mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="text-sm uppercase tracking-[0.32em] text-[#ff9d4d]">Operator Read Surface</div>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight text-white md:text-6xl">
              Review open economic-unit risk cases without digging through raw logs.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-white/60 md:text-lg">
              This is a lightweight admin surface for the live risk queue. It shows what still needs review and what the
              operator already closed, suppressed, or escalated.
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
              href="/network"
              className="rounded-full border border-white/10 px-5 py-3 text-sm font-medium text-white/70 transition hover:border-white/25 hover:text-white"
            >
              Network view
            </Link>
          </div>
        </div>

        <section className="rounded-[2rem] border border-white/10 bg-black/35 p-6 shadow-[0_30px_120px_rgba(0,0,0,0.45)] backdrop-blur">
          <form
            className="grid gap-4 lg:grid-cols-[1fr,auto]"
            onSubmit={(event) => {
              event.preventDefault()
              void loadRisk(apiBaseUrl)
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
              {loading ? 'Refreshing…' : 'Refresh risk queue'}
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
              <h2 className="text-lg font-semibold text-white">Open cases</h2>
              <div className="text-sm text-white/45">Current queue from `/admin/risk-cases`</div>
            </div>
            <div className="grid gap-4">
              {openItems.length ? (
                openItems.map((item) => (
                  <article key={item.id} className="rounded-3xl border border-white/8 bg-black/20 p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-sm uppercase tracking-[0.18em] text-[#ff9d4d]">{item.title}</div>
                        <div className="mt-2 text-xs text-white/45">{item.id}</div>
                      </div>
                      <div className="flex gap-2 text-xs uppercase tracking-[0.18em]">
                        <span className="rounded-full border border-white/10 px-3 py-2 text-white/70">{item.severity}</span>
                        <span className="rounded-full border border-white/10 px-3 py-2 text-white/70">{item.state}</span>
                      </div>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-4">
                        <div className="text-xs uppercase tracking-[0.18em] text-white/40">Economic unit</div>
                        <div className="mt-2 font-mono text-sm text-white">{item.economicUnitId}</div>
                      </div>
                      <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-4">
                        <div className="text-xs uppercase tracking-[0.18em] text-white/40">Miner address</div>
                        <div className="mt-2 font-mono text-sm text-white">{item.minerAddress}</div>
                      </div>
                    </div>
                    <div className="mt-4 text-sm text-white/55">{item.meta}</div>
                  </article>
                ))
              ) : (
                <div className="rounded-3xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-10 text-center text-sm text-white/45">
                  No open risk cases.
                </div>
              )}
            </div>
          </section>

          <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-[0_20px_80px_rgba(0,0,0,0.35)]">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Reviewed outcomes</h2>
              <div className="text-sm text-white/45">Most recent operator decisions</div>
            </div>
            <div className="grid gap-4">
              {reviewedItems.length ? (
                reviewedItems.map((item) => (
                  <article key={item.id} className="rounded-3xl border border-white/8 bg-black/20 p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-sm uppercase tracking-[0.18em] text-[#ff9d4d]">{item.title}</div>
                        <div className="mt-2 text-xs text-white/45">{item.id}</div>
                      </div>
                      <div className="flex gap-2 text-xs uppercase tracking-[0.18em]">
                        <span className="rounded-full border border-white/10 px-3 py-2 text-white/70">{item.severity}</span>
                        <span className="rounded-full border border-white/10 px-3 py-2 text-white/70">{item.state}</span>
                        <span className="rounded-full border border-white/10 px-3 py-2 text-white/70">{item.decision}</span>
                      </div>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-4">
                        <div className="text-xs uppercase tracking-[0.18em] text-white/40">Operator</div>
                        <div className="mt-2 font-mono text-sm text-white">{item.reviewedBy}</div>
                      </div>
                      <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-4">
                        <div className="text-xs uppercase tracking-[0.18em] text-white/40">Reviewed at</div>
                        <div className="mt-2 font-mono text-sm text-white">{item.reviewedAt}</div>
                      </div>
                    </div>
                    <div className="mt-4 text-sm text-white/55">{item.meta}</div>
                  </article>
                ))
              ) : (
                <div className="rounded-3xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-10 text-center text-sm text-white/45">
                  No reviewed cases yet.
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  )
}
