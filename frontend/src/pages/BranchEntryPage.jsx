import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { AiActivityPanel } from '../components/AiActivityPanel.jsx'
import ExtractedFieldGrid from '../components/ExtractedFieldGrid.jsx'
import BrandHeader from '../components/BrandHeader.jsx'
import ReportView from '../components/ReportView.jsx'
import QueueEta from '../components/QueueEta.jsx'
import StatusPill, { SourcePill } from '../components/StatusPill.jsx'
import AlertBanner from '../components/ui/AlertBanner.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'
import { getTextFieldsForMode } from '../config/scanForms.js'

const DOC_LABELS = {
  cnic_front: 'CNIC front',
  cnic_back: 'CNIC back',
  payslip: 'Payslip',
  bank_statement: 'Bank statement',
  account_opening_form: 'Account opening form',
}

function humanizeKey(key) {
  return String(key || '').replace(/_/g, ' ')
}

function bannerTypeForMessage(message) {
  const text = String(message || '').toLowerCase()
  if (!text) return 'info'
  if (text.includes('fail') || text.includes('error') || text.includes('required')) return 'error'
  if (text.includes('sent') || text.includes('confirm')) return 'success'
  return 'info'
}

function mapEntryDocumentsForReport(docs) {
  const mapped = {}
  const cnicPages = (docs || []).filter((doc) => doc.document_type === 'cnic')
  if (cnicPages[0]) mapped.cnic_front = cnicPages[0]
  // CNIC back is not used for account opening workflow — only front is mapped.
  for (const doc of docs || []) {
    if (doc.document_type === 'payslip') mapped.payslip = doc
    if (doc.document_type === 'bank_statement') mapped.bank_statement = doc
    if (doc.document_type === 'account_opening_form') mapped.account_opening_form = doc
  }
  return mapped
}

function workflowProgressSteps(progress) {
  const stage = String(progress?.stage || '').toLowerCase()
  const order = ['starting', 'ocr', 'llm', 'validating', 'report', 'complete']
  const index = order.indexOf(stage)
  return order.map((id, stepIndex) => {
    let state = 'todo'
    if (progress?.done || (index >= 0 && stepIndex < index) || id === 'complete' && progress?.done) {
      state = 'done'
    } else if (index === stepIndex) {
      state = 'active'
    }
    if (progress?.done) state = 'done'
    return {
      id,
      label: id.replace(/_/g, ' '),
      state,
    }
  })
}

function VerificationForm({
  entry,
  verificationDocument,
  setVerificationDocument,
  verificationTarget,
  setVerificationTarget,
  verificationNote,
  setVerificationNote,
  verificationStatusMessage,
  sendingVerification,
  confirmingVerification,
  onSubmit,
  onConfirm,
}) {
  return (
    <form className="panel" onSubmit={onSubmit}>
      <h3>Email verification</h3>
      <p className="hint">
        Send a verification request to the company or bank email for a payslip or bank statement.
      </p>
      <div className="form-stack">
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
          Verification email
          <input
            type="email"
            value={verificationTarget}
            onChange={(e) => setVerificationTarget(e.target.value)}
            placeholder="company@example.com"
            required
          />
        </label>
        <label className="field">
          Note
          <input
            type="text"
            value={verificationNote}
            onChange={(e) => setVerificationNote(e.target.value)}
            placeholder="Optional note"
          />
        </label>
      </div>
      <div className="actions">
        <button type="submit" className="btn" disabled={sendingVerification}>
          {sendingVerification ? 'Sending…' : 'Send verification email'}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={confirmingVerification || entry.verification_email_status !== 'sent'}
          onClick={onConfirm}
        >
          {confirmingVerification ? 'Confirming…' : 'Confirm verification received'}
        </button>
      </div>
      {verificationStatusMessage ? (
        <AlertBanner
          type={bannerTypeForMessage(verificationStatusMessage)}
          message={verificationStatusMessage}
          className="alert-banner-compact"
        />
      ) : null}
      {entry.verification_email_status ? (
        <p className="hint">Current email status: {entry.verification_email_status}</p>
      ) : null}
    </form>
  )
}

