export type ModelRow = {
  model: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  cost_cents: number
  cost_usd: number
  request_count: number
  tier: number | null
  is_auto: boolean
}

export type EventRow = {
  id: string
  ts_ms: number
  model: string
  kind: string | null
  cost_cents: number
  input_tokens: number
  output_tokens: number
}

export type Summary = {
  account: {
    email?: string
  } | null
  period: {
    start?: string
    end?: string
    membership?: string
    display_message?: string
    auto_message?: string
    plan_usage?: {
      totalSpend?: number
      includedSpend?: number
      bonusSpend?: number
      limit?: number
      apiPercentUsed?: number
      autoPercentUsed?: number
      totalPercentUsed?: number
    }
    total_cost_cents?: number
  } | null
  last_synced_at: number | null
  api_only: boolean
  total_cost_cents: number
  total_cost_usd: number
  models: ModelRow[]
  events: EventRow[]
}

export type Status = {
  auth_ok: boolean
  auth_error: string | null
  session: { email?: string | null } | null
  account: Summary['account']
  period: Summary['period']
  last_synced_at: number | null
  has_data: boolean
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json()
}

export function fetchStatus() {
  return fetch('/api/status', { cache: 'no-store' }).then((r) => json<Status>(r))
}

export function fetchSummary(apiOnly: boolean) {
  return fetch(`/api/summary?api_only=${apiOnly}`, { cache: 'no-store' }).then((r) => json<Summary>(r))
}

export function syncNow() {
  return fetch('/api/sync', { method: 'POST', headers: { 'X-Burn-Request': '1' } }).then((r) =>
    json<{ ok: boolean; models: number; events: number; total_cost_cents: number }>(r),
  )
}

export function sendHeartbeat() {
  return fetch('/api/heartbeat', {
    method: 'POST',
    headers: { 'X-Burn-Request': '1' },
    cache: 'no-store',
  })
}
