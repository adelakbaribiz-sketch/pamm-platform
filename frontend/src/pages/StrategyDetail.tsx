import React, { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useAuth } from '../auth'
import { useChartColors } from '../theme'
import { useAccountPerformance } from '../hooks'
import { usd, pct, nav as fmtNav, rate, shortDate, fullDate, prettyName, tone, maxDrawdown, METHOD_LABEL } from '../format'
import { Card, ChartTooltip, EmptyState, KindBadge, PageHeader, Segmented, Skeleton, StatCard, TableWrap, DemoNote } from '../components/ui'
import { Icon } from '../components/icons'
import InvestModal from '../components/InvestModal'
import { CAN_ALLOCATE } from './Home'

type Range = '4' | '12' | '26' | 'all'

export default function StrategyDetail() {
  const { masterId } = useParams()
  const { session } = useAuth()
  const c = useChartColors()
  const { data: accounts, isLoading } = useAccountPerformance()
  const [range, setRange] = useState<Range>('all')
  const [investOpen, setInvestOpen] = useState(false)
  const a = accounts?.find(x => x.master_account_id === masterId)

  const series = useMemo(() => {
    if (!a) return []
    const h = range === 'all' ? a.history : a.history.slice(-Number(range))
    return h.map(p => ({ ...p, date: p.date.slice(0, 10) }))
  }, [a, range])

  const drawdown = useMemo(() => {
    let peak = -Infinity
    return series.map(p => { peak = Math.max(peak, p.nav); return { date: p.date, dd: peak > 0 ? (p.nav / peak - 1) * 100 : 0 } })
  }, [series])

  if (isLoading) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-80" /></div>
  if (!a) return <div className="card"><EmptyState title="Strategy not found" action={<Link to="/" className="btn-primary">Back to marketplace</Link>} /></div>

  // Measure the window from the NAV just before it (base NAV for "All"), so "All" matches since-inception.
  const baseNav = Number((a as any).base_nav) || 100
  const startNav = range === 'all' || a.history.length <= series.length
    ? baseNav : a.history[a.history.length - series.length - 1].nav
  const last = series[series.length - 1]?.nav
  const periodReturn = last ? (last / startNav - 1) * 100 : 0
  const periodDd = maxDrawdown([startNav, ...series.map(s => s.nav)])
  const wins = series.filter(s => s.pnl > 0).length
  const canAllocate = !!session && CAN_ALLOCATE.includes(session.role) && a.strategy_kind !== 'copy' && !!a.strategy_id

  return (
    <div className="space-y-6">
      <Link to="/" className="inline-flex items-center gap-1 text-xs text-muted hover:text-fg"><Icon name="chevronLeft" className="w-3.5 h-3.5" /> Strategy marketplace</Link>
      <PageHeader eyebrow={`${prettyName(a.manager_name)} · ${a.login}`} title={a.strategy_name || a.login}
        subtitle={<span className="inline-flex flex-wrap items-center gap-2"><KindBadge kind={a.strategy_kind} />
          <span>{METHOD_LABEL[a.allocation_method] || a.allocation_method} allocation · {rate(a.performance_fee_rate)} performance fee over HWM · {a.currency}</span></span>}
        actions={<>
          <Segmented value={range} onChange={setRange} options={[{ value: '4', label: '1M' }, { value: '12', label: '3M' }, { value: '26', label: '6M' }, { value: 'all', label: 'All' }]} />
          {canAllocate && <button className="btn-primary" onClick={() => setInvestOpen(true)}><Icon name="plus" /> Allocate</button>}
        </>} />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4">
        <StatCard label="NAV per unit" value={fmtNav(a.nav)} sub="Base NAV 100.0000" />
        <StatCard label="Return (period)" value={pct(periodReturn)} tone={tone(periodReturn)} sub={`Since inception ${pct(a.return_pct)}`} />
        <StatCard label="Max drawdown (period)" value={pct(periodDd)} tone={periodDd < 0 ? 'text-loss' : ''} sub={`Since inception ${pct(a.max_drawdown)}`} />
        <StatCard label="Master equity" value={usd(a.equity, { decimals: 0 })} sub={`${a.subscriber_count} active investors`} />
        <StatCard label="Fees collected" value={usd(a.fees_collected)} sub={series.length ? `${wins}/${series.length} positive weeks` : 'No periods'} />
      </div>

      {series.length < 2 ? (
        <div className="card"><EmptyState icon="chart" title="Not enough history" hint="This master needs at least two rollovers to chart a track record." /></div>
      ) : (
        <>
          <Card title="NAV per unit" subtitle="Net asset value after each weekly rollover">
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="navFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={c.brand} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={c.brand} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={32} />
                <YAxis stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={48} domain={['auto', 'auto']} tickFormatter={v => Number(v).toFixed(1)} />
                <Tooltip content={<ChartTooltip labelFormat={fullDate} valueFormat={(v: number) => fmtNav(v)} />} />
                <ReferenceLine y={100} stroke={c.axis} strokeDasharray="3 3" />
                <Area isAnimationActive={false} type="monotone" dataKey="nav" name="NAV" stroke={c.brand} strokeWidth={2} fill="url(#navFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Weekly P&L" subtitle="Gross master P&L allocated to investors per rollover">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={series} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={c.grid} vertical={false} />
                  <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={24} />
                  <YAxis tickFormatter={v => usd(v, { compact: true })} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={52} />
                  <Tooltip cursor={{ fill: c.grid, opacity: 0.5 }} content={<ChartTooltip labelFormat={fullDate} valueFormat={(v: number) => usd(v, { signed: true })} />} />
                  <Bar isAnimationActive={false} dataKey="pnl" name="P&L" radius={[3, 3, 0, 0]}>{series.map(p => <Cell key={p.date} fill={p.pnl >= 0 ? c.gain : c.loss} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
            <Card title="Drawdown" subtitle="Decline from running NAV peak">
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={drawdown} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={c.grid} vertical={false} />
                  <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={24} />
                  <YAxis tickFormatter={v => `${Number(v).toFixed(1)}%`} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={48} />
                  <Tooltip content={<ChartTooltip labelFormat={fullDate} valueFormat={(v: number) => pct(v)} />} />
                  <Area isAnimationActive={false} type="monotone" dataKey="dd" name="Drawdown" stroke={c.loss} strokeWidth={1.6} fill={c.loss} fillOpacity={0.15} />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <Card title="Rollover history" subtitle="Most recent first">
            <TableWrap>
              <table>
                <thead><tr><th>Period end</th><th className="text-right">NAV after</th><th className="text-right">Period P&L</th><th className="text-right">Cumulative P&L</th><th className="text-right">Performance fee</th><th className="text-right">Equity after</th></tr></thead>
                <tbody>
                  {[...series].reverse().slice(0, 12).map(p => (
                    <tr key={p.date}>
                      <td>{fullDate(p.date)}</td>
                      <td className="text-right num">{fmtNav(p.nav)}</td>
                      <td className={`text-right num ${tone(p.pnl)}`}>{usd(p.pnl, { signed: true })}</td>
                      <td className={`text-right num ${tone(p.cumulative_pnl)}`}>{usd(p.cumulative_pnl, { signed: true })}</td>
                      <td className="text-right num text-muted">{p.total_fee ? usd(p.total_fee) : '—'}</td>
                      <td className="text-right num">{p.equity != null ? usd(p.equity, { decimals: 0 }) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </Card>
        </>
      )}
      <DemoNote>Simulated track record generated by the demo broker adapter. Past performance — real or simulated — does not indicate future results.</DemoNote>
      {investOpen && a.strategy_id && (
        <InvestModal target={{ strategy_id: a.strategy_id, name: a.strategy_name || a.login, kind: a.strategy_kind, nav: a.nav, performance_fee_rate: a.performance_fee_rate }}
          onClose={() => setInvestOpen(false)} />
      )}
    </div>
  )
}
