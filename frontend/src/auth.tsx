import React, { createContext, useContext, useState } from 'react'

export interface Session {
  access_token: string
  role: string
  tenant_id: string | null
  user_id: string
}

const Ctx = createContext<{ session: Session | null; setSession: (s: Session | null) => void; logout: () => void }>({
  session: null, setSession: () => {}, logout: () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<Session | null>(() => {
    const t = localStorage.getItem('access_token')
    const r = localStorage.getItem('role')
    const tid = localStorage.getItem('tenant_id')
    const uid = localStorage.getItem('user_id')
    if (t && r && uid) return { access_token: t, role: r, tenant_id: tid ? JSON.parse(tid) : null, user_id: uid }
    return null
  })
  const setSession = (s: Session | null) => {
    if (s) {
      localStorage.setItem('access_token', s.access_token)
      localStorage.setItem('role', s.role)
      localStorage.setItem('tenant_id', JSON.stringify(s.tenant_id))
      localStorage.setItem('user_id', s.user_id)
    } else { localStorage.clear() }
    setSessionState(s)
  }
  const logout = () => setSession(null)
  return <Ctx.Provider value={{ session, setSession, logout }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
