import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, downloadUrl } from '../api'
import { AiActivityPanel } from '../components/AiActivityPanel.jsx'
import BrandHeader from '../components/BrandHeader.jsx'
import ReportView from '../components/ReportView.jsx'
import StatusPill from '../components/StatusPill.jsx'

const DOC_LABELS = {
  cnic_front: 'CNIC front',
  cnic_back: 'CNIC back',
  payslip: 'Payslip',
  bank_statement: 'Bank statement',
}

export default function BranchApplicationPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [user, setUser] = useState(null)
  const [detail, setDetail] = useState(null)
  const [report, setReport] = useState(null)
  const [status, setStatus] = useState('Loading…')
  const [actionStatus, setActionStatus] = useState('')
  const [decideStatus, setDecideStatus] = useState('')
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectNote, setRejectNote] = useState('')
  const [queueing, setQueueing] = useState(false)

  async function load() {
    const app = await api(`/api/v1/branch/applications/${id}`)
    setDetail(app)
    if (app.has_report) {
      try {
        const reportData = await api(`/api/v1/branch/applications/${id}/report`)
        setReport(reportData)
      } catch {
        setReport(null)
      }
    } else {
      setReport(null)
    }
    setStatus('')
    return app
  }

  useEffect(() => {
    api('/api/v1/auth/me')
      .then((me) => {
        setUser(me)
        return load()
      })
      .catch(() => navigate('/branch/login', { replace: true }))
  }, [id, navigate])

  useEffect(() => {
    if (!detail) return undefined
    if (!['pending', 'analyzing'].includes(detail.status)) return undefined
    const timer = setInterval(() => {
      load().catch(() => {})
    }, 4000)
    return () => clearInterval(timer)
  }, [detail?.status, id])

  async function requeueAnalysis() {
    setQueueing(true)
    setActionStatus('Queuing AI analysis…')
    try {
      const result = await api(`/api/v1/branch/applications/${id}/analyze`, {
        method: 'POST',
      })
      setActionStatus(result.message || 'Queued.')
      await load()
    } catch (err) {
      setActionStatus(err.message)
    } finally {
      setQueueing(false)
    }
  }

  async function decide(decision) {
    if (decision === 'reject' && !rejectNote.trim()) {
      setDecideStatus('Rejection reason is required.')
      return
    }
    setDecideStatus(decision === 'accept' ? 'Accepting…' : 'Rejecting…')
    try {
      await api(`/api/v1/branch/applications/${id}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          note: decision === 'reject' ? rejectNote.trim() : undefined,
        }),
      })
      setDecideStatus(decision === 'accept' ? 'Application accepted.' : 'Application rejected.')
      setRejectOpen(false)
      setRejectNote('')
      await load()
    } catch (err) {
      setDecideStatus(err.message)
    }
  }

  if (!user || !detail) {
    return (
      <div className="mesh-workspace">
        <div className="shell">
          <p className="hint">{status || 'Loading application…'}</p>
        </div>
      </div>
    )
  }

  const canDecide = ['completed', 'accepted', 'rejected'].includes(detail.status)
  const canRequeue = !['accepted', 'rejected', 'analyzing'].includes(detail.status)

  return (
    <div className="mesh-workspace">
    <div className="shell wide">
      <BrandHeader
        variant="bar"
        subtitle={user.branch.name}
        actionTo="/branch"
        actionLabel="Back to grid"
        rightSlot={<span className="ai-badge">Case review</span>}
      />

      <section className="panel">
        <div className="detail-header">
          <div>
            <p className="eyebrow">Application dossier</p>
            <h2>{detail.full_name}</h2>
            <p className="meta">ID {detail.id}</p>
          </div>
          <StatusPill status={detail.status} />
        </div>

        {['pending', 'analyzing'].includes(detail.status) || detail.ai_progress ? (
          <div className="ai-activity-wrap">
            <AiActivityPanel
              title="AI Activity"
              message={detail.ai_progress?.message}
              steps={detail.ai_progress?.steps || []}
              messages={
                detail.status === 'completed' || detail.ai_progress?.done
                  ? (detail.ai_progress?.messages?.length
                      ? detail.ai_progress.messages
                      : [
                          'Document parsing complete.',
                          'LLM summary complete.',
                          'AI analysis complete.',
                        ])
                  : (detail.ai_progress?.messages || [])
              }
              aiWorking={Boolean(detail.ai_progress?.ai_working)}
            />
          </div>
        ) : null}

        {['pending', 'analyzing'].includes(detail.status) ? (
          <p className="hint">
            {detail.status === 'pending'
              ? 'Waiting in the AI queue. This page refreshes automatically.'
              : 'AI analysis is running. This page refreshes automatically every few seconds.'}
          </p>
        ) : null}

        <div className="kv-grid">
          <div><span className="kv-label">Age</span><p>{detail.age || '—'}</p></div>
          <div><span className="kv-label">Email</span><p>{detail.email}</p></div>
          <div><span className="kv-label">Phone</span><p>{detail.mobile_number}</p></div>
          <div><span className="kv-label">Gender</span><p>{detail.gender || '—'}</p></div>
          <div><span className="kv-label">CNIC full name</span><p>{detail.cnic_full_name || detail.full_name}</p></div>
          <div><span className="kv-label">Father name</span><p>{detail.father_name}</p></div>
          <div><span className="kv-label">CNIC</span><p>{detail.cnic_number}</p></div>
          <div><span className="kv-label">Date of birth</span><p>{detail.date_of_birth}</p></div>
          <div><span className="kv-label">Issue date</span><p>{detail.cnic_issue_date || '—'}</p></div>
          <div><span className="kv-label">Expiry date</span><p>{detail.cnic_expiry_date || '—'}</p></div>
          <div><span className="kv-label">Country to stay</span><p>{detail.country_to_stay || '—'}</p></div>
          <div><span className="kv-label">Company</span><p>{detail.company_name}</p></div>
          <div><span className="kv-label">Designation</span><p>{detail.designation || '—'}</p></div>
          <div><span className="kv-label">Employee ID</span><p>{detail.employee_id}</p></div>
          <div><span className="kv-label">Monthly salary</span><p>{detail.monthly_income}</p></div>
        </div>

        <h3 style={{ marginTop: '1.25rem', marginBottom: '0.5rem' }}>Documents</h3>
        <div className="doc-gallery">
          {Object.entries(detail.documents || {}).map(([key, doc]) => {
            const isImage =
              doc.is_image ||
              /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(doc.filename || doc.path || '')
            const isPdf =
              doc.is_pdf || /\.pdf$/i.test(doc.filename || doc.path || '')
            return (
              <figure key={key} className="doc-card">
                <figcaption>
                  <span>{DOC_LABELS[key] || key}</span>
                  <a href={`${doc.url}?download=true`} target="_blank" rel="noreferrer">
                    Download
                  </a>
                </figcaption>
                {isImage ? (
                  <a href={doc.url} target="_blank" rel="noreferrer" className="doc-preview-link">
                    <img
                      src={doc.url}
                      alt={DOC_LABELS[key] || key}
                      className="doc-preview-image"
                    />
                  </a>
                ) : isPdf ? (
                  <iframe title={DOC_LABELS[key] || key} src={doc.url} className="doc-preview-pdf" />
                ) : (
                  <a className="doc-link" href={doc.url} target="_blank" rel="noreferrer">
                    Open file
                  </a>
                )}
              </figure>
            )
          })}
        </div>

        <div className="actions">
          <button
            type="button"
            className="btn"
            disabled={!canRequeue || queueing}
            onClick={requeueAnalysis}
          >
            {queueing ? 'Queuing…' : detail.has_report ? 'Re-queue AI analysis' : 'Queue AI analysis'}
          </button>
          {detail.has_report ? (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => downloadUrl(`/api/v1/branch/applications/${detail.id}/report/pdf`)}
            >
              Download PDF report
            </button>
          ) : null}
          <p className="status-line">{actionStatus}</p>
        </div>
      </section>

      {report ? <ReportView report={report} documents={detail.documents} /> : null}

      {canDecide ? (
        <section className="panel">
          <h2>Decision</h2>
          {detail.status === 'accepted' || detail.status === 'rejected' ? (
            <p className="hint">
              Current status: <strong>{detail.status}</strong>
              {detail.decision_note ? ` — ${detail.decision_note}` : ''}
            </p>
          ) : (
            <p className="hint">Accept the application or reject it with a reason.</p>
          )}
          <div className="actions">
            <button type="button" className="btn btn-pass" onClick={() => decide('accept')}>
              Accept
            </button>
            <button type="button" className="btn btn-fail" onClick={() => setRejectOpen(true)}>
              Reject
            </button>
          </div>
          {rejectOpen ? (
            <div style={{ marginTop: '1rem' }}>
              <label className="field full">Rejection reason
                <textarea
                  rows={3}
                  value={rejectNote}
                  onChange={(e) => setRejectNote(e.target.value)}
                  placeholder="Describe why this application is rejected"
                />
              </label>
              <div className="actions">
                <button type="button" className="btn btn-fail" onClick={() => decide('reject')}>
                  Confirm reject
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setRejectOpen(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : null}
          <p className="status-line">{decideStatus}</p>
        </section>
      ) : null}
    </div>
    </div>
  )
}
