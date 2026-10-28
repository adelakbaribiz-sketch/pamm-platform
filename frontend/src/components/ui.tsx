import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer, YAxis } from 'recharts'
import { Icon, IconName } from './icons'
import { useChartColors } from '../theme'

export function PageHeader({ title, subtitle, actions, eyebrow }:
  { title: string; subtitle?: React.ReactNode; actions?: React.ReactNode; eyebrow?: string }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between mb-6">
      <div className="min-w-0">
        {eyebrow && <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-500 mb-1">{eyebrow}</div>}
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted mt-1 max-w-3xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2 shrink-0">{actions}</div>}
    </div>
  )
}

export function StatCard({ label, value, sub, icon, tone }:
  { label: string; value: React.ReactNode; sub?: React.ReactNode; icon?: IconName; tone?: string }) {
  return (
    <div className="card p-4 sm:p-5">
      <div className="flex items-center justify-between text-muted">
        <span className="text-xs font-medium">{label}</span>
        {icon && <span className="w-7 h-7 rounded-lg bg-raised border border-line grid place-items-center"><Icon name={icon} className="w-3.5 h-3.5" /></span>}
      </div>
      <div className={`stat-value mt-2 text-2xl font-semibold tracking-tight ${tone || ''}`}>{value}</div>
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  )
}

export function Card({ title, subtitle, actions, children, className = '', bodyClass = 'p-4 sm:p-5' }:
  { title?: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 px-4 sm:px-5 pt-4 sm:pt-5">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p className="text-xs text-muted mt-0.5">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}

/** Horizontal scroll wrapper so wide tables never break the page on mobile. */
export const TableWrap = ({ children }: { children: React.ReactNode }) => (
  <div className="overflow-x-auto -mx-4 sm:-mx-5 px-1">{children}</div>
)

export function EmptyState({ icon = 'inbox', title, hint, action }:
  { icon?: IconName; title: string; hint?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-10 px-4">
      <div className="w-10 h-10 rounded-xl bg-raised border border-line grid place-items-center text-subtle mb-3">
        <Icon name={icon} className="w-5 h-5" />
      </div>
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="text-xs text-muted mt-1 max-w-sm">{hint}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export const Skeleton = ({ className = 'h-4 w-full' }: { className?: string }) => (
  <div className={`animate-pulse rounded-md bg-raised ${className}`} />
)

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <div className="flex items-start gap-2 rounded-lg border border-loss/30 bg-loss/5 px-3 py-2 text-sm text-loss">
      <Icon name="alert" className="w-4 h-4 mt-0.5 shrink-0" />
      <span>{error instanceof Error ? error.message : String(error)}</span>
    </div>
  )
}

export function DemoNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-violet-500/25 bg-violet-500/5 px-3 py-2 text-xs text-muted">
      <Icon name="info" className="w-4 h-4 text-violet-500 shrink-0" />
      <span>{children}</span>
    </div>
  )
}

export function Modal({ title, subtitle, onClose, children, width = 'max-w-md' }:
  { title: string; subtitle?: string; onClose: () => void; children: React.ReactNode; width?: string }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-[2px] p-0 sm:p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className={`card shadow-pop w-full ${width} rounded-b-none sm:rounded-b-xl max-h-[90vh] overflow-y-auto`}
        onClick={e => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-3">
          <div>
            <h3 className="font-semibold">{title}</h3>
            {subtitle && <p className="text-xs text-muted mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="btn-quiet h-8 w-8 px-0" aria-label="Close"><Icon name="x" /></button>
        </div>
        <div className="px-5 pb-5">{children}</div>
      </div>
    </div>
  )
}

export function Field({ label, error, hint, children }:
  { label: string; error?: string | false; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {error ? <span className="block text-xs text-loss mt-1">{error}</span>
        : hint ? <span className="block text-xs text-subtle mt-1">{hint}</span> : null}
    </label>
  )
}

export function Segmented<T extends string>({ value, options, onChange }:
  { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="seg" role="group">
      {options.map(o => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  )
}

export function KindBadge({ kind }: { kind: string }) {
  const cls = kind === 'pamm' ? 'tag-info' : kind === 'mam' ? 'tag-warn' : 'tag-mock'
  return <span className={cls}>{kind.toUpperCase()}</span>
}

export function Change({ value, suffix = '%' }: { value: number; suffix?: string }) {
  const up = value > 0, down = value < 0
  return (
    <span className={`inline-flex items-center gap-0.5 font-medium num ${up ? 'text-gain' : down ? 'text-loss' : 'text-muted'}`}>
      {up && <Icon name="arrowUp" className="w-3 h-3" />}
      {down && <Icon name="arrowDown" className="w-3 h-3" />}
      {Math.abs(value).toFixed(2)}{suffix}
    </span>
  )
}

export function Sparkline({ data, dataKey = 'nav', height = 36, id }:
  { data: any[]; dataKey?: string; height?: number; id: string }) {
  const c = useChartColors()
  if (!data || data.length < 2) return <div style={{ height }} className="text-[11px] text-subtle flex items-center">No history</div>
  const up = Number(data[data.length - 1][dataKey]) >= Number(data[0][dataKey])
  const color = up ? c.gain : c.loss
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
        <defs>
          <linearGradient id={`sp-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={['dataMin', 'dataMax']} />
        <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.6} fill={`url(#sp-${id})`} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function ChartTooltip({ active, payload, label, labelFormat, valueFormat }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="card shadow-pop px-3 py-2 text-xs">
      <div className="text-muted mb-1">{labelFormat ? labelFormat(label) : label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color || p.stroke || p.fill }} />
          <span className="text-muted">{p.name}</span>
          <span className="ml-auto font-medium num">{valueFormat ? valueFormat(p.value, p.dataKey) : p.value}</span>
        </div>
      ))}
    </div>
  )
}

// --- Toasts -------------------------------------------------------------
type Toast = { id: number; text: string; kind: 'ok' | 'error' | 'info' }
const ToastCtx = createContext<(text: string, kind?: Toast['kind']) => void>(() => {})

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((text: string, kind: Toast['kind'] = 'ok') => {
    const id = Date.now() + Math.random()
    setItems(t => [...t, { id, text, kind }])
    setTimeout(() => setItems(t => t.filter(x => x.id !== id)), 4500)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 w-[calc(100%-2rem)] max-w-sm" aria-live="polite">
        {items.map(t => (
          <div key={t.id} className="card shadow-pop px-4 py-3 text-sm flex items-start gap-2">
            <Icon name={t.kind === 'error' ? 'alert' : t.kind === 'info' ? 'info' : 'check'}
              className={`w-4 h-4 mt-0.5 shrink-0 ${t.kind === 'error' ? 'text-loss' : t.kind === 'info' ? 'text-brand-500' : 'text-gain'}`} />
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
