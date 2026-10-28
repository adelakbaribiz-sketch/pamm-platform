import React, { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { useAccountPerformance } from '../hooks'
import { usd, pct, nav as fmtNav, num, rate, tone, prettyName, METHOD_LABEL } from '../format'
import { Card, EmptyState, KindBadge, PageHeader, Skeleton, Sparkline, StatCard, TableWrap } from '../components/ui'
import { Icon } from '../components/icons'

export default function MoneyManagerWorkspace() {
  const { session } = useAuth()
  const { data: masters, isLoading } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const { data: subs } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  const { data: strats } = useQuery({ queryKey: ['strats'], queryFn: api.listStrategies })
  const { data: perf } = useAccountPerformance()

  // The masters API is tenant-scoped; a manager's own book is identified via the public manager field.
  const me = session?.email?.split('@')[0]
  const mine = useMemo(() => {
    const own = new Set((perf || []).filter(p => session?.role !== 'money_manager' || p.manager_name === me).map(p => p.master_account_id))
    return (masters || []).filter(m => own.has(m.id))
  }, [masters, perf, me, session?.role])

  const perfById = new Map((perf || []).map(p => [p.master_account_id, p]))
  const stratByMaster = new Map((strats || []).map(s => [s.master_account_id, s]))
  const mineIds = new Set(mine.map(m => m.id))
  const mySubs = (subs || []).filter(s => mineIds.has(s.master_account_id) && s.status === 'active')
  const aum = mine.reduce((s, m) => s + Number(m.equity), 0)
  const fees = mine.reduce((s, m) => s + (perfById.get(m.id)?.fees_collected || 0), 0)

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={session?.role === 'money_manager' ? prettyName(me) : 'All managers (admin view)'} title="Manager desk"
        subtitle="Your master accounts, investor participation and performance-fee accrual."
        actions={<Link to="/rollover" className="btn-primary"><Icon name="refresh" /> Close period</Link>} />

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        <StatCard label="Assets under management" icon="wallet" value={isLoading ? <Skeleton className="h-7 w-28" /> : usd(aum, { decimals: 0 })} sub={`${mine.length} master accounts`} />
        <StatCard label="Investor allocations" icon="users" value={mySubs.length} sub={`${new Set(mySubs.map(s => s.investor_account_id)).size} distinct investors`} />
        <StatCard label="Performance fees collected" icon="chart" value={usd(fees)} sub="Charged on gains above HWM" />
        <StatCard label="Investor capital contributed" icon="layers" value={usd(mySubs.reduce((s, x) => s + Number(x.contributed_capital), 0), { decimals: 0 })} />
      </div>

      <Card title="Master accounts" bodyClass="px-4 sm:px-5 pb-4 pt-2">
        {!isLoading && !mine.length ? <EmptyState icon="layers" title="No master accounts" action={<Link to="/masters" className="btn-primary">Create master account</Link>} /> : (
          <TableWrap>
            <table>
              <thead><tr><th>Strategy</th><th>Allocation</th><th className="w-32">NAV trend</th><th className="text-right">NAV</th><th className="text-right">Return</th><th className="text-right">Equity</th><th className="text-right">HWM</th><th className="text-right">Fee</th></tr></thead>
              <tbody>
                {mine.map(m => {
                  const p = perfById.get(m.id), s = stratByMaster.get(m.id)
                  return (
                    <tr key={m.id}>
                      <td><Link to={`/strategy/${m.id}`} className="font-medium hover:text-brand-500 flex items-center gap-2">{s?.name || m.login} {s && <KindBadge kind={s.kind} />}</Link><div className="text-xs text-muted font-mono">{m.login}</div></td>
                      <td><span className="tag-neutral">{METHOD_LABEL[m.allocation_method] || m.allocation_method}</span></td>
                      <td className="w-32">{p && <Sparkline data={p.history} id={`mm-${m.id}`} height={30} />}</td>
                      <td className="text-right num">{fmtNav(m.nav)}</td>
                      <td className={`text-right num ${tone(p?.return_pct)}`}>{p?.weeks ? pct(p.return_pct) : '—'}</td>
                      <td className="text-right num">{usd(m.equity)}</td>
                      <td className="text-right num text-muted">{usd(m.hwm)}</td>
                      <td className="text-right num">{rate(m.performance_fee_rate)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </TableWrap>
        )}
      </Card>

      <Card title="Investor participation" subtitle="Investor logins only — no personal data is shown to managers" bodyClass="px-4 sm:px-5 pb-4 pt-2">
        {!mySubs.length ? <EmptyState icon="users" title="No investors allocated yet" /> : (
          <TableWrap>
            <table>
              <thead><tr><th>Investor</th><th>Master</th><th className="text-right">Units</th><th className="text-right">Contributed</th><th className="text-right">Value (GAV)</th><th className="text-right">P&L</th><th className="text-right">Share of master</th></tr></thead>
              <tbody>
                {mySubs.map(s => {
                  const m = mine.find(x => x.id === s.master_account_id)
                  const share = m && Number(m.total_units) ? Number(s.units) / Number(m.total_units) * 100 : 0
                  return (
                    <tr key={s.id}>
                      <td className="font-mono text-xs">{s.investor_login}</td>
                      <td className="font-mono text-xs text-muted">{s.master_login}</td>
                      <td className="text-right num">{num(s.units, 4)}</td>
                      <td className="text-right num">{usd(s.contributed_capital)}</td>
                      <td className="text-right num">{usd(s.current_gav)}</td>
                      <td className={`text-right num ${tone(s.unrealized_pnl)}`}>{usd(s.unrealized_pnl, { signed: true })}</td>
                      <td className="text-right num text-muted">{share.toFixed(1)}%</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </TableWrap>
        )}
      </Card>
    </div>
  )
}
