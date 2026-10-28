import React from 'react'
import { Routes, Route, Navigate, useLocation, Link } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import { canAccess } from './nav'
import { EmptyState } from './components/ui'
import Layout from './components/Layout'
import Login from './pages/Login'
import BrokerDashboard from './pages/BrokerDashboard'
import MasterAccounts from './pages/MasterAccounts'
import Investors from './pages/Investors'
import Rollover from './pages/Rollover'
import InvestorWorkspace from './pages/InvestorWorkspace'
import MoneyManagerWorkspace from './pages/MoneyManagerWorkspace'
import Settlement from './pages/Settlement'
import Mam from './pages/Mam'
import Copy from './pages/Copy'
import Sagas from './pages/Sagas'
import Allocation from './pages/Allocation'
import Latency from './pages/Latency'
import Outbox from './pages/Outbox'
import Adapters from './pages/Adapters'
import Home from './pages/Home'
import Managers from './pages/Managers'
import StrategyDetail from './pages/StrategyDetail'

function Protected({ children }: { children: React.ReactNode }) {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" />
  return <>{children}</>
}

/** Route-level role check mirroring the sidebar; the API still enforces authorization. */
function RoleGate({ children }: { children: React.ReactNode }) {
  const { session } = useAuth()
  const loc = useLocation()
  if (!canAccess(loc.pathname, session?.role)) {
    return (
      <div className="card">
        <EmptyState icon="shield" title="This area isn't available for your role"
          hint="Switch to a demo account with the required role, or return to the overview."
          action={<Link to="/" className="btn-primary">Back to overview</Link>} />
      </div>
    )
  }
  return <>{children}</>
}

const page = (el: React.ReactNode) => <RoleGate>{el}</RoleGate>

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Protected><Layout /></Protected>}>
          <Route index element={<Home />} />
          <Route path="strategy/:masterId" element={<StrategyDetail />} />
          <Route path="managers" element={page(<Managers />)} />
          <Route path="dashboard" element={page(<BrokerDashboard />)} />
          <Route path="masters" element={page(<MasterAccounts />)} />
          <Route path="investors" element={page(<Investors />)} />
          <Route path="rollover" element={page(<Rollover />)} />
          <Route path="investor-workspace" element={page(<InvestorWorkspace />)} />
          <Route path="manager-workspace" element={page(<MoneyManagerWorkspace />)} />
          <Route path="settlement" element={page(<Settlement />)} />
          <Route path="mam" element={page(<Mam />)} />
          <Route path="copy" element={page(<Copy />)} />
          <Route path="sagas" element={page(<Sagas />)} />
          <Route path="allocation" element={page(<Allocation />)} />
          <Route path="latency" element={page(<Latency />)} />
          <Route path="outbox" element={page(<Outbox />)} />
          <Route path="adapters" element={page(<Adapters />)} />
          <Route path="*" element={<div className="card"><EmptyState icon="info" title="Page not found" action={<Link to="/" className="btn-primary">Back to overview</Link>} /></div>} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
