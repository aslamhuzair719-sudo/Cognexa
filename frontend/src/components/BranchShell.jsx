import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'

const NAV_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { to: '/branch', end: true, label: 'Dashboard', icon: 'grid' },
      { to: '/branch/queue', end: false, label: 'Queue', icon: 'list' },
      { to: '/branch/history', end: false, label: 'History', icon: 'clock' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { to: '/branch/scan', end: false, label: 'Document Scan', icon: 'camera' },
      { to: '/branch/signatures', end: false, label: 'Signatures', icon: 'pen' },
    ],
  },
  {
    label: 'Compliance',
    items: [
      { to: '/branch/audit', end: false, label: 'Audit Log', icon: 'shield' },
    ],
  },
]

const PAGE_TITLES = {
  '/branch': 'Dashboard',
  '/branch/queue': 'Work Queue',
  '/branch/history': 'History',
  '/branch/audit': 'Audit Log',
  '/branch/scan': 'Document Scan',
  '/branch/signatures': 'Signature Scan',
}

function NavIcon({ type }) {
  const props = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', 'aria-hidden': true }
  switch (type) {
    case 'grid':
      return (
        <svg {...props}>
          <rect x="3" y="3" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          <rect x="13" y="3" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          <rect x="3" y="13" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          <rect x="13" y="13" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      )
    case 'list':
      return (
        <svg {...props}>
          <path d="M5 7h14M5 12h14M5 17h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      )
    case 'clock':
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.8" />
          <path d="M12 8v4l3 1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      )
    case 'shield':
      return (
        <svg {...props}>
          <path d="M12 3l7 3v5.5c0 5.25-3.5 8.75-7 9-3.5-.25-7-3.75-7-9V6l7-3Z" stroke="currentColor" strokeWidth="1.8" />
          <path d="M9.5 12.5 11 14l3.5-3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case 'camera':
      return (
        <svg {...props}>
          <rect x="4" y="7" width="16" height="12" rx="3" stroke="currentColor" strokeWidth="1.8" />
          <path d="M8 7 9.5 4.5h5L16 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="12" cy="13" r="3" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      )
    case 'pen':
      return (
        <svg {...props}>
          <path d="m7 17 4 4 9-9-4-4-9 9Z" stroke="currentColor" strokeWidth="1.8" />
          <path d="m12 6 6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      )
    default:
      return null
  }
}

function userInitials(username) {
  const parts = String(username || 'U').split(/[\s._-]+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return String(username || 'U').slice(0, 2).toUpperCase()
}

export default function BranchShell() {
  const navigate = useNavigate()
  const location = useLocation()
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
      <div className="branch-app">
        <div className="branch-main" style={{ marginLeft: 0 }}>
          <div className="branch-main-content">
            <p className="hint">Authenticating session…</p>
          </div>
        </div>
      </div>
    )
  }

  const pageTitle = PAGE_TITLES[location.pathname] || 'Branch Console'

  return (
    <div className="branch-app">
      <aside className="branch-sidebar" aria-label="Branch navigation">
        <div className="branch-sidebar-brand">
          <img src="/ubl-logo.png" alt="UBL" />
          <p className="branch-sidebar-product">Cognexa Verification</p>
          <p className="branch-sidebar-abbr">Cognexa Console</p>
          <p className="branch-sidebar-branch">{user.branch.name}</p>
        </div>

        <nav className="branch-sidebar-nav">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              <p className="nav-section-label">{section.label}</p>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `branch-sidebar-link${isActive ? ' active' : ''}`
                  }
                >
                  <span className="sidebar-link-icon">
                    <NavIcon type={item.icon} />
                  </span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="branch-sidebar-footer">
          <div className="sidebar-user-card">
            <div className="sidebar-user-avatar">{userInitials(user.username)}</div>
            <div>
              <p className="sidebar-user-name">{user.username}</p>
              <p className="sidebar-user-role">Branch operator · {user.branch.code}</p>
            </div>
          </div>
          <div className="sidebar-footer-actions">
            <a className="btn-sidebar" href="/">Customer portal</a>
            <button type="button" className="btn-sidebar btn-sidebar-danger" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <div className="branch-main">
        <header className="branch-main-topbar">
          <div>
            <p className="branch-main-topbar-title">{pageTitle}</p>
            <p className="branch-main-topbar-meta">
              {user.branch.name} · Code {user.branch.code}
            </p>
          </div>
          <span className="branch-live-badge">Live</span>
        </header>

        <main className="branch-main-content">
          <Outlet context={{ user }} />
        </main>
      </div>
    </div>
  )
}
