import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip, Line, LineChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { useAuth } from '../auth'
import { useChartColors } from '../theme'
import { useAccountPerformance } from '../hooks'
import { usd, pct, nav as fmtNav, num, fullDate, shortDate, tone, prettyName } from '../format'
import { Card, ChartTooltip, EmptyState, KindBadge, PageHeader, Skeleton, StatCard, TableWrap, DemoNote } from '../components/ui'
import { Icon } from '../components/icons'

export default function InvestorWorkspace() {
  const { session } = useAuth()
  const c = useChartColors()
  const { data: subs, isLoading } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  const { data: strats } = useQuery({ queryKey: ['strats'], queryFn: api.listStrategies })
  const { data: perf } = useAccountPerformance()
  const [focus, setFocus] = useState<string | null>(null)

  const holdings = useMemo(() => (subs || []).filter(s => s.status === 'active').map(s => {
    const strat = (strats || []).find(x => x.id === s.strategy_id)
    const p = (perf || []).find(x => x.master_account_id === s.master_account_id)
    const value = Number(s.current_gav), invested = Number(s.contributed_capital)
    return { ...s, strat, perf: p, value, invested, pnl: value - invested, ret: invested ? (value / invested - 1) * 100 : 0 }
  }).sort((a, b) => b.value - a.value), [subs, strats, perf])

  const totals = holdings.reduce((t, h) => ({ value: t.value + h.value, invested: t.invested + h.invested }), { value: 0, invested: 0 })
  const pnl = totals.value - totals.invested
  const ret = totals.invested ? (totals.value / totals.invested - 1) * 100 : 0
  const isInvestor = session?.role === 'investor'

  const focused = holdings.find(h => h.id === focus) || holdings[0]
  const navSeries = (focused?.perf?.history || []).map((h: { date: string; nav: number }) => ({ date: h.date.slice(0, 10), nav: h.nav }))

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={isInvestor ? prettyName(session?.email?.split('@')[0]) : 'All investors (admin view)'} title="My portfolio"
        subtitle="Your allocations across PAMM and MAM strategies, valued at the latest NAV."
        actions={<Link to="/" className="btn-primary"><Icon name="plus" /> New allocation</Link>} />

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        <StatCard label="Portfolio value" icon="wallet" value={isLoading ? <Skeleton className="h-7 w-28" /> : usd(totals.value)} sub="Units × current NAV (GAV)" />
        <StatCard label="Capital contributed" icon="layers" value={usd(totals.invested)} sub={`${holdings.length} allocations`} />
        <StatCard label="Unrealized P&L" icon="chart" value={usd(pnl, { signed: true })} tone={tone(pnl)} sub="Net of performance fees charged" />
        <StatCard label="Return on contributed" icon="target" value={pct(ret)} tone={tone(ret)} sub="Since each subscription" />
      </div>

      {!isLoading && !holdings.length ? (
        <div className="card"><EmptyState icon="wallet" title="No allocations yet" hint="Browse the strategy marketplace to allocate capital to a manager."
          action={<Link to="/" className="btn-primary">Explore strategies</Link>} /></div>
      ) : (
        <>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Card title="Allocation" subtitle="Share of portfolio value">
              <ResponsiveContainer width="100%" height={190}>
                <PieChart>
                  <Pie isAnimationActive={false} data={holdings} dataKey="value" nameKey="master_login" innerRadius={56} outerRadius={84} paddingAngle={2} stroke="none">
                    {holdings.map((_, i) => <Cell key={i} fill={c.series[i % c.series.length]} />)}
                  </Pie>
                  <Tooltip content={<ChartTooltip valueFormat={(v: number) => usd(v)} />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-2">
                {holdings.map((h, i) => (
                  <div key={h.id} className="flex items-center gap-2 text-sm">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: c.series[i % c.series.length] }} />
                    <span className="text-muted truncate">{h.strat?.name || h.master_login}</span>
                    <span className="ml-auto text-xs text-subtle num">{(h.value / totals.value * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </Card>
            <Card className="xl:col-span-2" title={`NAV history · ${focused?.strat?.name || focused?.master_login || ''}`} subtitle="Select a holding below to switch">
              {navSeries.length > 1 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={navSeries} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke={c.grid} vertical={false} />
                    <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={32} />
                    <YAxis domain={['auto', 'auto']} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={44} tickFormatter={v => Number(v).toFixed(0)} />
                    <Tooltip content={<ChartTooltip labelFormat={fullDate} valueFormat={(v: number) => fmtNav(v)} />} />
                    <Line isAnimationActive={false} type="monotone" dataKey="nav" name="NAV" stroke={c.brand} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : <EmptyState icon="chart" title="No NAV history for this strategy yet" />}
            </Card>
          </div>

          <Card title="Holdings" bodyClass="px-4 sm:px-5 pb-4 pt-2">
            <TableWrap>
              <table>
                <thead><tr><th>Strategy</th>{!isInvestor && <th>Investor</th>}<th>Since</th><th className="text-right">Units</th><th className="text-right">NAV</th><th className="text-right">Contributed</th><th className="text-right">Value</th><th className="text-right">P&L</th><th className="text-right">HWM</th><th /></tr></thead>
                <tbody>
                  {holdings.map(h => (
                    <tr key={h.id} className={`cursor-pointer ${focused?.id === h.id ? 'bg-raised' : ''}`} onClick={() => setFocus(h.id)}>
                      <td><div className="font-medium flex items-center gap-2">{h.strat?.name || h.master_login} {h.strat && <KindBadge kind={h.strat.kind} />}</div><div className="text-xs text-muted font-mono">{h.master_login}</div></td>
                      {!isInvestor && <td className="font-mono text-xs">{h.investor_login}</td>}
                      <td className="text-muted">{fullDate(h.subscribed_at)}</td>
                      <td className="text-right num">{num(h.units, 4)}</td>
                      <td className="text-right num">{fmtNav(h.current_nav)}</td>
                      <td className="text-right num">{usd(h.invested)}</td>
                      <td className="text-right num font-medium">{usd(h.value)}</td>
                      <td className={`text-right num ${tone(h.pnl)}`}>{usd(h.pnl, { signed: true })}<div className="text-[11px]">{pct(h.ret)}</div></td>
                      <td className="text-right num text-muted">{usd(h.hwm)}</td>
                      <td className="text-right" onClick={e => e.stopPropagation()}>{h.perf && <Link to={`/strategy/${h.master_account_id}`} className="btn-quiet h-8 text-xs">Details</Link>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </Card>
        </>
      )}
      <div className="grid sm:grid-cols-2 gap-3">
        <DemoNote>Deposits and withdrawals to the investor wallet are not implemented in this prototype — allocations are funded directly from the simulated trading account.</DemoNote>
        <DemoNote>Per-rollover statements with Merkle inclusion proofs are available under <Link to="/settlement" className="text-brand-500 underline">Settlement &amp; proofs</Link>.</DemoNote>
      </div>
    </div>
  )
}
