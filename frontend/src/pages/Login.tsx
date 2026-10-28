import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'

export default function Login() {
  const [email, setEmail] = useState('broker@demo.com')
  const [password, setPassword] = useState('Demo1234!')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const { setSession } = useAuth()
  const nav = useNavigate()

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const t = await api.login(email, password)
      setSession({ access_token: t.access_token, role: t.role, tenant_id: t.tenant_id, user_id: t.user_id })
      nav('/dashboard')
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <div className="card w-full max-w-md p-8 bg-slate-800 border-slate-700">
        <h1 className="text-2xl font-bold mb-1 text-white">PAMM Platform M3</h1>
        <p className="text-sm text-slate-400 mb-6">Sign in to your workspace</p>
        <form onSubmit={submit} className="space-y-4">
          <div><label className="label text-slate-400">Email</label>
            <input className="input" value={email} onChange={e => setEmail(e.target.value)} /></div>
          <div><label className="label text-slate-400">Password</label>
            <input type="password" className="input" value={password} onChange={e => setPassword(e.target.value)} /></div>
          {err && <div className="text-red-400 text-sm">{err}</div>}
          <button disabled={busy} className="btn-primary w-full">{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <div className="mt-6 text-xs text-slate-500 space-y-1">
          <div>Demo accounts (password: Demo1234!):</div>
          <div>• broker@demo.com — Broker Admin</div>
          <div>• manager@demo.com — Money Manager</div>
          <div>• investor1@demo.com / investor2@demo.com — Investor</div>
          <div>• compliance@demo.com — Compliance</div>
        </div>
      </div>
    </div>
  )
}
