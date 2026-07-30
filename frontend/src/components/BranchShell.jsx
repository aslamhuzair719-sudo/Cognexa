import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from '../api'
import BrandHeader from './BrandHeader.jsx'

const NAV = [
  { to: '/branch', end: true, label: 'Dashboard' },
  { to: '/branch/queue', end: false, label: 'Queue' },
  { to: '/branch/history', end: false, label: 'History' },
  { to: '/branch/audit', end: false, label: 'Audit' },
  { to: '/branch/scan', end: false, label: 'Scan' },
  { to: '/branch/signatures', end: false, label: 'Signature Scan' },
]

export default function BranchShell() {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)

  useEffect(() => {
    api('/api/v1/auth/me')
      .then(setUser)
      .catch(() => navigate('/branch/login', { replace: true }))
  }, [navigate])

  async function logout() {
    await api('/api/v1/auth/logout', { method: 'POST' })
    navigate('/branch/login')
  }

  if (!user) {
    return (
      <div className="branch-workspace">
        <div className="shell"><p className="hint">Authenticating session…</p></div>
      </div>
    )
  }

  return (
    <div className="branch-workspace">
      <div className="shell wide">
        <BrandHeader
          variant="bar"
          subtitle={user.branch.name}
          actionTo="/"
          actionLabel="Customer portal"
          rightSlot={
            <>
              <span className="ai-badge">Branch console</span>
              <span className="user-chip">{user.username}</span>
              <button type="button" className="btn btn-secondary" onClick={logout}>Sign out</button>
            </>
          }
        />

        <nav className="branch-nav" aria-label="Branch sections">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `branch-nav-link${isActive ? ' active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <Outlet context={{ user }} />
      </div>
    </div>
  )
}
