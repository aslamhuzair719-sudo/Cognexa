import { useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import { api } from '../api'
import StatusPill from '../components/StatusPill.jsx'
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
  const cards = [
    { key: 'total', label: 'All applications', tone: 'tone-ink' },
    { key: 'pending', label: 'Pending AI', tone: 'tone-amber' },
    { key: 'analyzing', label: 'Analyzing now', tone: 'tone-cyan' },
    { key: 'completed', label: 'Ready to decide', tone: 'tone-blue' },
    { key: 'accepted', label: 'Accepted', tone: 'tone-green' },
    { key: 'rejected', label: 'Rejected', tone: 'tone-rose' },
  ]

  return (
    <>
      <section className="hero hero-branch">
        <span className="ai-badge">Live branch pulse</span>
        <h1>{user.branch.name}</h1>
        <p>
          Full operational view for this branch — queue health, decisions, applicant activity,
          and the latest audit trail. Refreshes automatically.
        </p>
        <div className="hero-row">
          <span className="hero-pill">Queue size · {data?.queue_size ?? 0}</span>
          <span className="hero-pill">Acceptance · {data?.acceptance_rate ?? 0}%</span>
          <span className="hero-pill">Code · {user.branch.code}</span>
        </div>
      </section>

      {error ? <p className="status-line error shake">{error}</p> : null}

      <section className="dash-grid">
        {cards.map((card) => (
          <article key={card.key} className={`dash-card ${card.tone}`}>
            <span className="dash-card-label">{card.label}</span>
            <strong className="dash-card-value">
              <AnimatedValue value={counts[card.key] ?? 0} />
            </strong>
          </article>
        ))}
      </section>

      <div className="split-panels">
        <section className="panel panel-accent">
          <div className="panel-head">
            <div>
              <h2>Recent applications</h2>
              <p className="hint">Newest submissions with full contact & employment signals.</p>
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
              <p className="hint">Logins, AI runs, accepts, rejects, and queue events.</p>
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
