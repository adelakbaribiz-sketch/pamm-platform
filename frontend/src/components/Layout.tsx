import React, { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

const NAV = [
  { to: '/', label: 'خانه', roles: ['broker_admin', 'money_manager', 'investor', 'compliance', 'super_admin'] },
  { to: '/managers', label: 'مدیران', roles: ['broker_admin', 'money_manager', 'investor', 'compliance', 'super_admin'] },
  { to: '/dashboard', label: 'داشبورد', roles: ['broker_admin', 'money_manager', 'super_admin'] },
  { to: '/masters', label: 'اکانت‌های مستر', roles: ['broker_admin', 'money_manager', 'super_admin'] },
  { to: '/investors', label: 'سرمایه‌گذاران', roles: ['broker_admin', 'investor', 'super_admin'] },
  { to: '/rollover', label: 'تخصیص مجدد', roles: ['broker_admin', 'money_manager', 'super_admin'] },
  { to: '/investor-workspace', label: 'فضای سرمایه‌گذار', roles: ['investor', 'broker_admin', 'super_admin'] },
  { to: '/manager-workspace', label: 'فضای مدیر', roles: ['money_manager', 'broker_admin', 'super_admin'] },
  { to: '/settlement', label: 'تسویه و اثبات‌ها', roles: ['broker_admin', 'compliance', 'investor', 'money_manager', 'super_admin'] },
  { to: '/mam', label: 'تخصیص MAM', roles: ['broker_admin', 'money_manager', 'super_admin'] },
  { to: '/copy', label: 'کپی تریدینگ', roles: ['broker_admin', 'money_manager', 'investor', 'super_admin'] },
  { to: '/sagas', label: 'ساگاها', roles: ['broker_admin', 'money_manager', 'compliance', 'super_admin'] },
  { to: '/allocation', label: 'تخصیص P-1', roles: ['broker_admin', 'money_manager', 'super_admin'] },
  { to: '/latency', label: 'تأخیر P-2', roles: ['broker_admin', 'money_manager', 'super_admin'] },
  { to: '/outbox', label: 'Outbox', roles: ['broker_admin', 'super_admin'] },
  { to: '/adapters', label: 'آداپتورها', roles: ['broker_admin', 'super_admin'] },
]

export default function Layout() {
  const { session, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(true)
  const items = NAV.filter(i => !session || i.roles.includes(session.role))
  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100">
      <aside className={`${open ? 'w-64' : 'w-16'} transition-all bg-slate-900 text-slate-100 flex flex-col`}>
        <div className="p-4 font-bold border-b border-slate-700 cursor-pointer" onClick={() => setOpen(!open)}>
          {open ? 'پلتفرم PAMM' : 'P'}
        </div>
        <nav className="flex-1 py-2 overflow-y-auto">
          {items.map(i => (
            <NavLink key={i.to} to={i.to}
              className={({isActive}) =>
                `block px-4 py-2 text-sm hover:bg-slate-800 ${isActive ? 'bg-brand-700 border-l-4 border-brand-500' : ''}`}>
              {open ? i.label : '•'}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-700 text-xs">
          {open && <div className="mb-1 truncate">{session?.user_id}</div>}
          {open && <div className="mb-2 text-slate-400">{session?.role}</div>}
          <button onClick={() => { logout(); navigate('/login') }}
            className="text-xs text-slate-400 hover:text-white">Sign out</button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <div className="p-6 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
