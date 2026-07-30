import { Navigate, Route, Routes } from 'react-router-dom'
import BranchShell from './components/BranchShell.jsx'
import PageTransition from './components/ui/PageTransition.jsx'
import CustomerPage from './pages/CustomerPage.jsx'
import BranchLoginPage from './pages/BranchLoginPage.jsx'
import BranchDashboardPage from './pages/BranchDashboardPage.jsx'
import BranchQueuePage from './pages/BranchQueuePage.jsx'
import BranchHistoryPage from './pages/BranchHistoryPage.jsx'
import BranchAuditPage from './pages/BranchAuditPage.jsx'
import BranchApplicationPage from './pages/BranchApplicationPage.jsx'
import BranchScanPage from './pages/BranchScanPage.jsx'
import BranchSignaturesPage from './pages/BranchSignaturesPage.jsx'
import BranchEntryPage from './pages/BranchEntryPage.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<CustomerPage />} />
      <Route path="/branch/login" element={<BranchLoginPage />} />
      <Route path="/branch/applications/:id" element={<BranchApplicationPage />} />
      <Route path="/branch/entries/:id" element={<BranchEntryPage />} />
      <Route path="/branch" element={<BranchShell />}>
        <Route index element={<PageTransition><BranchDashboardPage /></PageTransition>} />
        <Route path="queue" element={<PageTransition><BranchQueuePage /></PageTransition>} />
        <Route path="history" element={<PageTransition><BranchHistoryPage /></PageTransition>} />
        <Route path="audit" element={<PageTransition><BranchAuditPage /></PageTransition>} />
        <Route path="scan" element={<PageTransition><BranchScanPage /></PageTransition>} />
        <Route path="signatures" element={<PageTransition><BranchSignaturesPage /></PageTransition>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
