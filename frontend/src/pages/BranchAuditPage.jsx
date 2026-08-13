import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import AlertBanner from '../components/ui/AlertBanner.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import FormField from '../components/ui/FormField.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import SearchBar from '../components/ui/SearchBar.jsx'
import { TableSkeleton } from '../components/ui/Skeleton.jsx'

function formatWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 16)
  return d.toLocaleString()
}

export default function BranchAuditPage() {
  const navigate = useNavigate()
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [actionFilter, setActionFilter] = useState('all')

  useEffect(() => {
    api('/api/v1/branch/audit-logs?limit=200')
      .then(setLogs)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const actions = useMemo(() => {
    const set = new Set(logs.map((l) => l.action))
    return [...set].sort()
  }, [logs])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return logs.filter((log) => {
      if (actionFilter !== 'all' && log.action !== actionFilter) return false
      if (!q) return true
      return [log.action, log.message, log.username, log.application_id]
        .join(' ')
        .toLowerCase()
        .includes(q)
    })
  }, [logs, query, actionFilter])

  return (
    <>
      <PageHeader
        eyebrow="Compliance trail"
        title="Audit logs"
        badge={`${filtered.length} events`}
        description="Immutable branch activity — authentication, AI queue events, and accept / reject decisions with operator identity."
      />

      {error ? <AlertBanner type="error" title="Could not load audit logs" message={error} /> : null}

      <section className="panel panel-ink">
        <div className="search-toolbar" style={{ gridTemplateColumns: 'minmax(220px, 1.6fr) minmax(160px, 0.9fr)' }}>
          <SearchBar
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search action, message, user, application…"
          />
          <FormField label="Action">
            <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)}>
              <option value="all">All actions</option>
              {actions.map((action) => (
                <option key={action} value={action}>{action.replaceAll('_', ' ')}</option>
              ))}
            </select>
          </FormField>
        </div>

        <div className="table-wrap" style={{ marginTop: '0.85rem' }}>
          {loading ? (
            <TableSkeleton rows={8} cols={5} />
          ) : filtered.length ? (
            <table className="data-grid dense">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Operator</th>
                  <th>Message</th>
                  <th>Application</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((log) => (
                  <tr key={log.id}>
                    <td>{formatWhen(log.created_at)}</td>
                    <td>
                      <span className={`audit-chip ${log.action}`}>
                        {log.action.replaceAll('_', ' ')}
                      </span>
                    </td>
                    <td>{log.username || 'system'}</td>
                    <td>{log.message}</td>
                    <td className="mono-cell">
                      {log.application_id ? (
                        <button
                          type="button"
                          className="linkish"
                          onClick={() => navigate(`/branch/applications/${log.application_id}`)}
                        >
                          {String(log.application_id).slice(0, 8)}…
                        </button>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              icon="🔒"
              title="No audit entries"
              description="Branch activity will appear here as operators use the console."
            />
          )}
        </div>
      </section>
    </>
  )
}
