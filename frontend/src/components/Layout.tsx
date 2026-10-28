import React, { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useTheme } from '../theme'
import { NAV_SECTIONS, NAV_ITEMS } from '../nav'
import { ROLE_LABEL, initials, prettyName } from '../format'
import { Icon } from './icons'

export function Brand({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="w-8 h-8 rounded-lg bg-brand-500 grid place-items-center shrink-0 shadow-sm">
        <svg viewBox="0 0 32 32" className="w-5 h-5"><path d="M8 21l5-6 4 3 7-9" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </span>
      {!compact && (
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight">PAMM Platform</div>
          <div className="text-[10px] uppercase tracking-wider text-subtle">Allocation suite</div>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const { session, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const navigate = useNavigate()
  const loc = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  useEffect(() => setMobileOpen(false), [loc.pathname])

  const current = NAV_ITEMS.find(i => i.to === loc.pathname)
  const name = session?.email?.split('@')[0]

  const nav = (compact: boolean) => (
    <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-5">
      {NAV_SECTIONS.map(sec => {
        const items = sec.items.filter(i => session && i.roles.includes(session.role))
        if (!items.length) return null
        return (
          <div key={sec.title}>
            {!compact && <div className="px-2 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-subtle">{sec.title}</div>}
            <div className="space-y-0.5">
              {items.map(i => (
                <NavLink key={i.to} to={i.to} end={i.to === '/'} title={compact ? i.label : undefined}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 rounded-lg px-2 h-8 text-[13px] transition-colors ${
                      isActive ? 'bg-brand-500/10 text-brand-600 dark:text-brand-400 font-medium' : 'text-muted hover:text-fg hover:bg-raised'
                    } ${compact ? 'justify-center' : ''}`}>
                  <Icon name={i.icon} className="w-4 h-4 shrink-0" />
                  {!compact && <span className="truncate">{i.label}</span>}
                </NavLink>
              ))}
            </div>
          </div>
        )
      })}
    </nav>
  )

  return (
    <div className="min-h-screen flex bg-bg">
      {/* Desktop sidebar */}
      <aside className={`hidden lg:flex ${collapsed ? 'w-[68px]' : 'w-60'} shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200 sticky top-0 h-screen`}>
        <div className={`h-14 flex items-center border-b border-line ${collapsed ? 'justify-center' : 'px-4'}`}><Brand compact={collapsed} /></div>
        {nav(collapsed)}
        <button onClick={() => setCollapsed(c => !c)} className="m-3 btn-quiet h-8 text-xs" aria-label="Toggle sidebar">
          <Icon name={collapsed ? 'chevronRight' : 'chevronLeft'} />
          {!collapsed && 'Collapse'}
        </button>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <aside className="relative w-64 max-w-[80%] flex flex-col bg-surface border-r border-line">
            <div className="h-14 flex items-center justify-between px-4 border-b border-line">
              <Brand />
              <button className="btn-quiet h-8 w-8 px-0" onClick={() => setMobileOpen(false)} aria-label="Close menu"><Icon name="x" /></button>
            </div>
            {nav(false)}
          </aside>
        </div>
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-14 sticky top-0 z-30 flex items-center gap-3 px-4 sm:px-6 border-b border-line bg-surface/85 backdrop-blur">
          <button className="lg:hidden btn-quiet h-8 w-8 px-0" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Icon name="menu" /></button>
          <div className="text-sm font-medium truncate">{current?.label || 'Strategy'}</div>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden md:inline-flex tag-mock" title="All broker connectivity is simulated in this prototype">
              <span className="w-1.5 h-1.5 rounded-full bg-violet-500" /> Demo environment · simulated broker
            </span>
            <button onClick={toggle} className="btn-quiet h-8 w-8 px-0" aria-label="Toggle theme" title="Toggle light/dark">
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            </button>
            <div className="flex items-center gap-2 pl-2 border-l border-line">
              <span className="w-8 h-8 rounded-full bg-brand-500/15 text-brand-600 dark:text-brand-400 grid place-items-center text-xs font-semibold">{initials(name)}</span>
              <div className="hidden sm:block leading-tight">
                <div className="text-xs font-medium">{prettyName(name)}</div>
                <div className="text-[11px] text-subtle">{ROLE_LABEL[session?.role || ''] || session?.role}</div>
              </div>
              <button onClick={() => { logout(); navigate('/login') }} className="btn-quiet h-8 w-8 px-0" aria-label="Sign out" title="Sign out">
                <Icon name="logout" />
              </button>
            </div>
          </div>
        </header>
        <main className="flex-1 min-w-0">
          <div className="px-4 sm:px-6 py-6 max-w-[1400px] mx-auto">
            <Outlet />
          </div>
        </main>
        <footer className="px-4 sm:px-6 py-4 text-[11px] text-subtle border-t border-line">
          Prototype for demonstration only. All balances, returns and trading activity shown are simulated and are not real or verified results.
        </footer>
      </div>
    </div>
  )
}
