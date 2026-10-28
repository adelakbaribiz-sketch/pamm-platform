import React, { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { useAuth } from '../auth'
import { useChartColors } from '../theme'
import { usd, nav as fmtNav, rate, ROLE_LABEL, METHOD_LABEL, KIND_LABEL } from '../format'
import { Card, ChartTooltip, EmptyState, PageHeader, Skeleton, StatCard, TableWrap } from '../components/ui'
import { Icon } from '../components/icons'

export default function BrokerDashboard() {
  const { session } = useAuth()
  const c = useChartColors()
  const { data: masters, isLoading } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const { data: subs } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  const { data: strats } = useQuery({ queryKey: ['strats'], queryFn: api.listStrategies })
  const { data: sagas } = useQuery({ queryKey: ['sagas'], queryFn: api.listSagas })
  const { data: alerts } = useQuery({ queryKey: ['alerts'], queryFn: api.listAllocationAlerts })
  const { data: outboxStats } = useQuery({ queryKey: ['outbox-stats'], queryFn: api.outboxStats })
  const { data: audit } = useQuery({ queryKey: ['audit'], queryFn: api.verifyAudit })
  const { data: adapters } = useQuery({ queryKey: ['adapters'], queryFn: api.listAdapters })

  const totalEquity = (masters || []).reduce((s, m) => s + Number(m.equity), 0)
  const activeSubs = (subs || []).filter(s => s.status === 'active')
  const invested = activeSubs.reduce((s, x) => s + Number(x.contributed_capital), 0)
  const openAlerts = (alerts || []).filter(a => !a.acknowledged).length
  const stratByMaster = useMemo(() => new Map((strats || []).map(s => [s.master_account_id, s])), [strats])

  const equityBars = (masters || []).map(m => ({ login: m.login, equity: Number(m.equity) })).sort((a, b) => b.equity - a.equity)
  const mix = ['pamm', 'mam', 'copy'].map(k => ({
    kind: KIND_LABEL[k],
    value: (masters || []).filter(m => stratByMaster.get(m.id)?.kind === k).reduce((s, m) => s + Number(m.equity), 0),
  })).filter(x => x.value > 0)
  const liveAdapters = (adapters || []).filter((a: any) => a.is_live).length

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={`${ROLE_LABEL[session?.role || ''] || ''} · Demo Broker Ltd`} title="Broker dashboard"
        subtitle="Book-level view of master accounts, investor capital and back-office health."
        actions={<>
          <Link to="/rollover" className="btn-ghost"><Icon name="refresh" /> Run rollover</Link>
          <Link to="/masters" className="btn-primary"><Icon name="plus" /> New master</Link>
        </>} />

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        <StatCard label="Total master equity" icon="wallet" value={isLoading ? <Skeleton className="h-7 w-28" /> : usd(totalEquity, { decimals: 0 })} sub={`${masters?.length ?? 0} master accounts`} />
        <StatCard label="Investor capital contributed" icon="users" value={usd(invested, { decimals: 0 })} sub={`${activeSubs.length} active subscriptions`} />
        <StatCard label="Unacknowledged risk alerts" icon="alert" value={openAlerts} tone={openAlerts ? 'text-caution' : ''} sub={<Link to="/allocation" className="hover:text-fg">View allocation alerts →</Link>} />
        <StatCard label="Audit chain" icon="shield" value={audit ? (audit.verified ? 'Intact' : 'Broken') : '—'} tone={audit?.verified ? 'text-gain' : audit ? 'text-loss' : ''} sub="Hash-chained audit log verification" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2" title="Equity by master account" subtitle="Current equity per master (simulated broker)">
          {equityBars.length ? (
            <ResponsiveContainer width="100%" height={330}>
              <BarChart data={equityBars} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="login" stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} interval={0} />
                <YAxis tickFormatter={v => usd(v, { compact: true })} stroke={c.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={56} />
                <Tooltip cursor={{ fill: c.grid, opacity: 0.5 }} content={<ChartTooltip valueFormat={(v: number) => usd(v, { decimals: 0 })} />} />
                <Bar isAnimationActive={false} dataKey="equity" name="Equity" fill={c.brand} radius={[4, 4, 0, 0]} maxBarSize={56} />
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState title="No master accounts" />}
        </Card>
        <div className="space-y-4">
        <Card title="Equity by product" subtitle="PAMM / MAM / Copy split">
          {mix.length ? (
            <div className="w-full">
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie isAnimationActive={false} data={mix} dataKey="value" nameKey="kind" innerRadius={52} outerRadius={78} paddingAngle={2} stroke="none">
                    {mix.map((_, i) => <Cell key={i} fill={c.series[i]} />)}
                  </Pie>
                  <Tooltip content={<ChartTooltip valueFormat={(v: number) => usd(v, { decimals: 0 })} />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="w-full space-y-1.5 mt-2">
                {mix.map((m, i) => (
                  <div key={m.kind} className="flex items-center gap-2 text-sm">
                    <span className="w-2.5 h-2.5 rounded-sm" style={{ background: c.series[i] }} />
                    <span className="text-muted">{m.kind}</span>
                    <span className="ml-auto num">{usd(m.value, { decimals: 0 })}</span>
                    <span className="w-12 text-right text-xs text-subtle num">{(m.value / totalEquity * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          ) : <EmptyState title="No funded strategies" />}
        </Card>
        <Card title="Back-office health">
          <ul className="space-y-3 text-sm">
            <Health label="Broker connectivity" value={liveAdapters ? `${liveAdapters} live` : 'Simulated only'} state={liveAdapters ? 'ok' : 'demo'} to="/adapters" />
            <Health label="Outbox pending" value={outboxStats?.pending ?? 0} state={outboxStats?.pending ? 'warn' : 'ok'} to="/outbox" />
            <Health label="Outbox delivered" value={outboxStats?.delivered ?? 0} state="ok" to="/outbox" />
            <Health label="Dead-letter events" value={outboxStats?.dead_letter ?? 0} state={outboxStats?.dead_letter ? 'bad' : 'ok'} to="/outbox" />
            <Health label="Settlement sagas" value={sagas?.length ?? 0} state="ok" to="/sagas" />
            <Health label="Audit chain" value={audit?.verified ? 'Verified' : 'Check'} state={audit?.verified ? 'ok' : 'bad'} to="/settlement" />
          </ul>
        </Card>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-3" title="Master accounts" bodyClass="px-4 sm:px-5 pb-4 pt-2">
          <TableWrap>
            <table>
              <thead><tr><th>Login</th><th>Strategy</th><th>Allocation</th><th className="text-right">Equity</th><th className="text-right">NAV</th><th className="text-right">HWM</th><th className="text-right">Perf. fee</th></tr></thead>
              <tbody>
                {(masters || []).map(m => {
                  const s = stratByMaster.get(m.id)
                  return (
                    <tr key={m.id}>
                      <td className="font-mono text-xs">{m.login}</td>
                      <td>{s?.name || <span className="text-subtle">—</span>}</td>
                      <td><span className="tag-neutral">{METHOD_LABEL[m.allocation_method] || m.allocation_method}</span></td>
                      <td className="text-right num">{usd(m.equity)}</td>
                      <td className="text-right num">{fmtNav(m.nav)}</td>
                      <td className="text-right num text-muted">{usd(m.hwm)}</td>
                      <td className="text-right num">{rate(m.performance_fee_rate)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </TableWrap>
        </Card>

      </div>
    </div>
  )
}

function Health({ label, value, state, to }: { label: string; value: React.ReactNode; state: 'ok' | 'warn' | 'bad' | 'demo'; to: string }) {
  const dot = { ok: 'bg-gain', warn: 'bg-caution', bad: 'bg-loss', demo: 'bg-violet-500' }[state]
  return (
    <li>
      <Link to={to} className="flex items-center gap-2 hover:text-fg">
        <span className={`w-2 h-2 rounded-full ${dot}`} />
        <span className="text-muted">{label}</span>
        <span className="ml-auto font-medium num">{value}</span>
      </Link>
    </li>
  )
}
