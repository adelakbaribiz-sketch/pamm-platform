import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { usd, nav as fmtNav, rate } from '../format'
import { Field, Modal, ErrorNote, DemoNote, KindBadge, useToast } from './ui'

const MIN_INVESTMENT = 100

export interface InvestTarget { strategy_id: string; name: string; kind: string; nav: number; performance_fee_rate: number }

export default function InvestModal({ target, onClose }: { target: InvestTarget; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: accounts, isLoading } = useQuery({ queryKey: ['investors'], queryFn: api.listInvestors })
  const [accountId, setAccountId] = useState('')
  const [amount, setAmount] = useState('1000')
  const [touched, setTouched] = useState(false)
  const selected = accountId || accounts?.[0]?.id || ''

  const amt = Number(amount)
  const amountError = !amount || !Number.isFinite(amt) ? 'Enter an amount'
    : amt < MIN_INVESTMENT ? `Minimum allocation is ${usd(MIN_INVESTMENT, { decimals: 0 })}` : ''
  const isCopy = target.kind === 'copy'

  const subscribe = useMutation({
    mutationFn: () => api.subscribe({ strategy_id: target.strategy_id, investor_account_id: selected, capital: amount }),
    onSuccess: (r: any) => {
      ;['subs', 'top-accounts', 'public-strategies', 'platform-stats', 'masters'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))
      toast(`Allocated ${usd(amt)} to ${target.name} — ${Number(r.units).toFixed(4)} units issued at NAV ${fmtNav(r.nav_at_entry)}`)
      onClose()
    },
  })

  return (
    <Modal title="Allocate capital" subtitle={target.name} onClose={onClose}>
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-3 rounded-lg bg-raised border border-line p-3 text-xs">
          <div><div className="text-subtle">Type</div><div className="mt-1"><KindBadge kind={target.kind} /></div></div>
          <div><div className="text-subtle">Current NAV</div><div className="mt-1 font-medium num">{fmtNav(target.nav)}</div></div>
          <div><div className="text-subtle">Performance fee</div><div className="mt-1 font-medium">{rate(target.performance_fee_rate)} over HWM</div></div>
        </div>

        {isCopy ? (
          <DemoNote>Copy strategies use follower subscriptions with their own risk multiplier. Use the <Link to="/copy" className="text-brand-500 underline">Copy trading</Link> console instead.</DemoNote>
        ) : !isLoading && !accounts?.length ? (
          <DemoNote>No investor trading account is linked to this user. A broker admin can create one under <Link to="/investors" className="text-brand-500 underline">Investor accounts</Link>.</DemoNote>
        ) : (
          <>
            <Field label="Funding account">
              <select className="input" value={selected} onChange={e => setAccountId(e.target.value)}>
                {(accounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.login} · {a.currency}</option>)}
              </select>
            </Field>
            <Field label="Amount (USD)" error={touched && amountError}
              hint={amt >= MIN_INVESTMENT && target.nav > 0 ? `≈ ${(amt / target.nav).toFixed(4)} units at current NAV` : undefined}>
              <input type="number" inputMode="decimal" min={MIN_INVESTMENT} step="100"
                className={`input num ${touched && amountError ? 'input-error' : ''}`}
                value={amount} onBlur={() => setTouched(true)} onChange={e => setAmount(e.target.value)} />
            </Field>
            <div className="flex gap-2">
              {[1000, 5000, 25000].map(v => (
                <button key={v} type="button" className="btn-ghost h-7 text-xs" onClick={() => { setAmount(String(v)); setTouched(true) }}>{usd(v, { decimals: 0 })}</button>
              ))}
            </div>
            {subscribe.isError && <ErrorNote error={subscribe.error} />}
            <button className="btn-primary w-full h-10" disabled={!!amountError || !selected || subscribe.isPending}
              onClick={() => { setTouched(true); if (!amountError) subscribe.mutate() }}>
              {subscribe.isPending ? 'Processing…' : `Confirm allocation${amountError ? '' : ` of ${usd(amt)}`}`}
            </button>
            <p className="text-[11px] text-subtle leading-relaxed">
              Units are issued at the current NAV. Performance fees accrue only on gains above each investor's high-water mark
              at rollover. Simulated environment — no real funds move.
            </p>
          </>
        )}
      </div>
    </Modal>
  )
}
