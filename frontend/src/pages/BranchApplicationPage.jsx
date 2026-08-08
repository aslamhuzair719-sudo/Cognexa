import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, downloadUrl } from '../api'
import { AiActivityPanel } from '../components/AiActivityPanel.jsx'
import BrandHeader from '../components/BrandHeader.jsx'
import ReportView from '../components/ReportView.jsx'
import StatusPill from '../components/StatusPill.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'

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
  const [showAllDetails, setShowAllDetails] = useState(false)
  const [verificationDocument, setVerificationDocument] = useState('payslip')
  const [verificationTarget, setVerificationTarget] = useState('')
  const [verificationNote, setVerificationNote] = useState('')
  const [verificationStatusMessage, setVerificationStatusMessage] = useState('')
  const [sendingVerification, setSendingVerification] = useState(false)
  const [confirmingVerification, setConfirmingVerification] = useState(false)
  const [activeTab, setActiveTab] = useState('report') // 'report' | 'docs' | 'verification'
  const toast = useToast()

  async function load() {
    const app = await api(`/api/v1/branch/applications/${id}`)
    setDetail(app)
    setVerificationTarget(app.verification_email_target || '')
    setVerificationNote(app.verification_email_note || '')
    setVerificationDocument(
      app.verification_email_document || (app.payslip_path ? 'payslip' : 'bank_statement')
    )
    if (app.verification_email_status) {
      setVerificationStatusMessage(`Email status: ${app.verification_email_status}`)
    }
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
    setActionStatus('Queuing Cognexa AI analysis…')
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

  async function sendVerificationEmail() {
    if (!verificationTarget.trim()) {
      setVerificationStatusMessage('Verification email target is required.')
      return
    }
    setSendingVerification(true)
    setVerificationStatusMessage('Sending verification email…')
    try {
      const result = await api(`/api/v1/branch/applications/${id}/verification-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_type: verificationDocument,
          target_email: verificationTarget.trim(),
          note: verificationNote.trim() || undefined,
        }),
      })
      const message = `Email sent to ${result.verification_email_target}. Status: ${result.verification_email_status}`
      setVerificationStatusMessage(message)
      toast.success('Verification email sent', message, {
        action: { label: 'Refresh', onClick: () => { load().catch(() => {}) } },
        duration: 8000,
      })
      await load()
    } catch (err) {
      const msg = err.message || 'Failed to send verification email.'
      setVerificationStatusMessage(msg)
      toast.error('Verification email failed', msg)
    } finally {
      setSendingVerification(false)
    }
  }

  async function confirmVerificationEmail() {
    setConfirmingVerification(true)
    setVerificationStatusMessage('Confirming verification email…')
    try {
      const result = await api(
        `/api/v1/branch/applications/${id}/verification-email/confirm`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ note: verificationNote.trim() || undefined }),
        },
      )
      const message = `Verification confirmed at ${result.verification_email_confirmed_at}`
      setVerificationStatusMessage(message)
      toast.success('Verification confirmed', message, {
        action: { label: 'Refresh', onClick: () => { load().catch(() => {}) } },
        duration: 8000,
      })
      await load()
    } catch (err) {
      const msg = err.message || 'Failed to confirm verification.'
      setVerificationStatusMessage(msg)
      toast.error('Verification confirm failed', msg)
    } finally {
      setConfirmingVerification(false)
    }
  }

  async function handleVerificationSubmit(event) {
    event.preventDefault()
    await sendVerificationEmail()
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
  const docCount = Object.keys(detail.documents || {}).length
  const overallScore = Number(report?.overall_score ?? detail.overall_score ?? '')
  const scoreLabel = Number.isFinite(overallScore) ? `${Math.round(overallScore)}%` : '—'
  const verificationLabel = detail.verification_email_status || 'Not sent'

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

        {/* Dynamic AI Status Banner */}
        {['pending', 'analyzing'].includes(detail.status) || detail.ai_progress ? (
          <div className="ai-activity-wrap" style={{ marginBottom: '1.5rem' }}>
            <AiActivityPanel
              title="Cognexa AI Activity"
              message={detail.ai_progress?.message}
              steps={detail.ai_progress?.steps || []}
              messages={
                detail.status === 'completed' || detail.ai_progress?.done
                  ? (detail.ai_progress?.messages?.length
                      ? detail.ai_progress.messages
                      : [
                          'Document parsing complete.',
                          'LLM summary complete.',
                          'Cognexa AI analysis complete.',
                        ])
                  : (detail.ai_progress?.messages || [])
              }
              aiWorking={Boolean(detail.ai_progress?.ai_working)}
            />
          </div>
        ) : null}

        {/* 2-Column Dashboard Layout */}
        <div className="dashboard-grid">
          {/* LEFT SIDEBAR: Applicant Metadata & Decision Actions */}
          <aside className="sidebar-column">
            <div className="panel sticky-panel">
              <div className="detail-header">
                <div>
                  <p className="eyebrow">Application dossier</p>
                  <h2>{detail.full_name}</h2>
                  <p className="meta">ID {detail.id}</p>
                </div>
                <StatusPill status={detail.status} />
              </div>

              <hr className="divider" />

              <div className="kv-grid compact">
                <div><span className="kv-label">Email</span><p>{detail.email}</p></div>
                <div><span className="kv-label">Phone</span><p>{detail.mobile_number}</p></div>
                <div><span className="kv-label">Company</span><p>{detail.company_name || '—'}</p></div>
                <div><span className="kv-label">Designation</span><p>{detail.designation || '—'}</p></div>
                <div><span className="kv-label">Monthly salary</span><p>{detail.monthly_income || '—'}</p></div>
                <div><span className="kv-label">Verification</span><p>{detail.verification_email_status || 'Not sent'}</p></div>
              </div>

              <button
                type="button"
                className="link-btn"
                style={{ marginTop: '0.75rem' }}
                onClick={() => setShowAllDetails((open) => !open)}
              >
                {showAllDetails ? 'Hide details ▲' : 'Show full profile ▼'}
              </button>

              {showAllDetails ? (
                <div className="kv-grid full-details" style={{ marginTop: '0.75rem' }}>
                  <div><span className="kv-label">Age</span><p>{detail.age || '—'}</p></div>
                  <div><span className="kv-label">Gender</span><p>{detail.gender || '—'}</p></div>
                  <div><span className="kv-label">CNIC name</span><p>{detail.cnic_full_name || detail.full_name}</p></div>
                  <div><span className="kv-label">Father name</span><p>{detail.father_name || '—'}</p></div>
                  <div><span className="kv-label">CNIC</span><p>{detail.cnic_number || '—'}</p></div>
                  <div><span className="kv-label">DOB</span><p>{detail.date_of_birth || '—'}</p></div>
                  <div><span className="kv-label">Issue date</span><p>{detail.cnic_issue_date || '—'}</p></div>
                  <div><span className="kv-label">Expiry date</span><p>{detail.cnic_expiry_date || '—'}</p></div>
                  <div><span className="kv-label">Country</span><p>{detail.country_to_stay || '—'}</p></div>
                  <div><span className="kv-label">Emp ID</span><p>{detail.employee_id || '—'}</p></div>
                </div>
              ) : null}

              <hr className="divider" />

              {/* Action Toolbar */}
              <div className="actions vertical">
                <button
                  type="button"
                  className="btn btn-full"
                  disabled={!canRequeue || queueing}
                  onClick={requeueAnalysis}
                >
                  {queueing ? 'Queuing…' : detail.has_report ? 'Re-queue Cognexa AI analysis' : 'Queue Cognexa AI analysis'}
                </button>
                {detail.has_report ? (
                  <button
                    type="button"
                    className="btn btn-secondary btn-full"
                    onClick={() => downloadUrl(`/api/v1/branch/applications/${detail.id}/report/pdf`)}
                  >
                    Download PDF report
                  </button>
                ) : null}
                {actionStatus ? <p className="status-line">{actionStatus}</p> : null}
              </div>

              {/* Decision Section */}
              {canDecide ? (
                <div className="decision-box">
                  <h3 className="section-title">Decision</h3>
                  {detail.status === 'accepted' || detail.status === 'rejected' ? (
                    <p className="hint">
                      Status: <strong>{detail.status}</strong>
                      {detail.decision_note ? ` — ${detail.decision_note}` : ''}
                    </p>
                  ) : null}
                  <div className="actions">
                    <button type="button" className="btn btn-pass" onClick={() => decide('accept')}>
                      Accept
                    </button>
                    <button type="button" className="btn btn-fail" onClick={() => setRejectOpen(true)}>
                      Reject
                    </button>
                  </div>
                  {rejectOpen ? (
                    <div style={{ marginTop: '0.75rem' }}>
                      <label className="field full">
                        Rejection reason
                        <textarea
                          rows={2}
                          value={rejectNote}
                          onChange={(e) => setRejectNote(e.target.value)}
                          placeholder="Reason required..."
                        />
                      </label>
                      <div className="actions" style={{ marginTop: '0.5rem' }}>
                        <button type="button" className="btn btn-fail" onClick={() => decide('reject')}>
                          Confirm
                        </button>
                        <button type="button" className="btn btn-secondary" onClick={() => setRejectOpen(false)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {decideStatus ? <p className="status-line">{decideStatus}</p> : null}
                </div>
              ) : null}
            </div>
          </aside>

          {/* RIGHT MAIN WORKSPACE: Tabbed Views */}
          <main className="main-column">
            <div className="top-summary">
              <div className="overview-grid">
                <div className="overview-card">
                  <span className="overview-label">Cognexa AI score</span>
                  <p className="overview-value">{report || detail.overall_score ? scoreLabel : 'Pending'}</p>
                </div>
                <div className="overview-card">
                  <span className="overview-label">Documents</span>
                  <p className="overview-value">{docCount}</p>
                </div>
                <div className="overview-card">
                  <span className="overview-label">Verification</span>
                  <p className="overview-value">{verificationLabel}</p>
                </div>
                <div className="overview-card">
                  <span className="overview-label">Application</span>
                  <p className="overview-value">{detail.application_type || detail.document_type || 'Standard'}</p>
                </div>
              </div>

              <div className="panel panel-accent" style={{ padding: '1.25rem 1.4rem' }}>
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">Insight overview</p>
                    <h3 style={{ margin: '0.35rem 0 0' }}>
                      Review the latest Cognexa AI assessment, documents and verification workflow.
                    </h3>
                  </div>
                  <StatusPill status={detail.status} />
                </div>
                <p className="hint" style={{ marginTop: '0.85rem' }}>
                  Use the tabs below to inspect the case report, review uploaded documents, and manage verification emails.
                </p>
              </div>
            </div>

            <nav className="tab-bar">
              <button
                type="button"
                className={`tab-btn ${activeTab === 'report' ? 'active' : ''}`}
                onClick={() => setActiveTab('report')}
              >
                Cognexa AI Report {detail.has_report ? '✓' : ''}
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'docs' ? 'active' : ''}`}
                onClick={() => setActiveTab('docs')}
              >
                Documents ({docCount})
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'verification' ? 'active' : ''}`}
                onClick={() => setActiveTab('verification')}
              >
                Email Verification
              </button>
            </nav>

            <div className="tab-content">
              {activeTab === 'report' && (
                <div className="tab-pane">
                  {report ? (
                    <ReportView report={report} documents={detail.documents} />
                  ) : (
                    <div className="panel empty-pane">
                      <h3>No Cognexa AI report generated yet</h3>
                      <p className="hint">
                        Queue an analysis using the sidebar controls to generate an assessment.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'docs' && (
                <div className="tab-pane">
                  <div className="panel">
                    <h3>Uploaded Documents</h3>
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
                  </div>
                </div>
              )}

              {activeTab === 'verification' && (
                <div className="tab-pane">
                  <form className="panel" onSubmit={handleVerificationSubmit}>
                    <h3>Email Verification Workflow</h3>
                    <p className="hint">
                      Send a verification request directly to the employer or financial institution.
                    </p>
                    <div className="form-stack" style={{ marginTop: '1rem' }}>
                      <label className="field">
                        Document type
                        <select
                          value={verificationDocument}
                          onChange={(e) => setVerificationDocument(e.target.value)}
                        >
                          <option value="payslip">Payslip</option>
                          <option value="bank_statement">Bank Statement</option>
                        </select>
                      </label>
                      <label className="field">
                        Verification target email
                        <input
                          type="email"
                          value={verificationTarget}
                          onChange={(e) => setVerificationTarget(e.target.value)}
                          placeholder="company@example.com"
                          required
                        />
                      </label>
                      <label className="field">
                        Internal note / instructions
                        <input
                          type="text"
                          value={verificationNote}
                          onChange={(e) => setVerificationNote(e.target.value)}
                          placeholder="Optional note..."
                        />
                      </label>
                      <div className="actions">
                        <button type="submit" className="btn" disabled={sendingVerification}>
                          {sendingVerification ? 'Sending…' : 'Send verification email'}
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          disabled={confirmingVerification || detail.verification_email_status !== 'sent'}
                          onClick={confirmVerificationEmail}
                        >
                          {confirmingVerification ? 'Confirming…' : 'Confirm verification received'}
                        </button>
                      </div>
                      {verificationStatusMessage ? (
                        <p className="status-line">{verificationStatusMessage}</p>
                      ) : null}
                    </div>
                  </form>
                </div>
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}