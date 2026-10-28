// Shared number/label formatting. API values arrive as decimal strings.

const toNum = (v: unknown) => {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

export function usd(v: unknown, opts: { decimals?: number; compact?: boolean; signed?: boolean } = {}) {
  const n = toNum(v)
  const { decimals = 2, compact = false, signed = false } = opts
  const s = new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
    notation: compact ? 'compact' : 'standard',
    minimumFractionDigits: compact ? 0 : decimals,
    maximumFractionDigits: compact ? 1 : decimals,
  }).format(Math.abs(n))
  if (n < 0) return `−${s}`
  return signed && n > 0 ? `+${s}` : s
}

export function pct(v: unknown, opts: { decimals?: number; signed?: boolean } = {}) {
  const n = toNum(v)
  const { decimals = 2, signed = true } = opts
  const s = Math.abs(n).toFixed(decimals)
  if (n < 0) return `−${s}%`
  return signed && n > 0 ? `+${s}%` : `${s}%`
}

export const num = (v: unknown, decimals = 2) =>
  new Intl.NumberFormat('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(toNum(v))

export const nav = (v: unknown) => num(v, 4)

export const rate = (v: unknown) => `${(toNum(v) * 100).toFixed(toNum(v) * 100 % 1 ? 1 : 0)}%`

export const tone = (v: unknown) => (toNum(v) > 0 ? 'text-gain' : toNum(v) < 0 ? 'text-loss' : 'text-muted')

export const shortDate = (v?: string | null) =>
  v ? new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''

export const fullDate = (v?: string | null) =>
  v ? new Date(v).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '—'

/** "atlas.quant" → "Atlas Quant" (manager names are email local-parts in the API). */
export const prettyName = (s?: string | null) =>
  (s || 'Unknown').split(/[._-]+/).filter(Boolean).map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

export const initials = (s?: string | null) =>
  prettyName(s).split(' ').map(w => w[0]).slice(0, 2).join('')

export const ROLE_LABEL: Record<string, string> = {
  broker_admin: 'Broker Admin', money_manager: 'Money Manager', investor: 'Investor',
  compliance: 'Compliance', super_admin: 'Super Admin',
}

export const KIND_LABEL: Record<string, string> = { pamm: 'PAMM', mam: 'MAM', copy: 'Copy' }

export const METHOD_LABEL: Record<string, string> = {
  euro_days: 'Euro-days', start_capital: 'Start capital', end_capital: 'End capital',
}

/** Peak-to-trough decline of a NAV series, as a negative percentage (0 if none). */
export function maxDrawdown(series: number[]) {
  let peak = -Infinity, mdd = 0
  for (const v of series) {
    if (v > peak) peak = v
    if (peak > 0) mdd = Math.min(mdd, (v - peak) / peak)
  }
  return mdd * 100
}

export function errorMessage(e: unknown) {
  const m = e instanceof Error ? e.message : String(e)
  try {
    const d = JSON.parse(m)
    if (d?.code) return `${String(d.code).replace(/_/g, ' ')}`
  } catch { /* not JSON */ }
  return m
}
