import React, { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAccountPerformance } from '../hooks'
import { usd, pct, nav as fmtNav, prettyName, initials, tone } from '../format'
import { Card, EmptyState, KindBadge, PageHeader, Skeleton, Sparkline, StatCard, DemoNote } from '../components/ui'
import { Icon } from '../components/icons'

export default function Managers() {
  const { data: managers, isLoading, error } = useQuery({ queryKey: ['public-managers'], queryFn: () => api.publicManagers(20) })
  const { data: perf } = useAccountPerformance()
  const perfByLogin = useMemo(() => new Map((perf || []).map(p => [p.login, p])), [perf])

  const totals = useMemo(() => ({
    aum: (managers || []).reduce((s: number, m: any) => s + Number(m.total_aum), 0),
    investors: (managers || []).reduce((s: number, m: any) => s + m.total_subscribers, 0),
    strategies: (managers || []).reduce((s: number, m: any) => s + m.strategies.length, 0),
  }), [managers])

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Directory" title="Money managers"
        subtitle="Managers running pooled strategies on this broker, with aggregate assets and per-strategy track records." />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatCard label="Managers" icon="users" value={managers ? managers.length : <Skeleton className="h-7 w-10" />} />
        <StatCard label="Assets managed" icon="wallet" value={managers ? usd(totals.aum, { decimals: 0 }) : <Skeleton className="h-7 w-28" />} />
        <StatCard label="Strategies · allocations" icon="layers" value={managers ? `${totals.strategies} · ${totals.investors}` : <Skeleton className="h-7 w-16" />} />
      </div>

      {error ? <div className="card"><EmptyState icon="alert" title="Could not load managers" hint={(error as Error).message} /></div>
        : isLoading ? <div className="grid lg:grid-cols-2 gap-4">{[0, 1].map(i => <Skeleton key={i} className="h-72" />)}</div>
        : !managers?.length ? <div className="card"><EmptyState icon="users" title="No managers yet" hint="Managers appear once they run at least one active master account." /></div>
        : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {managers.map((m: any) => {
              const share = totals.aum ? Number(m.total_aum) / totals.aum * 100 : 0
              return (
                <Card key={m.manager_id}>
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <span className="w-11 h-11 rounded-xl bg-brand-500/15 text-brand-600 dark:text-brand-400 grid place-items-center font-semibold">{initials(m.manager_name)}</span>
                      <div>
                        <div className="font-semibold">{prettyName(m.manager_name)}</div>
                        <div className="text-xs text-muted">{m.master_account_count} master accounts · {m.total_subscribers} investor allocations</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`text-lg font-semibold num ${tone(m.avg_return_pct)}`}>{pct(m.avg_return_pct)}</div>
                      <div className="text-[11px] text-subtle">avg. return per master</div>
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="flex justify-between text-xs mb-1.5"><span className="text-muted">AUM {usd(m.total_aum, { decimals: 0 })}</span><span className="text-subtle">{share.toFixed(1)}% of platform</span></div>
                    <div className="h-1.5 rounded-full bg-raised overflow-hidden"><div className="h-full bg-brand-500 rounded-full" style={{ width: `${share}%` }} /></div>
                  </div>

                  <div className="mt-4 divide-y divide-line/70 border border-line rounded-lg">
                    {m.strategies.map((s: any) => {
                      const p = perfByLogin.get(s.master_login)
                      return (
                        <Link key={s.strategy_id} to={p ? `/strategy/${p.master_account_id}` : '/'} className="flex items-center gap-3 px-3 py-2.5 hover:bg-raised transition-colors">
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium flex items-center gap-2 truncate">{s.name} <KindBadge kind={s.kind} /></div>
                            <div className="text-xs text-muted">NAV {fmtNav(s.nav)} · {s.subscriber_count} investors · {usd(s.equity, { decimals: 0 })}</div>
                          </div>
                          <div className="w-24 hidden sm:block">{p && <Sparkline data={p.history} id={`m-${s.strategy_id}`} height={30} />}</div>
                          <div className={`w-16 text-right text-sm font-medium num ${tone(s.return_pct)}`}>{pct(s.return_pct)}</div>
                          <Icon name="chevronRight" className="w-4 h-4 text-subtle" />
                        </Link>
                      )
                    })}
                  </div>
                </Card>
              )
            })}
          </div>
        )}
      <DemoNote>Manager names are derived from seeded demo accounts; performance comes from the simulated broker adapter.</DemoNote>
    </div>
  )
}
