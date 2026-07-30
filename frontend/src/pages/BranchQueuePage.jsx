import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import StatusPill, { SourcePill } from '../components/StatusPill.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import SearchBar from '../components/ui/SearchBar.jsx'
import { TableSkeleton } from '../components/ui/Skeleton.jsx'

export default function BranchQueuePage() {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [listStatus, setListStatus] = useState('')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [sortBy, setSortBy] = useState('newest')

  async function refreshList() {
    try {
      const data = await api('/api/v1/branch/records')
      setRows(data)
      setListStatus('')
      return data
    } catch (err) {
      setListStatus(err.message)
      throw err
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshList().catch(() => {})
  }, [])

  useEffect(() => {
    const hasActive = rows.some((a) => a.status === 'pending' || a.status === 'analyzing')
    if (!hasActive) return undefined
    const timer = setInterval(() => {
      refreshList().catch(() => {})
    }, 4000)
    return () => clearInterval(timer)
  }, [rows])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    let list = [...rows]
    if (sourceFilter !== 'all') {
      list = list.filter((a) => a.source === sourceFilter)
    }
    if (statusFilter === 'active') {
      list = list.filter((a) => ['pending', 'analyzing', 'completed', 'saved'].includes(a.status))
    } else if (statusFilter !== 'all') {
      list = list.filter((a) => a.status === statusFilter)
    }
    if (q) {
      list = list.filter((a) =>
        [
          a.full_name,
          a.cnic_number,
          a.email,
          a.mobile_number,
          a.company_name,
          a.designation,
          a.source,
          a.id,
        ]
          .join(' ')
          .toLowerCase()
          .includes(q),
      )
    }
    list.sort((a, b) => {
      if (sortBy === 'name') return String(a.full_name || '').localeCompare(String(b.full_name || ''))
      if (sortBy === 'status') return String(a.status || '').localeCompare(String(b.status || ''))
      if (sortBy === 'source') return String(a.source || '').localeCompare(String(b.source || ''))
      return String(b.created_at || '').localeCompare(String(a.created_at || ''))
    })
    return list
  }, [rows, query, statusFilter, sourceFilter, sortBy])

  function openRow(row) {
    if (row.source === 'branch_entry') {
      navigate(`/branch/entries/${row.id}`)
      return
    }
    navigate(`/branch/applications/${row.id}`)
  }

  return (
    <>
      <section className="hero hero-branch">
        <span className="ai-badge">Work queue</span>
        <h1>Applications in motion</h1>
        <p>
          Customer Portal submissions and Branch Entry scans in one grid.
          Filter by source or status, then open a row for the full record.
        </p>
      </section>

      <section className="panel panel-accent">
        <div className="search-toolbar">
          <SearchBar
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, CNIC, email, company, ID…"
          />
          <label className="field">Source
            <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
              <option value="all">All sources</option>
              <option value="customer_portal">Customer Portal</option>
              <option value="branch_entry">Branch Entry</option>
            </select>
          </label>
          <label className="field">Status
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="active">Active (pending / analyzing / completed / saved)</option>
              <option value="all">All statuses</option>
              <option value="pending">Pending</option>
              <option value="analyzing">Analyzing</option>
              <option value="completed">Completed</option>
              <option value="saved">Saved</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label className="field">Sort
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="newest">Newest first</option>
              <option value="name">Name A–Z</option>
              <option value="status">Status</option>
              <option value="source">Source</option>
            </select>
          </label>
          <button type="button" className="btn btn-secondary" onClick={() => refreshList()}>
            Refresh
          </button>
        </div>

        <p className="hint" style={{ marginTop: '0.85rem' }}>
          {listStatus || `${filtered.length} record(s)`}
          {rows.some((a) => a.status === 'pending' || a.status === 'analyzing')
            ? ' · Auto-refresh every 4s while AI is running'
            : ''}
        </p>

        <div className="table-wrap" style={{ marginTop: '0.85rem' }}>
          {loading ? (
            <TableSkeleton rows={6} cols={7} />
          ) : filtered.length ? (
            <table className="data-grid dense">
              <thead>
                <tr>
                  <th>Applicant</th>
                  <th>Source</th>
                  <th>CNIC</th>
                  <th>Mobile</th>
                  <th>Docs</th>
                  <th>Submitted</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr key={`${a.source}-${a.id}`} onClick={() => openRow(a)} title="Open record">
                    <td>
                      <strong>{a.full_name}</strong>
                      <div className="meta">{a.email || a.company_name || '—'}</div>
                    </td>
                    <td><SourcePill source={a.source} /></td>
                    <td>{a.cnic_number || '—'}</td>
                    <td>{a.mobile_number || '—'}</td>
                    <td>{a.document_count ?? (a.source === 'customer_portal' ? 4 : '—')}</td>
                    <td>{(a.created_at || '').slice(0, 10)}</td>
                    <td><StatusPill status={a.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              icon="🔍"
              title="No records match"
              description="Try adjusting your search or filters to find applications."
            />
          )}
        </div>
      </section>
    </>
  )
}
