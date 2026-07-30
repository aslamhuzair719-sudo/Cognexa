import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import StatusPill from '../components/StatusPill.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import SearchBar from '../components/ui/SearchBar.jsx'
import { TableSkeleton } from '../components/ui/Skeleton.jsx'

function formatWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 16)
  return d.toLocaleString()
}

export default function BranchHistoryPage() {
  const navigate = useNavigate()
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [decisionFilter, setDecisionFilter] = useState('all')

  useEffect(() => {
    api('/api/v1/branch/applications?status=accepted,rejected')
      .then(setApps)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    let rows = [...apps]
    if (decisionFilter !== 'all') {
      rows = rows.filter((a) => a.status === decisionFilter)
    }
    if (q) {
      rows = rows.filter((a) =>
        [a.full_name, a.cnic_number, a.email, a.company_name, a.decision_note, a.id]
          .join(' ')
          .toLowerCase()
          .includes(q),
      )
    }
    rows.sort((a, b) => String(b.decided_at || b.created_at || '').localeCompare(String(a.decided_at || a.created_at || '')))
    return rows
  }, [apps, query, decisionFilter])

  const accepted = apps.filter((a) => a.status === 'accepted').length
  const rejected = apps.filter((a) => a.status === 'rejected').length

  return (
    <>
      <section className="hero hero-branch">
        <span className="ai-badge">Decision archive</span>
        <h1>Accepted & rejected history</h1>
        <p>
          Closed applications for this branch, including decision timestamps and reject notes.
        </p>
        <div className="hero-row">
          <span className="hero-pill tone-green-pill">Accepted · {accepted}</span>
          <span className="hero-pill tone-rose-pill">Rejected · {rejected}</span>
        </div>
      </section>

      <section className="panel panel-warm">
        <div className="search-toolbar" style={{ gridTemplateColumns: 'minmax(220px, 1.6fr) minmax(140px, 0.8fr)' }}>
          <SearchBar
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, CNIC, note…"
          />
          <label className="field">Decision
            <select value={decisionFilter} onChange={(e) => setDecisionFilter(e.target.value)}>
              <option value="all">Accepted + rejected</option>
              <option value="accepted">Accepted only</option>
              <option value="rejected">Rejected only</option>
            </select>
          </label>
        </div>

        {error ? <p className="status-line error shake">{error}</p> : null}

        <div className="table-wrap" style={{ marginTop: '0.85rem' }}>
          {loading ? (
            <TableSkeleton rows={5} cols={6} />
          ) : filtered.length ? (
            <table className="data-grid dense">
              <thead>
                <tr>
                  <th>Applicant</th>
                  <th>CNIC</th>
                  <th>Company</th>
                  <th>Decided</th>
                  <th>Outcome</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr key={a.id} onClick={() => navigate(`/branch/applications/${a.id}`)} title="Open application">
                    <td>
                      <strong>{a.full_name}</strong>
                      <div className="meta">{a.email}</div>
                    </td>
                    <td>{a.cnic_number}</td>
                    <td>{a.company_name}</td>
                    <td>{formatWhen(a.decided_at)}</td>
                    <td><StatusPill status={a.status} /></td>
                    <td className="note-cell">{a.decision_note || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              icon="📁"
              title="No decided applications"
              description="Accepted and rejected applications will appear here once decisions are made."
            />
          )}
        </div>
      </section>
    </>
  )
}
