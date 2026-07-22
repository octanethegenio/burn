/// <reference types="vite/client" />

import {
  Fragment,
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  fetchStatus,
  fetchSummary,
  sendHeartbeat,
  syncNow,
  type ModelRow,
  type Status,
  type Summary,
} from './api'
import { groupModelsByProvider } from './providers'
import './App.css'

const AUTO_SYNC_MS = 120_000
const HEARTBEAT_MS = 30_000

function money(usd: number) {
  return usd.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function tokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function relTime(ts: number | null) {
  if (!ts) return 'never'
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

function RelativeTime({ ts }: { ts: number | null }) {
  const [, update] = useState(0)

  useEffect(() => {
    const id = window.setInterval(() => update((value) => value + 1), 30_000)
    return () => window.clearInterval(id)
  }, [])

  return <>{relTime(ts)}</>
}

function fmtRange(start?: string, end?: string) {
  if (!start || !end) return '—'
  const a = new Date(start)
  const b = new Date(end)
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }
  return `${a.toLocaleDateString(undefined, opts)} → ${b.toLocaleDateString(undefined, opts)}`
}

function formatPlanLabel(membership: string) {
  return membership
    .trim()
    .replace(/[_-]+/g, ' ')
    .replace(/\w\S*/g, (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
}

function kindLabel(kind: string | null) {
  if (!kind) return '—'
  return kind.replace(/^USAGE_EVENT_KIND_/, '').replaceAll('_', ' ').toLowerCase()
}

function norm(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

function compact(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]/g, '')
}

const ALIASES: Record<string, string[]> = {
  grok: ['grok', 'cursorgrok', 'xhigh'],
  composer: ['composer'],
  claude: ['claude'],
  sonnet: ['sonnet'],
  opus: ['opus'],
  fable: ['fable'],
  gpt: ['gpt'],
  glm: ['glm'],
  kimi: ['kimi'],
  auto: ['auto'],
  fast: ['fast'],
  high: ['high', 'xhigh'],
  xhigh: ['xhigh', 'high'],
}

function expandTokens(q: string): string[] {
  const raw = norm(q)
  if (!raw) return []
  const out: string[] = []
  for (const p of raw.split(/\s+/).filter(Boolean)) {
    out.push(p)
    const a = ALIASES[p]
    if (a) out.push(...a)
  }
  return [...new Set(out)]
}

function isSubsequence(needle: string, hay: string) {
  let i = 0
  for (const ch of hay) {
    if (ch === needle[i]) i++
    if (i === needle.length) return true
  }
  return needle.length === 0
}

type SearchIndex = { row: ModelRow; n: string; c: string }

function scoreIndexed(idx: SearchIndex, tokens: string[], qNorm: string, qComp: string): number {
  const { n: mNorm, c: mComp } = idx
  let score = 0
  if (mNorm === qNorm || mComp === qComp) score += 1000
  if (mNorm.startsWith(qNorm) || mComp.startsWith(qComp)) score += 400
  if (mNorm.includes(qNorm) || mComp.includes(qComp)) score += 220
  if (isSubsequence(qComp, mComp)) score += 80
  for (const t of tokens) {
    const tc = compact(t)
    if (!tc) continue
    if (mComp === tc) score += 180
    else if (mComp.startsWith(tc)) score += 120
    else if (mComp.includes(tc)) score += 90
    else if (isSubsequence(tc, mComp)) score += 35
  }
  if (tokens.length > 1) {
    const hits = tokens.filter((t) => {
      const tc = compact(t)
      return mComp.includes(tc) || isSubsequence(tc, mComp)
    })
    if (hits.length < Math.ceil(tokens.length * 0.6)) return 0
    score += hits.length * 25
  }
  return score
}

type Theme = 'dark' | 'light'
type TabId = 'models' | 'events'
type ModelsView = 'model' | 'provider'
type SortKey =
  | 'model'
  | 'request_count'
  | 'input_tokens'
  | 'output_tokens'
  | 'cache_read_tokens'
  | 'cost_usd'

function readTheme(): Theme {
  try {
    return localStorage.getItem('burn-theme') === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

function SortArrow({ dir, active }: { dir: 'asc' | 'desc'; active: boolean }) {
  return (
    <span className={`sort-ind${active ? ' on' : ''}${active && dir === 'asc' ? ' asc' : ''}`} aria-hidden="true">
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
        <path
          d="M2.25 3.6 5 6.4 7.75 3.6"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  )
}

function SortTh({
  label,
  col,
  sortKey,
  sortDir,
  align = 'left',
  onSort,
}: {
  label: string
  col: SortKey
  sortKey: SortKey
  sortDir: 'asc' | 'desc'
  align?: 'left' | 'right'
  onSort: (col: SortKey) => void
}) {
  const active = sortKey === col
  return (
    <th className={`${align === 'right' ? 'num' : ''} sortable${active ? ' sorted' : ''}`}>
      <button type="button" className="th-btn" onClick={() => onSort(col)}>
        {align === 'right' ? (
          <>
            <SortArrow dir={sortDir} active={active} />
            <span className="th-label">{label}</span>
          </>
        ) : (
          <>
            <span className="th-label">{label}</span>
            <SortArrow dir={sortDir} active={active} />
          </>
        )}
      </button>
    </th>
  )
}

function ModelCells({ m, maxCost }: { m: ModelRow; maxCost: number }) {
  return (
    <>
      <td className="model">
        <span className="model-name">{m.model}</span>
      </td>
      <td className="num">{m.request_count || '—'}</td>
      <td className="num">{tokens(m.input_tokens)}</td>
      <td className="num">{tokens(m.output_tokens)}</td>
      <td className="num">{tokens(m.cache_read_tokens)}</td>
      <td className="num cost">{money(m.cost_usd)}</td>
      <td className="bar-col">
        <div className="bar">
          <div className="fill" style={{ width: `${(m.cost_usd / maxCost) * 100}%` }} />
        </div>
      </td>
    </>
  )
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>('models')
  const [modelsView, setModelsView] = useState<ModelsView>('model')
  const [viewMenuOpen, setViewMenuOpen] = useState(false)
  const [theme, setTheme] = useState<Theme>(() => readTheme())
  const [query, setQuery] = useState('')
  const [searchFocused, setSearchFocused] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('cost_usd')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [emailBlurred, setEmailBlurred] = useState(true)
  const [eventPageSize, setEventPageSize] = useState<20 | 50 | 100>(20)
  const [eventPage, setEventPage] = useState(0)
  const [pageSizeOpen, setPageSizeOpen] = useState(false)

  const blurTimer = useRef<number | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const busyRef = useRef(false)
  const authOkRef = useRef(false)
  const pageSizeRef = useRef<HTMLDivElement>(null)
  const viewMenuRef = useRef<HTMLDivElement>(null)

  const deferredQuery = useDeferredValue(query)

  const toggleTheme = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', next)
    try {
      localStorage.setItem('burn-theme', next)
    } catch {
      // Theme still applies for this session.
    }
    setTheme(next)
  }

  useEffect(() => {
    if (!pageSizeOpen && !viewMenuOpen) return
    const onDoc = (e: MouseEvent) => {
      if (pageSizeOpen && !pageSizeRef.current?.contains(e.target as Node)) setPageSizeOpen(false)
      if (viewMenuOpen && !viewMenuRef.current?.contains(e.target as Node)) setViewMenuOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [pageSizeOpen, viewMenuOpen])

  useEffect(() => {
    if (tab !== 'events') setPageSizeOpen(false)
    if (tab !== 'models') setViewMenuOpen(false)
  }, [tab])

  const focusSearch = useCallback(() => {
    setTab((t) => t)
    searchRef.current?.focus()
    searchRef.current?.select()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      const typing = tag === 'INPUT' || tag === 'TEXTAREA'
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        focusSearch()
      }
      if (e.key === '/' && !typing) {
        e.preventDefault()
        focusSearch()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [focusSearch])

  const clearBlurTimer = () => {
    if (blurTimer.current != null) {
      window.clearTimeout(blurTimer.current)
      blurTimer.current = null
    }
  }

  const revealEmail = () => {
    clearBlurTimer()
    setEmailBlurred(false)
    blurTimer.current = window.setTimeout(() => {
      setEmailBlurred(true)
      blurTimer.current = null
    }, 10_000)
  }

  const toggleEmailBlur = () => {
    if (emailBlurred) revealEmail()
    else {
      clearBlurTimer()
      setEmailBlurred(true)
    }
  }

  useEffect(() => () => clearBlurTimer(), [])

  const refresh = useCallback(async () => {
    const [st, sum] = await Promise.all([fetchStatus(), fetchSummary(false)])
    setStatus(st)
    setSummary(sum)
    authOkRef.current = st.auth_ok
  }, [])

  useEffect(() => {
    refresh().catch((e: Error) => setError(e.message))
  }, [refresh])

  useEffect(() => {
    const beat = () => void sendHeartbeat().catch(() => undefined)
    beat()
    const id = window.setInterval(beat, HEARTBEAT_MS)
    return () => window.clearInterval(id)
  }, [])

  const onSync = useCallback(
    async (silent = false) => {
      if (busyRef.current) return
      busyRef.current = true
      if (!silent) {
        setBusy(true)
        setError(null)
      }
      try {
        await syncNow()
        await refresh()
      } catch (e) {
        if (!silent) setError(e instanceof Error ? e.message : String(e))
      } finally {
        busyRef.current = false
        if (!silent) setBusy(false)
      }
    },
    [refresh],
  )

  const didInitialSyncRef = useRef(false)
  useEffect(() => {
    if (didInitialSyncRef.current) return
    if (!status || !status.auth_ok || busy) return
    didInitialSyncRef.current = true
    // silent background refresh when we already have cached data;
    // visible sync when the DB is empty (nothing to show yet)
    void onSync(status.has_data)
  }, [status, busy, onSync])

  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      if (!authOkRef.current) return
      void onSync(true)
    }, AUTO_SYNC_MS)
    const onVis = () => {
      if (document.visibilityState === 'visible' && authOkRef.current) void onSync(true)
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [onSync])

  const modelIndex = useMemo<SearchIndex[]>(
    () =>
      (summary?.models ?? []).map((row) => ({
        row,
        n: norm(row.model),
        c: compact(row.model),
      })),
    [summary?.models],
  )

  const displayTotal = useMemo(
    () => modelIndex.reduce((s, x) => s + x.row.cost_usd, 0),
    [modelIndex],
  )

  const filteredModels = useMemo(() => {
    const q = deferredQuery.trim()
    const tokens = q ? expandTokens(q) : []
    const qNorm = q ? norm(q) : ''
    const qComp = q ? compact(q) : ''

    let scored: { row: ModelRow; score: number }[]
    if (!q) {
      scored = modelIndex.map((x) => ({ row: x.row, score: 1 }))
    } else {
      scored = []
      for (const x of modelIndex) {
        const score = scoreIndexed(x, tokens, qNorm, qComp)
        if (score > 0) scored.push({ row: x.row, score })
      }
    }

    const dir = sortDir === 'asc' ? 1 : -1
    scored.sort((a, b) => {
      if (q && sortKey === 'cost_usd' && sortDir === 'desc' && b.score !== a.score) {
        return b.score - a.score
      }
      const av = a.row[sortKey]
      const bv = b.row[sortKey]
      if (typeof av === 'string' && typeof bv === 'string') {
        return av.localeCompare(bv) * dir
      }
      return ((av as number) - (bv as number)) * dir
    })
    return scored.map((x) => x.row)
  }, [modelIndex, deferredQuery, sortKey, sortDir])

  const providerGroups = useMemo(
    () => groupModelsByProvider(filteredModels, sortKey, sortDir),
    [filteredModels, sortKey, sortDir],
  )

  const maxCost = useMemo(() => {
    if (!filteredModels.length) return 1
    let max = 0.01
    for (const m of filteredModels) if (m.cost_usd > max) max = m.cost_usd
    return max
  }, [filteredModels])

  const filteredEvents = useMemo(() => {
    const rows = summary?.events ?? []
    const q = deferredQuery.trim()
    if (!q) return rows
    const tokens = expandTokens(q)
    const qNorm = norm(q)
    const qComp = compact(q)
    return rows.filter((e) => {
      const modelIdx: SearchIndex = {
        row: {
          model: e.model,
          input_tokens: 0,
          output_tokens: 0,
          cache_read_tokens: 0,
          cache_write_tokens: 0,
          cost_cents: 0,
          cost_usd: 0,
          request_count: 0,
          tier: null,
          is_auto: false,
        },
        n: norm(e.model),
        c: compact(e.model),
      }
      if (scoreIndexed(modelIdx, tokens, qNorm, qComp) > 0) return true
      const kind = kindLabel(e.kind)
      return scoreIndexed({ ...modelIdx, n: norm(kind), c: compact(kind) }, tokens, qNorm, qComp) > 0
    })
  }, [summary?.events, deferredQuery])

  const eventPageCount = Math.max(1, Math.ceil(filteredEvents.length / eventPageSize) || 1)

  useEffect(() => {
    setEventPage(0)
  }, [deferredQuery, eventPageSize, summary?.events?.length])

  useEffect(() => {
    if (eventPage > eventPageCount - 1) setEventPage(Math.max(0, eventPageCount - 1))
  }, [eventPage, eventPageCount])

  const pagedEvents = useMemo(() => {
    const start = eventPage * eventPageSize
    return filteredEvents.slice(start, start + eventPageSize)
  }, [filteredEvents, eventPage, eventPageSize])

  const eventRangeLabel = useMemo(() => {
    if (!filteredEvents.length) return '0'
    const start = eventPage * eventPageSize + 1
    const end = Math.min(filteredEvents.length, (eventPage + 1) * eventPageSize)
    return `${start}–${end} of ${filteredEvents.length}`
  }, [filteredEvents.length, eventPage, eventPageSize])

  const email = summary?.account?.email || status?.session?.email || status?.account?.email

  const onSort = (col: SortKey) => {
    startTransition(() => {
      if (sortKey === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
      else {
        setSortKey(col)
        setSortDir(col === 'model' ? 'asc' : 'desc')
      }
    })
  }

  const modelsLabel = modelsView === 'model' ? 'By model' : 'By provider'

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <span className="mark">Burn</span>
          <span className="tag">Cursor usage</span>
        </div>
        <div className="actions">
          <button
            type="button"
            className="icon-btn"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="4.5" stroke="currentColor" strokeWidth="1.75" />
                <path
                  d="M12 2.5v2.2M12 19.3v2.2M21.5 12h-2.2M4.7 12H2.5M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6M18.7 18.7l-1.6-1.6M6.9 6.9 5.3 5.3"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M20.5 14.2A8.2 8.2 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
          <button className="sync" onClick={() => void onSync(false)} disabled={busy || !status?.auth_ok}>
            {busy ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
      </header>

      {error && <div className="banner bad">{error}</div>}
      {status && !status.auth_ok && (
        <div className="banner bad">
          No Cursor session found. Sign in to the Cursor app, then hit Sync.
          {status.auth_error ? ` (${status.auth_error})` : ''}
        </div>
      )}

      <section className="hero">
        <div className="hero-meta">
          <div className="meta-row">
            <span className="k">Account</span>
            {email ? (
              <button
                type="button"
                className={`v email-btn${emailBlurred ? ' blurred' : ''}`}
                onClick={toggleEmailBlur}
                data-tip={emailBlurred ? 'Click to reveal' : 'Click to hide'}
              >
                {email}
              </button>
            ) : (
              <span className="v">—</span>
            )}
          </div>
          <div className="meta-row">
            <span className="k">Cycle</span>
            <span className="v">{fmtRange(summary?.period?.start, summary?.period?.end)}</span>
          </div>
          <div className="meta-row">
            <span className="k">Synced</span>
            <span className="v">
              <RelativeTime ts={summary?.last_synced_at ?? status?.last_synced_at ?? null} />
            </span>
          </div>
        </div>
        <div className="total">
          <div className="total-label">Burned this cycle</div>
          <div className="total-value">{money(displayTotal)}</div>
          <div className="total-sub">
            {summary?.period?.membership && (
              <span className="plan-badge">{formatPlanLabel(summary.period.membership)}</span>
            )}
            <span>
              {modelIndex.length} model{modelIndex.length === 1 ? '' : 's'}
            </span>
            {summary?.period?.plan_usage?.apiPercentUsed != null && (
              <span>API pool {Math.round(summary.period.plan_usage.apiPercentUsed)}%</span>
            )}
          </div>
        </div>
      </section>

      {summary?.period?.display_message && (
        <p className="note">{summary.period.display_message}</p>
      )}

      <nav className="tabs">
        <div className="tab-group">
          <div className={`view-switch${tab === 'models' ? ' on' : ''}`} ref={viewMenuRef}>
            <button
              type="button"
              className="view-main"
              onClick={() => {
                setTab('models')
                setViewMenuOpen(false)
              }}
            >
              {modelsLabel}
            </button>
            <button
              type="button"
              className={`view-caret${viewMenuOpen ? ' open' : ''}`}
              aria-label="Switch models view"
              aria-haspopup="listbox"
              aria-expanded={viewMenuOpen}
              onClick={() => {
                setTab('models')
                setViewMenuOpen((v) => !v)
              }}
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
                <path
                  d="M2.25 3.6 5 6.4 7.75 3.6"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
            {viewMenuOpen && (
              <ul className="view-menu" role="listbox">
                <li>
                  <button
                    type="button"
                    role="option"
                    className={modelsView === 'model' ? 'on' : ''}
                    aria-selected={modelsView === 'model'}
                    onClick={() => {
                      setModelsView('model')
                      setTab('models')
                      setViewMenuOpen(false)
                    }}
                  >
                    By model
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    role="option"
                    className={modelsView === 'provider' ? 'on' : ''}
                    aria-selected={modelsView === 'provider'}
                    onClick={() => {
                      setModelsView('provider')
                      setTab('models')
                      setViewMenuOpen(false)
                    }}
                  >
                    By provider
                  </button>
                </li>
              </ul>
            )}
          </div>
          <button
            type="button"
            className={tab === 'events' ? 'on' : ''}
            onClick={() => setTab('events')}
          >
            Recent events
          </button>
        </div>

        <div className="tabs-tools">
          <div
            className={`search-field${searchFocused || query ? ' active' : ''}`}
            onClick={() => searchRef.current?.focus()}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.75" />
              <path d="M16.2 16.2 21 21" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
            </svg>
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setSearchFocused(false)}
              placeholder={tab === 'events' ? 'Search events' : 'Search models'}
              aria-label={tab === 'events' ? 'Search events' : 'Search models'}
            />
            {query && (
              <button
                type="button"
                className="clear-search"
                onClick={() => {
                  setQuery('')
                  searchRef.current?.focus()
                }}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>

          {tab === 'events' && filteredEvents.length > 0 && (
            <div className="pager-shell">
              <div className="pager-size-dd" ref={pageSizeRef}>
                <button
                  type="button"
                  className={`pager-size-btn${pageSizeOpen ? ' open' : ''}`}
                  onClick={() => setPageSizeOpen((v) => !v)}
                  aria-haspopup="listbox"
                  aria-expanded={pageSizeOpen}
                >
                  <span>{eventPageSize}</span>
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
                    <path
                      d="M2.25 3.6 5 6.4 7.75 3.6"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
                {pageSizeOpen && (
                  <ul className="pager-size-menu" role="listbox">
                    {([20, 50, 100] as const).map((n) => (
                      <li key={n}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={eventPageSize === n}
                          className={eventPageSize === n ? 'on' : ''}
                          onClick={() => {
                            setEventPageSize(n)
                            setPageSizeOpen(false)
                          }}
                        >
                          {n}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <span className="pager-range">{eventRangeLabel}</span>
              <div className="pager-nav">
                <button
                  type="button"
                  className="pager-arrow"
                  disabled={eventPage <= 0}
                  onClick={() => setEventPage((p) => Math.max(0, p - 1))}
                  aria-label="Newer events"
                  data-tip="Newer"
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                    <path
                      d="M7.4 2.5 3.9 6l3.5 3.5"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
                <button
                  type="button"
                  className="pager-arrow"
                  disabled={eventPage >= eventPageCount - 1}
                  onClick={() => setEventPage((p) => Math.min(eventPageCount - 1, p + 1))}
                  aria-label="Older events"
                  data-tip="Older"
                  data-tip-align="end"
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                    <path
                      d="M4.6 2.5 8.1 6l-3.5 3.5"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>
      </nav>

      {tab === 'models' && (
        <div className="table-wrap">
          <table className="models-table">
            <thead>
              <tr>
                <SortTh label="Model" col="model" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                <SortTh label="Requests" col="request_count" sortKey={sortKey} sortDir={sortDir} align="right" onSort={onSort} />
                <SortTh label="In" col="input_tokens" sortKey={sortKey} sortDir={sortDir} align="right" onSort={onSort} />
                <SortTh label="Out" col="output_tokens" sortKey={sortKey} sortDir={sortDir} align="right" onSort={onSort} />
                <SortTh label="Cache read" col="cache_read_tokens" sortKey={sortKey} sortDir={sortDir} align="right" onSort={onSort} />
                <SortTh label="Cost" col="cost_usd" sortKey={sortKey} sortDir={sortDir} align="right" onSort={onSort} />
                <th className="bar-col" />
              </tr>
            </thead>
            <tbody>
              {modelsView === 'model' &&
                filteredModels.map((m) => (
                  <tr key={m.model}>
                    <ModelCells m={m} maxCost={maxCost} />
                  </tr>
                ))}

              {modelsView === 'provider' &&
                providerGroups.map((g) => (
                  <Fragment key={g.provider.id}>
                    <tr className="provider-row">
                      <td colSpan={7}>
                        <div className="provider-head">
                          {g.provider.iconSrc ? (
                            <span className="provider-ico" aria-hidden="true">
                              <img src={g.provider.iconSrc} alt="" />
                            </span>
                          ) : (
                            <span className="provider-fallback" aria-hidden="true">
                              {g.provider.name.slice(0, 1)}
                            </span>
                          )}
                          <span className="provider-name">{g.provider.name}</span>
                          <span className="provider-meta">
                            {g.models.length} model{g.models.length === 1 ? '' : 's'} · {money(g.cost_usd)}
                          </span>
                        </div>
                      </td>
                    </tr>
                    {g.models.map((m) => (
                      <tr key={m.model} className="provider-child">
                        <ModelCells m={m} maxCost={maxCost} />
                      </tr>
                    ))}
                  </Fragment>
                ))}

              {!filteredModels.length && (
                <tr>
                  <td colSpan={7} className="empty">
                    {busy
                      ? 'Pulling usage from Cursor…'
                      : deferredQuery
                        ? 'No models match that search.'
                        : 'No data yet. Sync to load this billing cycle.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'events' && (
        <div className="table-wrap events-wrap">
          <table className="events-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Model</th>
                <th>Kind</th>
                <th className="num">In</th>
                <th className="num">Out</th>
                <th className="num">Cache</th>
                <th className="num">Cost</th>
              </tr>
            </thead>
            <tbody>
              {pagedEvents.map((e) => (
                <tr key={e.id}>
                  <td className="when">
                    {new Date(e.ts_ms).toLocaleString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </td>
                  <td className="model">
                    <span className="model-name">{e.model}</span>
                  </td>
                  <td className="kind">
                    <span className="kind-text">{kindLabel(e.kind)}</span>
                  </td>
                  <td className="num">{tokens(e.input_tokens)}</td>
                  <td className="num">{tokens(e.output_tokens)}</td>
                  <td className="num">{tokens(e.cache_read_tokens)}</td>
                  <td className="num cost">{money(e.cost_cents / 100)}</td>
                </tr>
              ))}
              {!pagedEvents.length && (
                <tr>
                  <td colSpan={7} className="empty">
                    {deferredQuery ? 'No events match that search.' : 'No events cached yet.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <footer className="foot">
        Auto-syncs every 2 min while this tab is open · stays on this machine
      </footer>
    </div>
  )
}
