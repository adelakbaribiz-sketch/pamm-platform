import React, { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { useAuth } from '../auth'
import { usd, nav as fmtNav, num, tone, errorMessage, fullDate } from '../format'
import { Card, EmptyState, ErrorNote, Field, Modal, PageHeader, TableWrap, useToast } from '../components/ui'
import { Icon } from '../components/icons'

export default function Investors() {
  const qc = useQueryClient()
  const toast = useToast()
  const { session } = useAuth()
  const isAdmin = session?.role === 'broker_admin' || session?.role === 'super_admin'
  const { data: investors, isLoading } = useQuery({ queryKey: ['investors'], queryFn: api.listInvestors })
  const { data: subs } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  const { data: brokers } = useQuery({ queryKey: ['brokers'], queryFn: api.listBrokers })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: api.listStrategies })
  const [showInv, setShowInv] = useState(false)
  const [showSub, setShowSub] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [filter, setFilter] = useState('')
  const [invForm, setInvForm] = useState({ broker_id: '', login: '', currency: 'USD' })
  const [subForm, setSubForm] = useState({ strategy_id: '', investor_account_id: '', capital: '1000' })

  const refresh = () => ['investors', 'subs', 'masters', 'top-accounts', 'platform-stats'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))
  const createInv = useMutation({ mutationFn: () => api.createInvestor(invForm), onSuccess: (r: any) => { refresh(); setShowInv(false); toast(`Investor account ${r.login} created`) } })
  const subscribe = useMutation({ mutationFn: () => api.subscribe(subForm), onSuccess: (r: any) => { refresh(); setShowSub(false); toast(`Subscription created — ${Number(r.units).toFixed(4)} units issued`) } })

  const invErrors = {
    broker_id: !invForm.broker_id && 'Select a broker',
    login: !invForm.login.trim() ? 'Login is required' : (investors || []).some(i => i.login === invForm.login.trim()) && 'Login already exists',
    currency: !/^[A-Z]{3}$/.test(invForm.currency) && 'Use a 3-letter ISO code',
  }
  const subErrors = {
    strategy_id: !subForm.strategy_id && 'Select a strategy',
    investor_account_id: !subForm.investor_account_id && 'Select an investor account',
    capital: !(Number(subForm.capital) >= 100) && 'Minimum is $100',
  }
  const hasErr = (e: Record<string, any>) => Object.values(e).some(Boolean)
  const show = (e: string | false) => submitted && e

  const countBy = useMemo(() => {
    const m = new Map<string, { n: number; value: number }>()
    for (const s of subs || []) {
      const cur = m.get(s.investor_account_id) || { n: 0, value: 0 }
      m.set(s.investor_account_id, { n: cur.n + 1, value: cur.value + Number(s.current_gav) })
    }
    return m
  }, [subs])
  const q = filter.trim().toLowerCase()
  const visibleSubs = (subs || []).filter(s => !q || [s.investor_login, s.master_login].some((v: string) => v?.toLowerCase().includes(q)))

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Workspaces" title="Investor accounts & subscriptions"
        subtitle="Trading accounts that fund allocations, and every active subscription with its unit position."
        actions={<>
          {isAdmin && <button className="btn-ghost" onClick={() => { setSubmitted(false); setInvForm({ broker_id: brokers?.[0]?.id || '', login: '', currency: 'USD' }); setShowInv(true) }}><Icon name="plus" /> New investor account</button>}
          <button className="btn-primary" onClick={() => { setSubmitted(false); setSubForm({ strategy_id: '', investor_account_id: investors?.[0]?.id || '', capital: '1000' }); setShowSub(true) }} disabled={!investors?.length}><Icon name="plus" /> Subscribe</button>
        </>} />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="Investor accounts" bodyClass="px-4 sm:px-5 pb-4 pt-2">
          {!isLoading && !investors?.length ? <EmptyState icon="users" title="No investor accounts" hint={isAdmin ? 'Create one to start subscribing.' : 'Ask your broker to link a trading account.'} /> : (
            <TableWrap>
              <table>
                <thead><tr><th>Login</th><th className="text-right">Allocations</th><th className="text-right">Value</th><th>Status</th></tr></thead>
                <tbody>
                  {(investors || []).map(i => (
                    <tr key={i.id}>
                      <td className="font-mono text-xs">{i.login}<div className="text-[11px] text-subtle font-sans">{i.currency}</div></td>
                      <td className="text-right num">{countBy.get(i.id)?.n || 0}</td>
                      <td className="text-right num">{usd(countBy.get(i.id)?.value || 0, { decimals: 0 })}</td>
                      <td><span className={i.status === 'active' ? 'tag-ok' : 'tag-neutral'}>{i.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </Card>
        <Card className="xl:col-span-2" title="Subscriptions" bodyClass="px-4 sm:px-5 pb-4 pt-2"
          actions={<input className="input h-8 w-48" placeholder="Filter by investor or master" value={filter} onChange={e => setFilter(e.target.value)} aria-label="Filter subscriptions" />}>
          {!visibleSubs.length ? <EmptyState title={subs?.length ? 'No subscriptions match' : 'No subscriptions yet'} /> : (
            <TableWrap>
              <table>
                <thead><tr><th>Investor</th><th>Master</th><th>Since</th><th className="text-right">Contributed</th><th className="text-right">Units</th><th className="text-right">NAV</th><th className="text-right">Value (GAV)</th><th className="text-right">Unrealized P&L</th></tr></thead>
                <tbody>
                  {visibleSubs.map(s => (
                    <tr key={s.id}>
                      <td className="font-mono text-xs">{s.investor_login}</td>
                      <td className="font-mono text-xs text-muted">{s.master_login}</td>
                      <td className="text-muted">{fullDate(s.subscribed_at)}</td>
                      <td className="text-right num">{usd(s.contributed_capital)}</td>
                      <td className="text-right num">{num(s.units, 4)}</td>
                      <td className="text-right num">{fmtNav(s.current_nav)}</td>
                      <td className="text-right num">{usd(s.current_gav)}</td>
                      <td className={`text-right num ${tone(s.unrealized_pnl)}`}>{usd(s.unrealized_pnl, { signed: true })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </Card>
      </div>

      {showInv && (
        <Modal title="New investor account" onClose={() => setShowInv(false)}>
          <form className="space-y-3" noValidate onSubmit={e => { e.preventDefault(); setSubmitted(true); if (!hasErr(invErrors)) createInv.mutate() }}>
            <Field label="Broker" error={show(invErrors.broker_id)}>
              <select className="input" value={invForm.broker_id} onChange={e => setInvForm({ ...invForm, broker_id: e.target.value })}>
                <option value="">Select broker…</option>
                {(brokers || []).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </Field>
            <Field label="Login" error={show(invErrors.login)}><input className={`input font-mono ${show(invErrors.login) ? 'input-error' : ''}`} placeholder="e.g. INV-20001" value={invForm.login} onChange={e => setInvForm({ ...invForm, login: e.target.value })} /></Field>
            <Field label="Currency" error={show(invErrors.currency)}><input className="input" maxLength={3} value={invForm.currency} onChange={e => setInvForm({ ...invForm, currency: e.target.value.toUpperCase() })} /></Field>
            {createInv.isError && <ErrorNote error={errorMessage(createInv.error)} />}
            <button className="btn-primary w-full h-10" disabled={createInv.isPending}>{createInv.isPending ? 'Creating…' : 'Create account'}</button>
          </form>
        </Modal>
      )}
      {showSub && (
        <Modal title="Subscribe to strategy" subtitle="PAMM and MAM strategies only — copy uses follower subscriptions" onClose={() => setShowSub(false)}>
          <form className="space-y-3" noValidate onSubmit={e => { e.preventDefault(); setSubmitted(true); if (!hasErr(subErrors)) subscribe.mutate() }}>
            <Field label="Strategy" error={show(subErrors.strategy_id)}>
              <select className="input" value={subForm.strategy_id} onChange={e => setSubForm({ ...subForm, strategy_id: e.target.value })}>
                <option value="">Select strategy…</option>
                {(strategies || []).filter(s => s.kind !== 'copy').map(s => <option key={s.id} value={s.id}>{s.name} ({s.kind.toUpperCase()})</option>)}
              </select>
            </Field>
            <Field label="Investor account" error={show(subErrors.investor_account_id)}>
              <select className="input" value={subForm.investor_account_id} onChange={e => setSubForm({ ...subForm, investor_account_id: e.target.value })}>
                <option value="">Select account…</option>
                {(investors || []).map(i => <option key={i.id} value={i.id}>{i.login}</option>)}
              </select>
            </Field>
            <Field label="Capital (USD)" error={show(subErrors.capital)}><input className="input num" inputMode="decimal" value={subForm.capital} onChange={e => setSubForm({ ...subForm, capital: e.target.value })} /></Field>
            {subscribe.isError && <ErrorNote error={errorMessage(subscribe.error)} />}
            <button className="btn-primary w-full h-10" disabled={subscribe.isPending}>{subscribe.isPending ? 'Subscribing…' : 'Subscribe'}</button>
          </form>
        </Modal>
      )}
    </div>
  )
}
