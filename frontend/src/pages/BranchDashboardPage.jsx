import { useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import { api } from '../api'
import DashboardCharts from '../components/dashboard/DashboardCharts.jsx'
import StatusPill from '../components/StatusPill.jsx'
import AlertBanner from '../components/ui/AlertBanner.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import Button from '../components/ui/Button.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import { DashboardSkeleton } from '../components/ui/Skeleton.jsx'

function formatWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 16)
  return d.toLocaleString()
}

function AnimatedValue({ value }) {
  const [display, setDisplay] = useState(0)
  const target = Number(value) || 0

  useEffect(() => {
    if (target === 0) {
      setDisplay(0)
      return undefined
    }
    let frame
    const start = performance.now()
    const duration = 600
    function tick(now) {
      const progress = Math.min((now - start) / duration, 1)
      setDisplay(Math.round(target * progress))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target])

  return <>{display}</>
}

const METRIC_ICONS = {
  total: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 7h16M4 12h16M4 17h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  pending: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" />
      <path d="M12 8v4l2.5 1.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  analyzing: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
    </svg>
  ),
  completed: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="4" y="4" width="16" height="16" rx="3" stroke="currentColor" strokeWidth="2" />
    </svg>
  ),
  accepted: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  rejected: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M8 8l8 8M16 8l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
    </svg>
  ),
}

const METRICS = [
  { key: 'total', label: 'All applications', accent: '#0055a4', iconBg: '#e8f2fb' },
  { key: 'pending', label: 'Pending Cognexa AI', accent: '#d97706', iconBg: '#fff8eb' },
  { key: 'analyzing', label: 'Analyzing now', accent: '#0891b2', iconBg: '#ecfeff' },
  { key: 'completed', label: 'Ready to decide', accent: '#2563eb', iconBg: '#eff6ff' },
  { key: 'accepted', label: 'Accepted', accent: '#059669', iconBg: '#ecfdf5' },
  { key: 'rejected', label: 'Rejected', accent: '#dc2626', iconBg: '#fef2f2' },
]

export default function BranchDashboardPage() {
  const navigate = useNavigate()
  const { user } = useOutletContext()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  async function refresh() {
    try {
      const payload = await api('/api/v1/branch/dashboard')
      setData(payload)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    refresh()
    const timer = setInterval(() => {
      refresh().catch(() => {})
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  if (!data && !error) {
    return <DashboardSkeleton />
  }

  const counts = data?.counts || {}

  return (
    <>
      <PageHeader
        eyebrow="Branch operations"
        title={user.branch.name}
        badge="Live dashboard"
        description="Operational view of queue health, decisions, applicant activity, and audit trail. Refreshes every 5 seconds."
        actions={
          <>
            <Button variant="secondary" onClick={() => refresh()}>Refresh</Button>
            <Link to="/branch/queue" className="btn">Open queue</Link>
          </>
        }
      >
        <div className="page-header-pills">
          <span className="page-pill">Queue · <strong>{data?.queue_size ?? 0}</strong></span>
          <span className="page-pill">Acceptance · <strong>{data?.acceptance_rate ?? 0}%</strong></span>
          <span className="page-pill">Branch · <strong>{user.branch.code}</strong></span>
        </div>
      </PageHeader>

      {error ? (
        <AlertBanner type="error" title="Could not load dashboard" message={error} />
      ) : null}

      <section className="dash-grid-v2">
        {METRICS.map((metric, index) => (
          <article
            key={metric.key}
            className="dash-metric-card"
            style={{
              '--metric-accent': metric.accent,
              '--metric-icon-bg': metric.iconBg,
              animationDelay: `${index * 0.05}s`,
            }}
          >
            <div className="dash-metric-icon">{METRIC_ICONS[metric.key]}</div>
            <span className="dash-metric-label">{metric.label}</span>
            <strong className="dash-metric-value">
              <AnimatedValue value={counts[metric.key] ?? 0} />
            </strong>
          </article>
        ))}
      </section>

      <DashboardCharts counts={counts} acceptanceRate={data?.acceptance_rate ?? 0} />

      <div className="split-panels">
        <section className="panel panel-accent">
          <div className="panel-head">
            <div>
              <h2>Recent applications</h2>
              <p className="hint">Newest submissions with contact and employment signals.</p>
            </div>
            <Link className="btn btn-secondary" to="/branch/queue">Open queue</Link>
          </div>

          <div className="table-wrap">
            {(data?.recent_applications || []).length ? (
              <table className="data-grid dense">
                <thead>
                  <tr>
                    <th>Applicant</th>
                    <th>CNIC</th>
                    <th>Mobile</th>
                    <th>Company / role</th>
                    <th>Income</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_applications.map((a) => (
                    <tr key={a.id} onClick={() => navigate(`/branch/applications/${a.id}`)} title="Open application">
                      <td>
                        <strong>{a.full_name}</strong>
                        <div className="meta">{a.email}</div>
                      </td>
                      <td>{a.cnic_number}</td>
                      <td>{a.mobile_number}</td>
                      <td>
                        {a.company_name}
                        <div className="meta">{a.designation || '—'}</div>
                      </td>
                      <td>{a.monthly_income || '—'}</td>
                      <td><StatusPill status={a.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState
                icon="📋"
                title="No applications yet"
                description="Customer portal submissions will appear here once received."
                actionLabel="Open queue"
                onAction={() => navigate('/branch/queue')}
              />
            )}
          </div>
        </section>

        <section className="panel panel-warm">
          <div className="panel-head">
            <div>
              <h2>Latest audit activity</h2>
              <p className="hint">Logins, Cognexa AI runs, accepts, rejects, and queue events.</p>
            </div>
            <Link className="btn btn-secondary" to="/branch/audit">All logs</Link>
          </div>

          <ul className="audit-feed">
            {(data?.recent_audit || []).length ? (
              data.recent_audit.map((log) => (
                <li key={log.id}>
                  <div className="audit-feed-top">
                    <span className={`audit-chip ${log.action}`}>{log.action.replaceAll('_', ' ')}</span>
                    <time>{formatWhen(log.created_at)}</time>
                  </div>
                  <p>{log.message}</p>
                  <div className="meta">
                    {log.username || 'system'}
                    {log.application_id ? ` · ${String(log.application_id).slice(0, 8)}…` : ''}
                  </div>
                </li>
              ))
            ) : (
              <li>
                <EmptyState
                  icon="📝"
                  title="No audit events"
                  description="Branch activity will be recorded here automatically."
                />
              </li>
            )}
          </ul>
        </section>
      </div>
    </>
  )
}
