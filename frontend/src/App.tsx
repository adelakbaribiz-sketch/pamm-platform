import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
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

function Protected({ children }: { children: React.ReactNode }) {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" />
  return <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Protected><Layout /></Protected>}>
          <Route index element={<Home />} />
          <Route path="managers" element={<Managers />} />
          <Route path="dashboard" element={<BrokerDashboard />} />
          <Route path="masters" element={<MasterAccounts />} />
          <Route path="investors" element={<Investors />} />
          <Route path="rollover" element={<Rollover />} />
          <Route path="investor-workspace" element={<InvestorWorkspace />} />
          <Route path="manager-workspace" element={<MoneyManagerWorkspace />} />
          <Route path="settlement" element={<Settlement />} />
          <Route path="mam" element={<Mam />} />
          <Route path="copy" element={<Copy />} />
          <Route path="sagas" element={<Sagas />} />
          <Route path="allocation" element={<Allocation />} />
          <Route path="latency" element={<Latency />} />
          <Route path="outbox" element={<Outbox />} />
          <Route path="adapters" element={<Adapters />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
