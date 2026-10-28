import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { usd, nav as fmtNav, rate, errorMessage, METHOD_LABEL } from '../format'
import { Card, DemoNote, EmptyState, ErrorNote, Field, KindBadge, Modal, PageHeader, TableWrap, useToast } from '../components/ui'
import { Icon } from '../components/icons'

const METHODS = ['euro_days', 'start_capital', 'end_capital']

export default function MasterAccounts() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: brokers } = useQuery({ queryKey: ['brokers'], queryFn: api.listBrokers })
  const { data: masters, isLoading } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: api.listStrategies })
  const [showMaster, setShowMaster] = useState(false)
  const [showStrat, setShowStrat] = useState(false)
  const [pnlModal, setPnlModal] = useState<any | null>(null)
  const [mForm, setMForm] = useState({ broker_id: '', login: '', currency: 'USD', base_nav: '100', performance_fee_rate: '0.2', allocation_method: 'euro_days' })
  const [sForm, setSForm] = useState({ master_account_id: '', name: '', description: '', kind: 'pamm' })
  const [pnl, setPnl] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const refresh = () => ['masters', 'strategies', 'strats', 'top-accounts', 'platform-stats'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))
  const createM = useMutation({ mutationFn: () => api.createMaster(mForm), onSuccess: (r: any) => { refresh(); setShowMaster(false); toast(`Master account ${r.login} created`) } })
  const createS = useMutation({ mutationFn: () => api.createStrategy(sForm), onSuccess: () => { refresh(); setShowStrat(false); toast(`Strategy “${sForm.name}” created`) } })
  const simPnl = useMutation({
    mutationFn: () => api.simulatePnl(pnlModal.id, pnl),
    onSuccess: (r: any) => { refresh(); setPnlModal(null); setPnl(''); toast(`Simulated P&L applied — equity now ${usd(r.equity)}`, 'info') },
  })

  const fee = Number(mForm.performance_fee_rate)
  const mErrors = {
    broker_id: !mForm.broker_id && 'Select a broker',
    login: !mForm.login.trim() ? 'Login is required' : (masters || []).some(m => m.login === mForm.login.trim()) && 'Login already exists',
    currency: !/^[A-Z]{3}$/.test(mForm.currency) && 'Use a 3-letter ISO code',
    base_nav: !(Number(mForm.base_nav) > 0) && 'Must be greater than 0',
    performance_fee_rate: !(fee >= 0 && fee < 1) && 'Enter a fraction between 0 and 0.99 (e.g. 0.2 = 20%)',
  }
  const sErrors = { master_account_id: !sForm.master_account_id && 'Select a master account', name: !sForm.name.trim() && 'Name is required' }
  const pnlError = pnl === '' || !Number.isFinite(Number(pnl)) || Number(pnl) === 0 ? 'Enter a non-zero amount, e.g. 500 or -200' : ''
  const hasErr = (e: Record<string, any>) => Object.values(e).some(Boolean)
  const show = (e: string | false) => submitted && e

  const openMaster = () => { setSubmitted(false); setMForm({ ...mForm, login: '', broker_id: brokers?.[0]?.id || '' }); setShowMaster(true) }
  const openStrat = () => { setSubmitted(false); setSForm({ master_account_id: masters?.[0]?.id || '', name: '', description: '', kind: 'pamm' }); setShowStrat(true) }
  const stratByMaster = new Map((strategies || []).map(s => [s.master_account_id, s]))

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Workspaces" title="Master accounts & strategies"
        subtitle="Master trading accounts hold pooled capital; each strategy exposes a master to investors as PAMM, MAM or copy."
        actions={<>
          <button className="btn-ghost" onClick={openMaster}><Icon name="plus" /> New master</button>
          <button className="btn-primary" onClick={openStrat} disabled={!masters?.length}><Icon name="plus" /> New strategy</button>
        </>} />

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <Card className="xl:col-span-3" title="Master accounts" bodyClass="px-4 sm:px-5 pb-4 pt-2">
          {!isLoading && !masters?.length ? <EmptyState icon="layers" title="No master accounts" action={<button className="btn-primary" onClick={openMaster}>Create the first master</button>} /> : (
            <TableWrap>
              <table>
                <thead><tr><th>Login</th><th>Allocation</th><th className="text-right">Equity</th><th className="text-right">NAV</th><th className="text-right">Fee</th><th /></tr></thead>
                <tbody>
                  {(masters || []).map(m => (
                    <tr key={m.id}>
                      <td><Link to={`/strategy/${m.id}`} className="font-mono text-xs hover:text-brand-500">{m.login}</Link><div className="text-xs text-muted">{stratByMaster.get(m.id)?.name || 'No strategy'}</div></td>
                      <td><span className="tag-neutral">{METHOD_LABEL[m.allocation_method] || m.allocation_method}</span></td>
                      <td className="text-right num">{usd(m.equity)}</td>
                      <td className="text-right num">{fmtNav(m.nav)}</td>
                      <td className="text-right num">{rate(m.performance_fee_rate)}</td>
                      <td className="text-right"><button className="btn-ghost h-8 text-xs" onClick={() => { setPnl(''); setSubmitted(false); setPnlModal(m) }}>Simulate P&L</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </Card>
        <Card className="xl:col-span-2" title="Strategies">
          {!strategies?.length ? <EmptyState title="No strategies" /> : (
            <ul className="space-y-2">
              {strategies.map(s => (
                <li key={s.id} className="rounded-lg border border-line p-3 hover:bg-raised transition-colors">
                  <div className="flex items-center gap-2 font-medium text-sm">{s.name} <KindBadge kind={s.kind} /><span className={`ml-auto ${s.status === 'active' ? 'tag-ok' : 'tag-neutral'}`}>{s.status}</span></div>
                  {s.description && <div className="text-xs text-muted mt-1">{s.description}</div>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {showMaster && (
        <Modal title="New master account" subtitle="Created on the broker's simulated trading server" onClose={() => setShowMaster(false)}>
          <form className="space-y-3" noValidate onSubmit={e => { e.preventDefault(); setSubmitted(true); if (!hasErr(mErrors)) createM.mutate() }}>
            <Field label="Broker" error={show(mErrors.broker_id)}>
              <select className="input" value={mForm.broker_id} onChange={e => setMForm({ ...mForm, broker_id: e.target.value })}>
                <option value="">Select broker…</option>
                {(brokers || []).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </Field>
            <Field label="Login" error={show(mErrors.login)}><input className={`input font-mono ${show(mErrors.login) ? 'input-error' : ''}`} placeholder="e.g. PAMM-004" value={mForm.login} onChange={e => setMForm({ ...mForm, login: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Currency" error={show(mErrors.currency)}><input className="input" value={mForm.currency} onChange={e => setMForm({ ...mForm, currency: e.target.value.toUpperCase() })} maxLength={3} /></Field>
              <Field label="Base NAV" error={show(mErrors.base_nav)}><input className="input num" inputMode="decimal" value={mForm.base_nav} onChange={e => setMForm({ ...mForm, base_nav: e.target.value })} /></Field>
              <Field label="Performance fee (fraction)" error={show(mErrors.performance_fee_rate)} hint={fee >= 0 && fee < 1 ? `${(fee * 100).toFixed(1)}% of gains above HWM` : undefined}>
                <input className="input num" inputMode="decimal" value={mForm.performance_fee_rate} onChange={e => setMForm({ ...mForm, performance_fee_rate: e.target.value })} />
              </Field>
              <Field label="Allocation method">
                <select className="input" value={mForm.allocation_method} onChange={e => setMForm({ ...mForm, allocation_method: e.target.value })}>
                  {METHODS.map(m => <option key={m} value={m}>{METHOD_LABEL[m]}</option>)}
                </select>
              </Field>
            </div>
            {createM.isError && <ErrorNote error={errorMessage(createM.error)} />}
            <button className="btn-primary w-full h-10" disabled={createM.isPending}>{createM.isPending ? 'Creating…' : 'Create master account'}</button>
          </form>
        </Modal>
      )}

      {showStrat && (
        <Modal title="New strategy" onClose={() => setShowStrat(false)}>
          <form className="space-y-3" noValidate onSubmit={e => { e.preventDefault(); setSubmitted(true); if (!hasErr(sErrors)) createS.mutate() }}>
            <Field label="Master account" error={show(sErrors.master_account_id)}>
              <select className="input" value={sForm.master_account_id} onChange={e => setSForm({ ...sForm, master_account_id: e.target.value })}>
                <option value="">Select master…</option>
                {(masters || []).map(m => <option key={m.id} value={m.id}>{m.login}</option>)}
              </select>
            </Field>
            <Field label="Product type">
              <select className="input" value={sForm.kind} onChange={e => setSForm({ ...sForm, kind: e.target.value })}>
                <option value="pamm">PAMM — pooled, unit-based</option>
                <option value="mam">MAM — lot allocation across sub-accounts</option>
                <option value="copy">Copy — follower trade mirroring</option>
              </select>
            </Field>
            <Field label="Name" error={show(sErrors.name)}><input className={`input ${show(sErrors.name) ? 'input-error' : ''}`} value={sForm.name} onChange={e => setSForm({ ...sForm, name: e.target.value })} /></Field>
            <Field label="Description"><textarea className="input" rows={3} value={sForm.description} onChange={e => setSForm({ ...sForm, description: e.target.value })} /></Field>
            {createS.isError && <ErrorNote error={errorMessage(createS.error)} />}
            <button className="btn-primary w-full h-10" disabled={createS.isPending}>{createS.isPending ? 'Creating…' : 'Create strategy'}</button>
          </form>
        </Modal>
      )}

      {pnlModal && (
        <Modal title="Simulate P&L" subtitle={`${pnlModal.login} · equity ${usd(pnlModal.equity)}`} onClose={() => setPnlModal(null)}>
          <form className="space-y-3" noValidate onSubmit={e => { e.preventDefault(); setSubmitted(true); if (!pnlError) simPnl.mutate() }}>
            <DemoNote>Simulated broker — no real orders are placed. Risk rules (max exposure, max drawdown) are still enforced.</DemoNote>
            <Field label="P&L amount (USD)" error={show(pnlError)}><input className="input num" inputMode="decimal" value={pnl} onChange={e => setPnl(e.target.value)} placeholder="e.g. 500 or -200" autoFocus /></Field>
            {simPnl.isError && <ErrorNote error={`Rejected by risk engine: ${errorMessage(simPnl.error)}`} />}
            <button className="btn-primary w-full h-10" disabled={simPnl.isPending}>{simPnl.isPending ? 'Applying…' : 'Apply simulated P&L'}</button>
          </form>
        </Modal>
      )}
    </div>
  )
}
