import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Bar, BarChart, Cell } from 'recharts'
import { api } from '../api'
import { useAuth } from '../auth'
import { useChartColors } from '../theme'
import { useAccountPerformance, AccountPerf } from '../hooks'
import { usd, pct, nav as fmtNav, rate, shortDate, fullDate, prettyName, tone, KIND_LABEL } from '../format'
import { Card, ChartTooltip, EmptyState, KindBadge, PageHeader, Segmented, Skeleton, Sparkline, StatCard, TableWrap, DemoNote } from '../components/ui'
import { Icon } from '../components/icons'
import InvestModal, { InvestTarget } from '../components/InvestModal'

type SortKey = 'return_pct' | 'equity' | 'max_drawdown' | 'subscriber_count' | 'nav'
export const CAN_ALLOCATE = ['broker_admin', 'investor']

export default function Home() {
  const { session } = useAuth()
  const nav = useNavigate()
  const c = useChartColors()
  const { data: stats } = useQuery({ queryKey: ['platform-stats'], queryFn: api.platformStats })
  const { data: accounts, isLoading, error } = useAccountPerformance()
  const [kind, setKind] = useState<'all' | 'pamm' | 'mam' | 'copy'>('all')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'return_pct', dir: -1 })
  const [query, setQuery] = useState('')
  const [invest, setInvest] = useState<InvestTarget | null>(null)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (accounts || [])
      .filter(a => kind === 'all' || a.strategy_kind === kind)
      .filter(a => !q || [a.strategy_name, a.login, a.manager_name].some(v => v?.toLowerCase().includes(q)))
      .sort((a, b) => (Number(a[sort.key]) - Number(b[sort.key])) * sort.dir)
  }, [accounts, kind, sort, query])

  // Aggregate AUM across masters by rollover week (equity recorded after each rollover).
  const aumSeries = useMemo(() => {
    const byDay = new Map<string, number>()
    for (const a of accounts || []) for (const h of a.history) {
      if (h.equity == null || !h.date) continue
      const d = h.date.slice(0, 10)
      byDay.set(d, (byDay.get(d) || 0) + h.equity)
    }
    return [...byDay.entries()].sort(([x], [y]) => x.localeCompare(y)).map(([date, aum]) => ({ date, aum }))
  }, [accounts])

  const aumChange = aumSeries.length > 1 ? (aumSeries[aumSeries.length - 1].aum / aumSeries[0].aum - 1) * 100 : 0
  const weeklyPnl = useMemo(() => {
    const byDay = new Map<string, number>()
    for (const a of accounts || []) for (const h of a.history) {
      if (!h.date) continue
      const d = h.date.slice(0, 10)
      byDay.set(d, (byDay.get(d) || 0) + (h.pnl || 0))
    }
    return [...byDay.entries()].sort(([x], [y]) => x.localeCompare(y)).slice(-12).map(([date, pnl]) => ({ date, pnl }))
  }, [accounts])

  const best = (accounts || []).filter(a => a.weeks > 0).sort((a, b) => b.return_pct - a.return_pct)[0]
  const toggleSort = (key: SortKey) => setSort(s => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : -1 }))
  const canAllocate = !!session && CAN_ALLOCATE.includes(session.role)
  const openInvest = (a: AccountPerf) => a.strategy_id && setInvest({
    strategy_id: a.strategy_id, name: a.strategy_name || a.login, kind: a.strategy_kind, nav: a.nav, performance_fee_rate: a.performance_fee_rate,
  })

  const Th = ({ k, children, className = '' }: { k: SortKey; children: React.ReactNode; className?: string }) => (
    <th className={className}>
      <button onClick={() => toggleSort(k)} className={`inline-flex items-center gap-1 uppercase tracking-wider hover:text-fg ${sort.key === k ? 'text-fg' : ''}`}>
        {children}{sort.key === k && <Icon name={sort.dir === -1 ? 'arrowDown' : 'arrowUp'} className="w-3 h-3" />}
      </button>
    </th>
  )

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Market overview" title="Strategy marketplace"
        subtitle="Live view of every PAMM, MAM and copy strategy on the platform — NAV track records, risk and investor participation."
        actions={<span className="tag-mock self-start sm:self-auto">Simulated performance data</span>} />

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        <StatCard label="Assets under management" icon="wallet" value={stats ? usd(stats.total_aum, { decimals: 0 }) : <Skeleton className="h-7 w-32" />}
          sub={aumSeries.length > 1 ? <span><span className={tone(aumChange)}>{pct(aumChange)}</span> in {aumSeries.length} weeks, incl. net inflows</span> : 'Across active master accounts'} />
        <StatCard label="Active allocations" icon="users" value={stats?.total_active_investors ?? <Skeleton className="h-7 w-12" />} sub="Investor subscriptions" />
        <StatCard label="Strategies" icon="layers" value={stats?.total_strategies ?? <Skeleton className="h-7 w-12" />} sub={`${stats?.total_masters ?? '—'} master accounts`} />
        <StatCard label="Rollovers (30 days)" icon="refresh" value={stats?.recent_rollovers_30d ?? <Skeleton className="h-7 w-12" />}
          sub={best ? <>Top: {best.strategy_name} <span className="text-gain">{pct(best.return_pct)}</span></> : 'Settlement periods closed'} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2" title="Platform AUM" subtitle="Sum of master equity after each weekly rollover (net of performance fees)">
          {isLoading ? <Skeleton className="h-64" /> : aumSeries.length > 1 ? (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={aumSeries} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="aumFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={c.brand} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={c.brand} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={32} />
                <YAxis tickFormatter={v => usd(v, { compact: true })} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={56} domain={['auto', 'auto']} />
                <Tooltip content={<ChartTooltip labelFormat={fullDate} valueFormat={(v: number) => usd(v, { decimals: 0 })} />} />
                <Area isAnimationActive={false} type="monotone" dataKey="aum" name="AUM" stroke={c.brand} strokeWidth={2} fill="url(#aumFill)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : <EmptyState icon="chart" title="No rollover history yet" hint="Run a rollover to start building the AUM track record." />}
        </Card>
        <Card title="Weekly platform P&L" subtitle="Gross P&L allocated across all masters, last 12 periods">
          {isLoading ? <Skeleton className="h-64" /> : weeklyPnl.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={weeklyPnl} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={16} />
                <YAxis tickFormatter={v => usd(v, { compact: true })} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={52} />
                <Tooltip cursor={{ fill: c.grid, opacity: 0.5 }} content={<ChartTooltip labelFormat={fullDate} valueFormat={(v: number) => usd(v, { signed: true })} />} />
                <Bar isAnimationActive={false} dataKey="pnl" name="P&L" radius={[3, 3, 0, 0]}>
                  {weeklyPnl.map(p => <Cell key={p.date} fill={p.pnl >= 0 ? c.gain : c.loss} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState icon="chart" title="No P&L recorded" />}
        </Card>
      </div>

      <Card title="Strategy leaderboard" subtitle="Return and drawdown measured on NAV per unit since inception (base NAV 100)"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <input className="input h-8 w-44" placeholder="Search strategy or manager" value={query} onChange={e => setQuery(e.target.value)} aria-label="Search strategies" />
            <Segmented value={kind} onChange={setKind} options={[
              { value: 'all', label: 'All' }, { value: 'pamm', label: 'PAMM' }, { value: 'mam', label: 'MAM' }, { value: 'copy', label: 'Copy' },
            ]} />
          </div>
        }>
        {error ? <EmptyState icon="alert" title="Could not load strategies" hint={String((error as Error).message)} /> : isLoading ? (
          <div className="space-y-3">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-10" />)}</div>
        ) : rows.length === 0 ? (
          <EmptyState title="No strategies match" hint="Try a different filter or search term." />
        ) : (
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>Strategy</th>
                  <Th k="nav" className="text-right">NAV</Th>
                  <Th k="return_pct" className="text-right">Return</Th>
                  <Th k="max_drawdown" className="text-right">Max DD</Th>
                  <th className="w-36">26-week NAV</th>
                  <Th k="equity" className="text-right">Equity</Th>
                  <Th k="subscriber_count" className="text-right">Investors</Th>
                  <th className="text-right">Fee</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map(a => (
                  <tr key={a.master_account_id} className="cursor-pointer" onClick={() => nav(`/strategy/${a.master_account_id}`)}>
                    <td>
                      <div className="flex items-center gap-3">
                        <div className="min-w-0">
                          <div className="font-medium flex items-center gap-2">{a.strategy_name || a.login} <KindBadge kind={a.strategy_kind} /></div>
                          <div className="text-xs text-muted">{prettyName(a.manager_name)} · <span className="font-mono">{a.login}</span></div>
                        </div>
                      </div>
                    </td>
                    <td className="text-right num">{fmtNav(a.nav)}</td>
                    <td className={`text-right num font-medium ${tone(a.return_pct)}`}>{a.weeks ? pct(a.return_pct) : '—'}</td>
                    <td className="text-right num text-muted">{a.weeks ? pct(a.max_drawdown) : '—'}</td>
                    <td className="w-36"><Sparkline data={a.history} id={a.master_account_id} /></td>
                    <td className="text-right num">{usd(a.equity, { decimals: 0 })}</td>
                    <td className="text-right num">{a.subscriber_count}</td>
                    <td className="text-right num text-muted">{rate(a.performance_fee_rate)}</td>
                    <td className="text-right" onClick={e => e.stopPropagation()}>
                      {canAllocate && a.strategy_kind !== 'copy' && a.strategy_id
                        ? <button className="btn-ghost h-8 text-xs" onClick={() => openInvest(a)}>Allocate</button>
                        : <button className="btn-quiet h-8 text-xs" onClick={() => nav(`/strategy/${a.master_account_id}`)}>Details</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
        <div className="mt-4">
          <DemoNote>Track records are produced by the platform's real NAV, fee and rollover engine running on a seeded random-walk P&L from the simulated broker adapter. They are illustrative only — {Object.values(KIND_LABEL).join(' / ')} figures are not real investment results.</DemoNote>
        </div>
      </Card>

      {invest && <InvestModal target={invest} onClose={() => setInvest(null)} />}
    </div>
  )
}
