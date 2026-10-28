import type { IconName } from './components/icons'

const ALL = ['broker_admin', 'money_manager', 'investor', 'compliance', 'super_admin']

export interface NavItem { to: string; label: string; icon: IconName; roles: string[] }

// Single source of truth for sidebar items and route-level role checks.
export const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: 'Overview',
    items: [
      { to: '/', label: 'Market overview', icon: 'home', roles: ALL },
      { to: '/managers', label: 'Managers', icon: 'users', roles: ALL },
      { to: '/dashboard', label: 'Broker dashboard', icon: 'grid', roles: ['broker_admin', 'money_manager', 'super_admin'] },
    ],
  },
  {
    title: 'Workspaces',
    items: [
      { to: '/investor-workspace', label: 'My portfolio', icon: 'wallet', roles: ['investor', 'broker_admin', 'super_admin'] },
      { to: '/manager-workspace', label: 'Manager desk', icon: 'briefcase', roles: ['money_manager', 'broker_admin', 'super_admin'] },
      { to: '/masters', label: 'Master accounts', icon: 'layers', roles: ['broker_admin', 'money_manager', 'super_admin'] },
      { to: '/investors', label: 'Investor accounts', icon: 'users', roles: ['broker_admin', 'investor', 'super_admin'] },
    ],
  },
  {
    title: 'Allocation',
    items: [
      { to: '/rollover', label: 'Rollovers', icon: 'refresh', roles: ['broker_admin', 'money_manager', 'super_admin'] },
      { to: '/settlement', label: 'Settlement & proofs', icon: 'shield', roles: ALL },
      { to: '/mam', label: 'MAM split', icon: 'split', roles: ['broker_admin', 'money_manager', 'super_admin'] },
      { to: '/copy', label: 'Copy trading', icon: 'copy', roles: ['broker_admin', 'money_manager', 'investor', 'super_admin'] },
      { to: '/allocation', label: 'Risk allocation', icon: 'target', roles: ['broker_admin', 'money_manager', 'super_admin'] },
    ],
  },
  {
    title: 'Infrastructure',
    items: [
      { to: '/sagas', label: 'Settlement sagas', icon: 'flow', roles: ['broker_admin', 'money_manager', 'compliance', 'super_admin'] },
      { to: '/latency', label: 'Latency model', icon: 'clock', roles: ['broker_admin', 'money_manager', 'super_admin'] },
      { to: '/outbox', label: 'Event outbox', icon: 'inbox', roles: ['broker_admin', 'super_admin'] },
      { to: '/adapters', label: 'Broker adapters', icon: 'plug', roles: ['broker_admin', 'super_admin'] },
    ],
  },
]

export const NAV_ITEMS = NAV_SECTIONS.flatMap(s => s.items)

export const canAccess = (path: string, role?: string) => {
  const item = NAV_ITEMS.find(i => i.to === path)
  return !item || (!!role && item.roles.includes(role))
}
