import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { PageHeader } from '../components/ui'

function Modal({ title, children, onClose }: any) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="card p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} className="text-slate-400">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

function ConfirmDialog({ title, message, confirmLabel, onConfirm, onCancel, danger = false }:
  { title: string; message: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void; danger?: boolean }) {
  return (
    <Modal title={title} onClose={onCancel}>
      <div className="space-y-4">
        <p className="text-sm text-slate-700 dark:text-slate-300">{message}</p>
        <div className="flex gap-2 justify-end">
          <button className="btn-ghost" onClick={onCancel}>Cancel</button>
          <button className={danger ? 'bg-red-600 text-white px-3 py-2 rounded-md text-sm font-medium hover:bg-red-700'
                                    : 'btn-primary'}
                  onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </Modal>
  )
}

export default function Copy() {
  const qc = useQueryClient()
  const { data: subs } = useQuery({ queryKey: ['copy-subs'], queryFn: api.listCopySubscriptions })
  const { data: trades } = useQuery({ queryKey: ['copy-trades'], queryFn: api.listCopyTrades })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: api.listStrategies })
  const { data: investors } = useQuery({ queryKey: ['investors'], queryFn: api.listInvestors })

  const [showSub, setShowSub] = useState(false)
  const [showTrade, setShowTrade] = useState(false)
  const [expandedTrade, setExpandedTrade] = useState<string | null>(null)
  const [followerTrades, setFollowerTrades] = useState<any[]>([])
  const [pendingDetach, setPendingDetach] = useState<{ id: string; closePositions: boolean } | null>(null)
  const [actionError, setActionError] = useState('')

  const [subForm, setSubForm] = useState({ strategy_id: '', follower_account_id: '',
    max_lots_per_trade: '2', lot_multiplier: '1.0', excluded_symbols: '[]' })
  const [tradeForm, setTradeForm] = useState({ strategy_id: '', master_account_id: '',
    symbol: 'EURUSD', side: 'buy', master_lots: '1', master_price: '1.10', idempotency_key: '' })

  const copySub = useMutation({
    mutationFn: () => api.copySubscribe({
      ...subForm,
      max_lots_per_trade: subForm.max_lots_per_trade || null,
      excluded_symbols: JSON.parse(subForm.excluded_symbols || '[]'),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['copy-subs'] }); setShowSub(false) },
    onError: (e: any) => setActionError(e.message),
  })
  const openTrade = useMutation({
    mutationFn: () => api.openCopyTrade({
      ...tradeForm, idempotency_key: tradeForm.idempotency_key || crypto.randomUUID(),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['copy-trades'] }); setShowTrade(false) },
    onError: (e: any) => setActionError(e.message),
  })
  const control = useMutation({
    mutationFn: (body: any) => api.copyControl(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['copy-subs'] }); setActionError('') },
    onError: (e: any) => setActionError(e.message),
  })
  const fetchFollowers = useMutation({
    mutationFn: (trade_id: string) => api.listCopyTrades(),  // TODO: replace with /api/copy/trades/{id}/followers when API method exists
    onSuccess: () => {},
  })

  async function expandTrade(trade_id: string) {
    if (expandedTrade === trade_id) {
      setExpandedTrade(null); setFollowerTrades([]); return
    }
    try {
      const fs = await fetch(`/api/copy/trades/${trade_id}/followers`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
      }).then(r => r.json())
      setFollowerTrades(fs)
      setExpandedTrade(trade_id)
    } catch (e: any) { setActionError(e.message) }
  }

  const copyStrategies = (strategies || []).filter(s => s.kind === 'copy')
  const totalActive = (subs || []).filter(s => s.status === 'active').length
  const totalPaused = (subs || []).filter(s => s.status === 'paused').length
  const totalDetached = (subs || []).filter(s => s.status === 'detached').length

  return (
    <div>
      <PageHeader eyebrow="Allocation" title="Copy trading"
        subtitle={<>{totalActive} active · {totalPaused} paused · {totalDetached} detached followers. Master trades are mirrored to followers with a per-follower risk multiplier.</>}
        actions={<div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={() => setShowSub(true)}>New Follower Subscription</button>
          <button className="btn-primary" onClick={() => {
            const cs = (subs || [])[0]
            setTradeForm({ ...tradeForm, strategy_id: cs?.strategy_id || '',
                          master_account_id: cs?.master_account_id || '' })
            setShowTrade(true)
          }}>Open Copy Trade</button>
        </div>} />

      {actionError && (
        <div className="card p-3 mb-4 bg-red-50 dark:bg-red-900/20 border-red-300 dark:border-red-700">
          <div className="flex justify-between items-center">
            <span className="text-sm text-red-700 dark:text-red-300">{actionError}</span>
            <button className="text-red-500 text-xs" onClick={() => setActionError('')}>✕</button>
          </div>
        </div>
      )}

      <div className="card p-4 mb-6">
        <h2 className="font-semibold mb-3">Follower Subscriptions</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <th className="py-2">Follower</th>
              <th>Master</th>
              <th>Multiplier</th>
              <th>Max Lots</th>
              <th>Status</th>
              <th>Excluded Symbols</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {(subs || []).map(s => (
              <tr key={s.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-2 font-mono">{s.follower_login}</td>
                <td className="font-mono">{s.master_login}</td>
                <td>{s.lot_multiplier}</td>
                <td>{s.max_lots_per_trade || '—'}</td>
                <td>
                  <span className={
                    s.status === 'active' ? 'tag-ok' :
                    s.status === 'paused' ? 'tag-warn' : 'tag-danger'
                  }>{s.status}</span>
                </td>
                <td className="text-xs text-slate-500">{(s.excluded_symbols || []).join(', ') || '—'}</td>
                <td>
                  <div className="flex gap-1 flex-wrap">
                    {s.status === 'active' && (
                      <button
                        className="bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 px-2 py-1 rounded text-xs font-medium hover:bg-amber-200"
                        disabled={control.isPending}
                        onClick={() => control.mutate({ copy_subscription_id: s.id, action: 'pause' })}
                      >Pause</button>
                    )}
                    {s.status === 'paused' && (
                      <button
                        className="bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 px-2 py-1 rounded text-xs font-medium hover:bg-green-200"
                        disabled={control.isPending}
                        onClick={() => control.mutate({ copy_subscription_id: s.id, action: 'resume' })}
                      >Resume</button>
                    )}
                    {s.status !== 'detached' && (
                      <>
                        <button
                          className="bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 px-2 py-1 rounded text-xs font-medium hover:bg-red-200"
                          disabled={control.isPending}
                          onClick={() => setPendingDetach({ id: s.id, closePositions: false })}
                        >Detach</button>
                        <button
                          className="bg-red-200 text-red-900 dark:bg-red-900/60 dark:text-red-200 px-2 py-1 rounded text-xs font-medium hover:bg-red-300"
                          disabled={control.isPending}
                          onClick={() => setPendingDetach({ id: s.id, closePositions: true })}
                        >Detach + Close</button>
                      </>
                    )}
                    {s.status === 'detached' && (
                      <span className="text-xs text-slate-500">Permanent — no actions available</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {subs && subs.length === 0 && (
              <tr><td colSpan={7} className="py-4 text-center text-slate-500">No follower subscriptions yet.</td></tr>
            )}
          </tbody>
        </table>
        <div className="mt-3 text-xs text-slate-500">
          <strong>Pause</strong>: new master trades are skipped for this follower (existing positions left open).
          <strong> Resume</strong>: re-accepts new master trades.
          <strong> Detach</strong>: permanent — follower no longer receives trades.
          <strong> Detach + Close</strong>: also requests closing existing follower positions (broker permitting).
        </div>
      </div>

      {pendingDetach && (
        <ConfirmDialog
          title={pendingDetach.closePositions ? 'Detach and close positions?' : 'Detach subscription?'}
          message={pendingDetach.closePositions
            ? 'This will permanently stop new trades for this follower AND request closing existing follower positions via the broker. Existing positions may be left open if the broker rejects close orders. This action is irreversible.'
            : 'This will permanently stop new trades for this follower. Existing positions will be left open. This action is irreversible.'}
          confirmLabel={pendingDetach.closePositions ? 'Detach + Close' : 'Detach (leave open)'}
          danger
          onConfirm={() => {
            control.mutate({ copy_subscription_id: pendingDetach.id, action: 'detach',
                             close_positions: pendingDetach.closePositions })
            setPendingDetach(null)
          }}
          onCancel={() => setPendingDetach(null)}
        />
      )}

      <div className="card p-4">
        <h2 className="font-semibold mb-3">Recent Copy Trades (click to expand follower details)</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <th className="py-2">Symbol</th>
              <th>Side</th>
              <th>Master Lots</th>
              <th>Status</th>
              <th>Filled</th>
              <th>Rejected</th>
              <th>Skipped</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(trades || []).map(t => (
              <React.Fragment key={t.id}>
                <tr
                  className="border-t border-slate-100 dark:border-slate-800 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700/40"
                  onClick={() => expandTrade(t.id)}
                >
                  <td className="py-2 font-mono">{t.symbol}</td>
                  <td>
                    <span className={t.side === 'buy' ? 'text-green-600' : t.side === 'sell' ? 'text-red-600' : 'text-amber-600'}>
                      {t.side}
                    </span>
                  </td>
                  <td>{t.master_lots}</td>
                  <td><span className="tag-ok">{t.status}</span></td>
                  <td className="text-green-600">{t.filled}</td>
                  <td className="text-red-600">{t.rejected}</td>
                  <td className="text-amber-600">{t.skipped}</td>
                  <td className="text-xs">{new Date(t.created_at).toLocaleString()}</td>
                  <td className="text-xs text-slate-500">
                    {expandedTrade === t.id ? '▲ collapse' : '▼ expand'}
                  </td>
                </tr>
                {expandedTrade === t.id && (
                  <tr className="bg-slate-50 dark:bg-slate-900/40">
                    <td colSpan={9} className="p-4">
                      {followerTrades.length === 0 ? (
                        <p className="text-sm text-slate-500">No follower trades for this copy trade.</p>
                      ) : (
                        <div>
                          <h3 className="font-semibold text-sm mb-2">Follower Trades with Latency Breakdown</h3>
                          <table className="w-full text-xs">
                            <thead className="text-left text-slate-500">
                              <tr>
                                <th className="py-1">Follower Account</th>
                                <th>Subscription</th>
                                <th>Requested</th>
                                <th>Allocated</th>
                                <th>Fill Price</th>
                                <th>Status</th>
                                <th>Server Latency</th>
                                <th>Broker Latency</th>
                                <th>Total</th>
                                <th>Slippage (bps)</th>
                                <th>Executed At</th>
                              </tr>
                            </thead>
                            <tbody>
                              {followerTrades.map((ft: any) => (
                                <tr key={ft.id} className="border-t border-slate-200 dark:border-slate-700">
                                  <td className="py-1 font-mono">{ft.follower_account_id.slice(0, 8)}</td>
                                  <td className="font-mono">{ft.subscription_id.slice(0, 8)}</td>
                                  <td>{ft.requested_lots}</td>
                                  <td>{ft.allocated_lots}</td>
                                  <td>{ft.fill_price || '—'}</td>
                                  <td>
                                    <span className={
                                      ft.status === 'filled' ? 'tag-ok' :
                                      ft.status === 'rejected' ? 'tag-danger' :
                                      ft.status === 'skipped' ? 'tag-warn' : 'tag-mock'
                                    }>{ft.status}</span>
                                    {ft.reject_reason && <div className="text-xs text-red-500">{ft.reject_reason}</div>}
                                  </td>
                                  <td className="text-blue-600 dark:text-blue-400">
                                    {ft.server_side_latency_ms !== null ? `${ft.server_side_latency_ms} ms` : '—'}
                                  </td>
                                  <td className="text-purple-600 dark:text-purple-400">
                                    {ft.broker_latency_ms !== null ? `${ft.broker_latency_ms} ms` : '—'}
                                  </td>
                                  <td className="text-slate-600 dark:text-slate-300 font-medium">
                                    {(ft.server_side_latency_ms !== null && ft.broker_latency_ms !== null)
                                      ? `${ft.server_side_latency_ms + ft.broker_latency_ms} ms` : '—'}
                                  </td>
                                  <td className={Number(ft.slippage_bps || 0) >= 0 ? 'text-amber-600' : 'text-green-600'}>
                                    {ft.slippage_bps !== null ? ft.slippage_bps : '—'}
                                  </td>
                                  <td className="text-xs">
                                    {ft.executed_at ? new Date(ft.executed_at).toLocaleTimeString() : '—'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <div className="mt-2 text-xs text-slate-500">
                            <strong>Server latency</strong> = platform processing time (dedup check + risk interlock + allocation).
                            <strong> Broker latency</strong> = network + broker + exchange round-trip.
                            These are tracked separately so calibration can attribute execution-quality issues correctly.
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
            {trades && trades.length === 0 && (
              <tr><td colSpan={9} className="py-4 text-center text-slate-500">No copy trades yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showSub && (
        <Modal title="New Follower Subscription" onClose={() => setShowSub(false)}>
          <div className="space-y-3">
            <div><label className="label">Copy Strategy</label>
              <select className="input" value={subForm.strategy_id} onChange={e => setSubForm({...subForm, strategy_id: e.target.value})}>
                <option value="">—</option>
                {copyStrategies.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div><label className="label">Follower Account</label>
              <select className="input" value={subForm.follower_account_id} onChange={e => setSubForm({...subForm, follower_account_id: e.target.value})}>
                <option value="">—</option>
                {(investors || []).map(i => <option key={i.id} value={i.id}>{i.login}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div><label className="label">Lot Multiplier</label><input className="input" value={subForm.lot_multiplier} onChange={e => setSubForm({...subForm, lot_multiplier: e.target.value})} /></div>
              <div><label className="label">Max Lots / Trade</label><input className="input" value={subForm.max_lots_per_trade} onChange={e => setSubForm({...subForm, max_lots_per_trade: e.target.value})} /></div>
            </div>
            <div><label className="label">Excluded Symbols (JSON array, e.g. ["GBPUSD","XAUUSD"])</label>
              <input className="input font-mono text-xs" value={subForm.excluded_symbols} onChange={e => setSubForm({...subForm, excluded_symbols: e.target.value})} />
            </div>
            <button className="btn-primary w-full" onClick={() => copySub.mutate()} disabled={copySub.isPending}>Subscribe</button>
            {copySub.isError && <div className="text-red-500 text-xs">{String(copySub.error)}</div>}
          </div>
        </Modal>
      )}

      {showTrade && (
        <Modal title="Open Copy Trade" onClose={() => setShowTrade(false)}>
          <div className="space-y-3">
            <div className="tag-mock">Simulated broker — no real orders placed.</div>
            <div><label className="label">Symbol</label><input className="input" value={tradeForm.symbol} onChange={e => setTradeForm({...tradeForm, symbol: e.target.value})} /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><label className="label">Side</label>
                <select className="input" value={tradeForm.side} onChange={e => setTradeForm({...tradeForm, side: e.target.value})}>
                  <option value="buy">buy</option>
                  <option value="sell">sell</option>
                  <option value="close">close</option>
                </select>
              </div>
              <div><label className="label">Master Lots</label><input className="input" value={tradeForm.master_lots} onChange={e => setTradeForm({...tradeForm, master_lots: e.target.value})} /></div>
              <div><label className="label">Master Price</label><input className="input" value={tradeForm.master_price} onChange={e => setTradeForm({...tradeForm, master_price: e.target.value})} /></div>
              <div><label className="label">Idempotency Key (auto)</label><input className="input" value={tradeForm.idempotency_key} onChange={e => setTradeForm({...tradeForm, idempotency_key: e.target.value})} placeholder="auto-generated" /></div>
            </div>
            <button className="btn-primary w-full" onClick={() => openTrade.mutate()} disabled={openTrade.isPending}>Open Trade</button>
            {openTrade.isError && <div className="text-red-500 text-xs">{String(openTrade.error)}</div>}
          </div>
        </Modal>
      )}
    </div>
  )
}
