import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import QueueEta from '../components/QueueEta.jsx'
import StatusPill, { SourcePill } from '../components/StatusPill.jsx'
import AlertBanner from '../components/ui/AlertBanner.jsx'
import Button from '../components/ui/Button.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import FormField from '../components/ui/FormField.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import SearchBar from '../components/ui/SearchBar.jsx'
import { TableSkeleton } from '../components/ui/Skeleton.jsx'

export default function BranchQueuePage() {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [sortBy, setSortBy] = useState('newest')
  const [listSyncedAt, setListSyncedAt] = useState(0)

  async function refreshList() {
    try {
      const data = await api('/api/v1/branch/records')
      setRows(data)
      setListSyncedAt(Date.now())
      setListError('')
      return data
    } catch (err) {
      setListError(err.message)
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
      list = list.filter((a) => ['pending', 'analyzing', 'completed', 'saved', 'review_required', 'failed'].includes(a.status))
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

  const autoRefresh = rows.some((a) => ['pending', 'analyzing'].includes(a.status))

  return (
    <>
      <PageHeader
        eyebrow="Work queue"
        title="Applications in motion"
        badge={`${filtered.length} records`}
        description="Customer Portal submissions and Branch Entry scans in one grid. Filter by source or status, then open a row for the full record."
        actions={
          <Button variant="secondary" onClick={() => refreshList()} loading={loading}>
            Refresh
          </Button>
        }
      />

      {listError ? (
        <AlertBanner type="error" title="Could not load queue" message={listError} />
      ) : null}

        {autoRefresh ? (
        <AlertBanner
          type="info"
          title="Processing in progress"
          message="The queue refreshes every 4 seconds while applications or workflow customers are pending or analyzing."
        />
      ) : null}

      <section className="panel panel-accent">
        <div className="search-toolbar">
          <SearchBar
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, CNIC, email, company, ID…"
          />
          <FormField label="Source">
            <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
              <option value="all">All sources</option>
              <option value="customer_portal">Customer Portal</option>
              <option value="branch_entry">Branch Entry</option>
            </select>
          </FormField>
          <FormField label="Status">
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="active">Active (pending / analyzing / completed / saved)</option>
              <option value="all">All statuses</option>
              <option value="pending">Pending</option>
              <option value="analyzing">Analyzing</option>
              <option value="completed">Completed</option>
              <option value="saved">Saved</option>
              <option value="review_required">Review required</option>
              <option value="failed">Failed</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
            </select>
          </FormField>
          <FormField label="Sort">
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="newest">Newest first</option>
              <option value="name">Name A–Z</option>
              <option value="status">Status</option>
              <option value="source">Source</option>
            </select>
          </FormField>
        </div>

        <p className="hint" style={{ marginTop: '0.85rem' }}>
          Showing {filtered.length} of {rows.length} record(s)
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
                    <td>
                      <div className="queue-status-cell">
                        <StatusPill status={a.status} />
                        <QueueEta eta={a.queue_eta} syncedAt={listSyncedAt} compact />
                      </div>
                    </td>
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