function DocumentList({ documents, expanded, setExpanded }) {
  return (
    <div className="entry-doc-list">
      {(documents || []).map((doc) => {
        const isOpen = Boolean(expanded[doc.id])
        const fields = doc.fields || {}
        const checks = doc.checkboxes || {}
        return (
          <article key={doc.id} className="panel entry-doc-card">
            <div className="panel-head" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <p className="eyebrow" style={{ marginBottom: '0.15rem' }}>
                  {doc.document_type_label || doc.document_type}
                </p>
                <h3 style={{ margin: 0, fontSize: '1rem' }}>{doc.original_filename}</h3>
              </div>
              <div className="actions" style={{ margin: 0 }}>
                <a className="btn btn-secondary" href={doc.url} target="_blank" rel="noreferrer">
                  Open
                </a>
                <a
                  className="btn btn-secondary"
                  href={`${doc.url}?download=true`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Download
                </a>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setExpanded((prev) => ({ ...prev, [doc.id]: !isOpen }))}
                >
                  {isOpen ? 'Hide fields' : 'Show fields'}
                </button>
              </div>
            </div>

            {doc.is_image ? (
              <a href={doc.url} target="_blank" rel="noreferrer" className="doc-preview-link">
                <img src={doc.url} alt={doc.original_filename} className="doc-preview-image" />
              </a>
            ) : null}

            {isOpen ? (
              <>
                {doc.document_type === 'payslip' ? (
                  <ExtractedFieldGrid
                    fields={getTextFieldsForMode('payslip')}
                    values={fields}
                    readOnly
                    mode="payslip"
                  />
                ) : Object.keys(fields).length ? (
                  <div className="scan-edit-grid" style={{ marginTop: '0.85rem' }}>
                    {Object.entries(fields).map(([key, value]) => (
                      <label key={key} className={`field banking-field${value ? ' is-filled' : ' is-empty'}`}>
                        <span className="banking-field-label">{humanizeKey(key)}</span>
                        <input value={value == null ? '' : String(value)} readOnly placeholder="Not found on document" />
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="hint">No text fields stored for this document.</p>
                )}
                {Object.keys(checks).length > 0 ? (
                  <div className="scan-checkbox-section">
                    <p className="eyebrow" style={{ marginBottom: '0.65rem' }}>Checkboxes</p>
                    <div className="scan-checkbox-grid">
                      {Object.entries(checks).map(([key, value]) => (
                        <label key={key} className="scan-check-item">
                          <input type="checkbox" checked={Boolean(value)} readOnly disabled />
                          <span>{humanizeKey(key)}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ) : null}
                {doc.extracted_text ? (
                  <pre className="scan-ocr-text" style={{ marginTop: '0.85rem' }}>
                    {doc.extracted_text}
                  </pre>
                ) : null}
              </>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}

export default function BranchEntryPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [entry, setEntry] = useState(null)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState({})
  const [activeTab, setActiveTab] = useState('report')
  const [verificationDocument, setVerificationDocument] = useState('payslip')
  const [verificationTarget, setVerificationTarget] = useState('')
  const [verificationNote, setVerificationNote] = useState('')
  const [verificationStatusMessage, setVerificationStatusMessage] = useState('')
  const [sendingVerification, setSendingVerification] = useState(false)
  const [confirmingVerification, setConfirmingVerification] = useState(false)
  const [etaSyncedAt, setEtaSyncedAt] = useState(0)
  const toast = useToast()

  function applyEntry(data) {
    setEntry(data)
    setEtaSyncedAt(Date.now())
  }

  useEffect(() => {
    api('/api/v1/auth/me')
      .then(() => api(`/api/v1/branch/branch-entries/${id}`))
      .then((data) => {
        applyEntry(data)
        setError('')
        const open = {}
        ;(data.documents || []).forEach((d, i) => { open[d.id] = i === 0 })
        setExpanded(open)
        setVerificationTarget(data.verification_email_target || '')
        setVerificationNote(data.verification_email_note || '')
        setVerificationDocument(data.verification_email_document || 'payslip')
        if (data.verification_email_status) {
          setVerificationStatusMessage(`Email status: ${data.verification_email_status}`)
        }
      })
      .catch((err) => {
        if (String(err.message || '').toLowerCase().includes('auth')) {
          navigate('/branch/login', { replace: true })
          return
        }
        setError(err.message || 'Failed to load branch entry')
      })
  }, [id, navigate])

  useEffect(() => {
    if (!entry) return undefined
    if (!['pending', 'analyzing'].includes(entry.status)) return undefined
    const timer = setInterval(() => {
      api(`/api/v1/branch/branch-entries/${id}`)
        .then(applyEntry)
        .catch(() => {})
    }, 4000)
    return () => clearInterval(timer)
  }, [entry?.status, id])

  async function sendVerificationEmail() {
    if (!verificationTarget.trim()) {
      setVerificationStatusMessage('Verification email target is required.')
      return
    }
    setSendingVerification(true)
    setVerificationStatusMessage('Sending verification email…')
    try {
      const result = await api(`/api/v1/branch/branch-entries/${id}/verification-email`, {
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
        action: { label: 'Refresh', onClick: () => { api(`/api/v1/branch/branch-entries/${id}`).then((u) => applyEntry(u)).catch(() => {}) } },
        duration: 8000,
      })
      const updated = await api(`/api/v1/branch/branch-entries/${id}`)
      applyEntry(updated)
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
        `/api/v1/branch/branch-entries/${id}/verification-email/confirm`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ note: verificationNote.trim() || undefined }),
        },
      )
      const message = `Verification confirmed at ${result.verification_email_confirmed_at}`
      setVerificationStatusMessage(message)
      toast.success('Verification confirmed', message, {
        action: { label: 'Refresh', onClick: () => { api(`/api/v1/branch/branch-entries/${id}`).then((u) => applyEntry(u)).catch(() => {}) } },
        duration: 8000,
      })
      const updated = await api(`/api/v1/branch/branch-entries/${id}`)
      applyEntry(updated)
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

  const isWorkflow = Boolean(entry?.workflow_type)
  const report = entry?.workflow_meta?.report || null
  const reportDocuments = useMemo(
    () => mapEntryDocumentsForReport(entry?.documents || []),
    [entry?.documents],
  )
  const docCount = isWorkflow
    ? Object.keys(reportDocuments).length
    : (entry?.document_count ?? entry?.documents?.length ?? 0)
  const overallScore = Number(report?.overall_score ?? entry?.overall_score ?? entry?.workflow_meta?.overall_score ?? '')
  const scoreLabel = Number.isFinite(overallScore) ? `${Math.round(overallScore)}%` : '—'
  const verificationLabel = entry?.verification_email_status || 'Not sent'
  const workflowProgress = entry?.workflow_meta?.progress

  if (!entry && !error) {
    return (
      <div className="mesh-workspace">
        <div className="shell">
          <p className="hint">Loading branch entry…</p>
        </div>
      </div>
    )
  }

  if (isWorkflow) {
    return (
      <div className="mesh-workspace">
        <div className="shell wide">
          <BrandHeader
            variant="bar"
            subtitle="Account opening workflow"
            actionTo="/branch/queue"
            actionLabel="Back to queue"
            rightSlot={<span className="ai-badge">Workflow customer</span>}
          />

          {error ? (
            <AlertBanner type="error" title="Could not load entry" message={error} />
          ) : (
            <>
              <PageHeader
                eyebrow="Account opening · workflow queue"
                title={entry.customer_name || entry.full_name}
                description={`Entry ID ${entry.id} · ${entry.workflow_type?.replace(/_/g, ' ') || 'Workflow'}`}
                actions={
                  <Link to="/branch/scan" className="btn btn-secondary">
                    New scan
                  </Link>
                }
              >
                <div className="page-header-pills">
                  <SourcePill source="branch_entry" />
                  <div className="queue-status-cell">
                    <StatusPill status={entry.status || 'pending'} />
                    <QueueEta eta={entry.queue_eta} syncedAt={etaSyncedAt} compact />
                  </div>
                  {entry.has_report ? <span className="page-header-badge">Report ready</span> : null}
                  <span className="page-header-badge">{docCount} documents</span>
                </div>
              </PageHeader>

              {['pending', 'analyzing'].includes(entry.status) || workflowProgress ? (
                <div className="ai-activity-wrap" style={{ marginBottom: '1.5rem' }}>
                  {entry.queue_eta ? (
                    <p className="queue-eta-banner">
                      <QueueEta eta={entry.queue_eta} syncedAt={etaSyncedAt} />
                    </p>
                  ) : null}
                  <AiActivityPanel
                    title="Cognexa AI Activity"
                    message={workflowProgress?.message || 'OCR, extraction, and cross-document checks are running…'}
                    steps={workflowProgressSteps(workflowProgress)}
                    messages={
                      entry.status === 'completed' || entry.status === 'review_required' || workflowProgress?.done
                        ? [
                            'Document parsing complete.',
                            'LLM extraction complete.',
                            'Cross-document validation complete.',
                            'Cognexa AI report ready.',
                          ]
                        : [workflowProgress?.message].filter(Boolean)
                    }
                    aiWorking={['pending', 'analyzing'].includes(entry.status)}
                    collapsible={!['pending', 'analyzing'].includes(entry.status)}
                    defaultCollapsed={!['pending', 'analyzing'].includes(entry.status)}
                  />
                </div>
              ) : null}

              {entry.status === 'failed' ? (
                <AlertBanner
                  type="error"
                  title="Workflow analysis failed"
                  message={entry.workflow_meta?.error || workflowProgress?.message || 'Analysis could not be completed.'}
                />
              ) : null}

              <div className="dashboard-grid application-review-grid">
                <aside className="sidebar-column">
                  <div className="panel sticky-panel dossier-panel">
                    <div className="dossier-panel-head">
                      <p className="eyebrow">Customer dossier</p>
                      <StatusPill status={entry.status || 'pending'} />
                    </div>
                    <div className="kv-grid compact dossier-kv">
                      <div><span className="kv-label">CNIC</span><p>{entry.cnic_number || '—'}</p></div>
                      <div><span className="kv-label">Mobile</span><p>{entry.mobile_number || '—'}</p></div>
                      <div><span className="kv-label">Company</span><p>{entry.company_name || '—'}</p></div>
                      <div><span className="kv-label">Created</span><p>{entry.created_at ? new Date(entry.created_at).toLocaleString() : '—'}</p></div>
                      <div><span className="kv-label">Created by</span><p>{entry.created_by || '—'}</p></div>
                      <div><span className="kv-label">Verification</span><p>{verificationLabel}</p></div>
                    </div>
                    <hr className="divider" />
                    <div className="actions vertical">
                      <Link className="btn btn-secondary btn-full" to="/branch/queue">
                        Back to queue
                      </Link>
                    </div>
                  </div>
                </aside>

                <main className="main-column application-main">
                  <div className="overview-grid application-stats">
                    <div className="overview-card">
                      <span className="overview-label">Cognexa AI score</span>
                      <p className="overview-value">{entry.has_report ? scoreLabel : 'Pending'}</p>
                    </div>
                    <div className="overview-card">
                      <span className="overview-label">Documents</span>
                      <p className="overview-value">{docCount}</p>
                    </div>
                    <div className="overview-card">
                      <span className="overview-label">Verification</span>
                      <p className="overview-value overview-value-sm">{verificationLabel}</p>
                    </div>
                    <div className="overview-card">
                      <span className="overview-label">Workflow</span>
                      <p className="overview-value overview-value-sm">{entry.workflow_type?.replace(/_/g, ' ') || 'Account opening'}</p>
                    </div>
                  </div>

                  <nav className="app-tab-bar" role="tablist" aria-label="Workflow entry views">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeTab === 'report'}
                      className={`app-tab${activeTab === 'report' ? ' active' : ''}`}
                      onClick={() => setActiveTab('report')}
                    >
                      Cognexa AI Report {entry.has_report ? '✓' : ''}
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeTab === 'docs'}
                      className={`app-tab${activeTab === 'docs' ? ' active' : ''}`}
                      onClick={() => setActiveTab('docs')}
                    >
                      Documents ({entry.documents?.length || 0})
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeTab === 'verification'}
                      className={`app-tab${activeTab === 'verification' ? ' active' : ''}`}
                      onClick={() => setActiveTab('verification')}
                    >
                      Email Verification
                    </button>
                  </nav>

                  <div className="tab-content">
                    {activeTab === 'report' && (
                      <div className="tab-pane">
                        {report ? (
                          <div className="panel report-panel">
                            <ReportView report={report} documents={reportDocuments} />
                          </div>
                        ) : (
                          <div className="panel empty-pane">
                            <h3>No Cognexa AI report yet</h3>
                            <p className="hint">
                              {['pending', 'analyzing'].includes(entry.status)
                                ? 'Analysis is running in the queue. This page will refresh automatically.'
                                : 'Report was not generated for this entry.'}
                            </p>
                          </div>
                        )}
                      </div>
                    )}

                    {activeTab === 'docs' && (
                      <div className="tab-pane">
                        <div className="panel">
                          <h3>Uploaded documents</h3>
                          <div className="doc-gallery">
                            {Object.entries(reportDocuments).map(([key, doc]) => {
                              const isImage = doc.is_image || /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(doc.filename || doc.path || '')
                              const isPdf = doc.is_pdf || /\.pdf$/i.test(doc.filename || doc.path || '')
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
                                      <img src={doc.url} alt={DOC_LABELS[key] || key} className="doc-preview-image" />
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
                          <DocumentList documents={entry.documents} expanded={expanded} setExpanded={setExpanded} />
                        </div>
                      </div>
                    )}

                    {activeTab === 'verification' && (
                      <div className="tab-pane">
                        <VerificationForm
                          entry={entry}
                          verificationDocument={verificationDocument}
                          setVerificationDocument={setVerificationDocument}
                          verificationTarget={verificationTarget}
                          setVerificationTarget={setVerificationTarget}
                          verificationNote={verificationNote}
                          setVerificationNote={setVerificationNote}
                          verificationStatusMessage={verificationStatusMessage}
                          sendingVerification={sendingVerification}
                          confirmingVerification={confirmingVerification}
                          onSubmit={handleVerificationSubmit}
                          onConfirm={confirmVerificationEmail}
                        />
                      </div>
                    )}
                  </div>
                </main>
              </div>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="mesh-workspace">
      <div className="shell wide">
        <BrandHeader
          subtitle="Branch Entry"
          actionTo="/branch/queue"
          actionLabel="Back to queue"
          variant="bar"
          rightSlot={<span className="ai-badge">Saved scan</span>}
        />

        {error ? (
          <AlertBanner type="error" title="Could not load entry" message={error} />
        ) : (
          <>
            <PageHeader
              eyebrow="Branch entry"
              title={entry.customer_name || entry.full_name}
              description={`Entry ID ${entry.id} · Created ${entry.created_at ? new Date(entry.created_at).toLocaleString() : '—'}`}
              actions={
                <Link to="/branch/scan" className="btn btn-secondary">
                  New scan
                </Link>
              }
            >
              <div className="page-header-pills">
                <SourcePill source="branch_entry" />
                <StatusPill status={entry.status || 'saved'} />
                <span className="page-header-badge">
                  {entry.document_count ?? entry.documents?.length ?? 0} documents
                </span>
              </div>
            </PageHeader>

            <section className="panel case-review-panel">
              <div className="kv-grid" style={{ marginTop: '0.25rem' }}>
                <div>
                  <span className="kv-label">Created</span>
                  <p>{entry.created_at ? new Date(entry.created_at).toLocaleString() : '—'}</p>
                </div>
                <div>
                  <span className="kv-label">Created by</span>
                  <p>{entry.created_by || '—'}</p>
                </div>
                <div>
                  <span className="kv-label">Documents</span>
                  <p>{entry.document_count ?? entry.documents?.length ?? 0}</p>
                </div>
                <div>
                  <span className="kv-label">CNIC</span>
                  <p>{entry.cnic_number || '—'}</p>
                </div>
                <div>
                  <span className="kv-label">Mobile</span>
                  <p>{entry.mobile_number || '—'}</p>
                </div>
              </div>

              <div style={{ marginTop: '1rem' }}>
                <VerificationForm
                  entry={entry}
                  verificationDocument={verificationDocument}
                  setVerificationDocument={setVerificationDocument}
                  verificationTarget={verificationTarget}
                  setVerificationTarget={setVerificationTarget}
                  verificationNote={verificationNote}
                  setVerificationNote={setVerificationNote}
                  verificationStatusMessage={verificationStatusMessage}
                  sendingVerification={sendingVerification}
                  confirmingVerification={confirmingVerification}
                  onSubmit={handleVerificationSubmit}
                  onConfirm={confirmVerificationEmail}
                />
              </div>

              <h3 style={{ marginTop: '1.4rem', marginBottom: '0.65rem' }}>Documents</h3>
              <DocumentList documents={entry.documents} expanded={expanded} setExpanded={setExpanded} />

              <div className="actions" style={{ marginTop: '1.1rem' }}>
                <Link className="btn btn-secondary" to="/branch/queue">Back to queue</Link>
                <Link className="btn btn-secondary" to="/branch/scan">Scan another</Link>
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
