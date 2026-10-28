import React, { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { useAuth } from '../auth'
import { usd, nav as fmtNav, num, fullDate, METHOD_LABEL } from '../format'
import { Card, EmptyState, ErrorNote, Field, PageHeader, StatCard, DemoNote } from '../components/ui'
import { Icon } from '../components/icons'

export default function Settlement() {
  const { session } = useAuth()
  const { data: masters } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const { data: mySubs } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  const { data: audit } = useQuery({ queryKey: ['audit'], queryFn: api.verifyAudit })
  const isInvestor = session?.role === 'investor'
  // Investors only pick from masters they hold; everyone else sees the tenant's masters.
  const pickable = (masters || []).filter(m => !isInvestor || (mySubs || []).some(s => s.master_account_id === m.id))

  const [masterId, setMasterId] = useState('')
  const [rolloverId, setRolloverId] = useState('')
  const [subId, setSubId] = useState('')
  const [proof, setProof] = useState<any>(null)
  const [statement, setStatement] = useState<any>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (!masterId && pickable.length) setMasterId(pickable[0].id) }, [pickable, masterId])
  const { data: rollovers } = useQuery({
    queryKey: ['rollovers', masterId], queryFn: () => api.listRollovers(masterId), enabled: !!masterId,
    select: (rs: any[]) => [...rs].sort((a, b) => b.period_end.localeCompare(a.period_end)),
  })
  useEffect(() => { setRolloverId(rollovers?.[0]?.id || ''); setProof(null); setStatement(null) }, [rollovers])
  const { data: rollover } = useQuery({ queryKey: ['rollover', rolloverId], queryFn: () => api.getRollover(rolloverId), enabled: !!rolloverId })
  const entries = rollover?.entries || []
  useEffect(() => { setSubId(entries[0]?.subscription_id || ''); setProof(null); setStatement(null) }, [rollover]) // eslint-disable-line react-hooks/exhaustive-deps

  async function verify() {
    setErr(''); setBusy(true)
    try {
      const [p, s] = await Promise.all([api.getProof(rolloverId, subId), api.getStatement(rolloverId, subId)])
      setProof(p); setStatement(s)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  function download() {
    const blob = new Blob([JSON.stringify({ statement, proof }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `${statement.statement_id}.json`; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Allocation" title="Settlement & proofs"
        subtitle="Every rollover publishes a Merkle root over all investor entries. Any investor can verify their statement is included — without seeing anyone else's." />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatCard label="Audit chain" icon="shield" value={audit ? (audit.verified ? 'Intact' : 'Broken') : '—'} tone={audit?.verified ? 'text-gain' : 'text-loss'} sub="SHA-256 hash chain over all audit events" />
        <StatCard label="Rollovers for this master" icon="refresh" value={rollovers?.length ?? '—'} />
        <StatCard label="Entries in selected rollover" icon="users" value={rollover ? entries.length : '—'} sub={isInvestor ? 'Only your own entries are listed' : undefined} />
      </div>

      <Card title="Verify a statement">
        {!pickable.length ? <EmptyState title="No settled allocations" hint="Statements appear after the first rollover of a strategy you hold." /> : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Field label="Master account">
                <select className="input" value={masterId} onChange={e => setMasterId(e.target.value)}>
                  {pickable.map(m => <option key={m.id} value={m.id}>{m.login}</option>)}
                </select>
              </Field>
              <Field label="Rollover period">
                <select className="input" value={rolloverId} onChange={e => setRolloverId(e.target.value)} disabled={!rollovers?.length}>
                  {!rollovers?.length && <option>No rollovers yet</option>}
                  {(rollovers || []).map(r => <option key={r.id} value={r.id}>{fullDate(r.period_end)} · NAV {fmtNav(r.nav_after)}</option>)}
                </select>
              </Field>
              <Field label="Investor entry">
                <select className="input" value={subId} onChange={e => setSubId(e.target.value)} disabled={!entries.length}>
                  {!entries.length && <option>No entries</option>}
                  {entries.map((e: any) => <option key={e.subscription_id} value={e.subscription_id}>{e.investor_login} · {num(e.units, 4)} units</option>)}
                </select>
              </Field>
            </div>
            <div className="flex flex-wrap gap-2 mt-4">
              <button className="btn-primary" disabled={!rolloverId || !subId || busy} onClick={verify}><Icon name="shield" /> {busy ? 'Verifying…' : 'Verify inclusion proof'}</button>
              {statement && <button className="btn-ghost" onClick={download}>Download statement (JSON)</button>}
            </div>
            {err && <div className="mt-3"><ErrorNote error={err} /></div>}
          </>
        )}
      </Card>

      {proof && statement && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Card title="Investor settlement statement" subtitle={statement.statement_id}
            actions={<span className="tag-neutral">{METHOD_LABEL[statement.method] || statement.method}</span>}>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <Row k="Investor" v={<span className="font-mono">{statement.investor_login}</span>} />
              <Row k="Units held" v={num(statement.units, 4)} />
              <Row k="NAV before → after" v={`${fmtNav(statement.nav_before)} → ${fmtNav(statement.nav_after)}`} />
              <Row k="P&L share" v={usd(statement.pnl_share, { signed: true })} />
              <Row k="Performance fee" v={usd(statement.performance_fee)} />
              <Row k="Units after fee" v={num(statement.units_after, 4)} />
            </dl>
          </Card>
          <Card title="Merkle inclusion proof" actions={proof.verified ? <span className="tag-ok"><Icon name="check" className="w-3 h-3" /> Verified</span> : <span className="tag-danger">Failed</span>}>
            <div className="space-y-3 text-xs">
              <Hash k="Published root" v={proof.root_hash} />
              <Hash k="Leaf hash" v={proof.leaf_hash} />
              <div>
                <div className="text-subtle mb-1">Path ({proof.path.length} siblings)</div>
                <ol className="space-y-1">
                  {proof.path.map((p: any, i: number) => (
                    <li key={i} className="flex gap-2"><span className="tag-neutral shrink-0">{p.position}</span><code className="font-mono break-all text-muted">{p.sibling}</code></li>
                  ))}
                </ol>
              </div>
              <details>
                <summary className="cursor-pointer text-subtle hover:text-fg">Canonical leaf data</summary>
                <pre className="mt-2 bg-raised border border-line rounded-lg p-3 whitespace-pre-wrap break-all font-mono">{proof.leaf_blob}</pre>
              </details>
            </div>
          </Card>
        </div>
      )}
      <DemoNote>The verifier recomputes the root from the leaf and sibling path. An offline verifier is included in <span className="font-mono">tools/offline_verifier.py</span>.</DemoNote>
    </div>
  )
}

const Row = ({ k, v }: { k: string; v: React.ReactNode }) => (<><dt className="text-muted">{k}</dt><dd className="text-right num font-medium">{v}</dd></>)
const Hash = ({ k, v }: { k: string; v: string }) => (
  <div><div className="text-subtle mb-1">{k}</div><code className="block font-mono break-all bg-raised border border-line rounded-lg px-3 py-2">{v}</code></div>
)
