import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

export default function Settlement() {
  const { data: masters } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const [masterId, setMasterId] = useState('')
  const { data: rollovers } = useQuery({ queryKey: ['rollovers', masterId], queryFn: () => api.listRollovers(masterId), enabled: !!masterId })
  const [rolloverId, setRolloverId] = useState('')
  const [proof, setProof] = useState<any>(null)
  const [statement, setStatement] = useState<any>(null)
  const [subId, setSubId] = useState('')
  const [err, setErr] = useState('')
  async function loadProof() {
    setErr(''); setProof(null)
    try { setProof(await api.getProof(rolloverId, subId)) } catch (e: any) { setErr(e.message) }
  }
  async function loadStatement() {
    setErr(''); setStatement(null)
    try { setStatement(await api.getStatement(rolloverId, subId)) } catch (e: any) { setErr(e.message) }
  }
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Settlement & Merkle Proofs</h1>
      <div className="card p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div><label className="label">Master Account</label>
            <select className="input" value={masterId} onChange={e => setMasterId(e.target.value)}>
              <option value="">—</option>
              {(masters || []).map(m => <option key={m.id} value={m.id}>{m.login}</option>)}
            </select>
          </div>
          <div><label className="label">Rollover</label>
            <select className="input" value={rolloverId} onChange={e => setRolloverId(e.target.value)}>
              <option value="">—</option>
              {(rollovers || []).map(r => <option key={r.id} value={r.id}>{r.id.slice(0,8)} · {r.method}</option>)}
            </select>
          </div>
          <div><label className="label">Subscription ID</label><input className="input" value={subId} onChange={e => setSubId(e.target.value)} placeholder="paste subscription id" /></div>
        </div>
        <div className="flex gap-2 mt-3">
          <button className="btn-primary" disabled={!rolloverId || !subId} onClick={loadProof}>Verify Merkle Proof</button>
          <button className="btn-ghost" disabled={!rolloverId || !subId} onClick={loadStatement}>Download Statement</button>
        </div>
        {err && <div className="text-red-500 text-xs mt-2">{err}</div>}
      </div>
      {proof && (
        <div className="card p-4 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Merkle Inclusion Proof</h2>
            {proof.verified ? <span className="tag-ok">VERIFIED</span> : <span className="tag-danger">FAILED</span>}
          </div>
          <div className="text-xs mb-2"><strong>Root:</strong> <code className="break-all">{proof.root_hash}</code></div>
          <div className="text-xs mb-2"><strong>Leaf:</strong> <code className="break-all">{proof.leaf_hash}</code></div>
          <div className="text-xs mb-2"><strong>Canonical blob:</strong><pre className="bg-slate-100 dark:bg-slate-900 p-2 rounded text-xs mt-1 whitespace-pre-wrap">{proof.leaf_blob}</pre></div>
          <div className="text-xs"><strong>Path ({proof.path.length} siblings):</strong>
            <ol className="list-decimal ml-5 mt-1 space-y-1">
              {proof.path.map((p: any, i: number) => (
                <li key={i} className="text-xs"><code className="break-all">{p.sibling}</code> ({p.position})</li>
              ))}
            </ol>
          </div>
        </div>
      )}
      {statement && (
        <div className="card p-4">
          <div className="flex justify-between items-center mb-3">
            <h2 className="font-semibold">Investor Settlement Statement</h2>
            <button className="btn-ghost text-xs" onClick={() => {
              const blob = new Blob([JSON.stringify(statement, null, 2)], { type: 'application/json' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a'); a.href = url; a.download = `${statement.statement_id}.json`; a.click()
            }}>Download JSON</button>
          </div>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-slate-500">Statement ID</dt><dd className="font-mono">{statement.statement_id}</dd>
            <dt className="text-slate-500">Investor</dt><dd>{statement.investor_login}</dd>
            <dt className="text-slate-500">Method</dt><dd>{statement.method}</dd>
            <dt className="text-slate-500">Units</dt><dd>{statement.units}</dd>
            <dt className="text-slate-500">NAV Before → After</dt><dd>{statement.nav_before} → {statement.nav_after}</dd>
            <dt className="text-slate-500">P&L Share</dt><dd>${Number(statement.pnl_share).toFixed(2)}</dd>
            <dt className="text-slate-500">Performance Fee</dt><dd>${Number(statement.performance_fee).toFixed(2)}</dd>
            <dt className="text-slate-500">Units After</dt><dd>{statement.units_after}</dd>
            <dt className="text-slate-500">Merkle Root</dt><dd className="font-mono text-xs break-all">{statement.merkle_root}</dd>
          </dl>
        </div>
      )}
    </div>
  )
}
