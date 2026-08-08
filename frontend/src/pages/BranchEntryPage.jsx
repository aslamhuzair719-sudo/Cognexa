import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import BrandHeader from '../components/BrandHeader.jsx'
import StatusPill, { SourcePill } from '../components/StatusPill.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'

function humanizeKey(key) {
  return String(key || '').replace(/_/g, ' ')
}

export default function BranchEntryPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [entry, setEntry] = useState(null)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState({})
  const [verificationDocument, setVerificationDocument] = useState('payslip')
  const [verificationTarget, setVerificationTarget] = useState('')
  const [verificationNote, setVerificationNote] = useState('')
  const [verificationStatusMessage, setVerificationStatusMessage] = useState('')
  const [sendingVerification, setSendingVerification] = useState(false)
  const [confirmingVerification, setConfirmingVerification] = useState(false)
  const toast = useToast()

  useEffect(() => {
    api('/api/v1/auth/me')
      .then(() => api(`/api/v1/branch/branch-entries/${id}`))
      .then((data) => {
        setEntry(data)
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
        action: { label: 'Refresh', onClick: () => { api(`/api/v1/branch/branch-entries/${id}`).then((u) => setEntry(u)).catch(() => {}) } },
        duration: 8000,
      })
      const updated = await api(`/api/v1/branch/branch-entries/${id}`)
      setEntry(updated)
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
        action: { label: 'Refresh', onClick: () => { api(`/api/v1/branch/branch-entries/${id}`).then((u) => setEntry(u)).catch(() => {}) } },
        duration: 8000,
      })
      const updated = await api(`/api/v1/branch/branch-entries/${id}`)
      setEntry(updated)
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

  if (!entry && !error) {
    return (
      <div className="mesh-workspace">
        <div className="shell">
          <p className="hint">Loading branch entry…</p>
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
          <p className="status-line error">{error}</p>
        ) : (
          <section className="panel">
            <div className="detail-header">
              <div>
                <p className="eyebrow">Branch Entry</p>
                <h2>{entry.customer_name || entry.full_name}</h2>
                <p className="meta">ID {entry.id}</p>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <SourcePill source="branch_entry" />
                <StatusPill status={entry.status || 'saved'} />
              </div>
            </div>

            <div className="kv-grid" style={{ marginTop: '1rem' }}>
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

            <form className="panel" style={{ marginTop: '1rem' }} onSubmit={handleVerificationSubmit}>
              <h3>Email verification</h3>
              <p className="hint">
                Use this to send a verification request to the company or bank email for a payslip or bank statement.
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
                  onClick={confirmVerificationEmail}
                >
                  {confirmingVerification ? 'Confirming…' : 'Confirm verification received'}
                </button>
              </div>
              <p className="status-line">{verificationStatusMessage}</p>
              {entry.verification_email_status ? (
                <p className="hint">Current email status: {entry.verification_email_status}</p>
              ) : null}
            </form>

            <h3 style={{ marginTop: '1.4rem', marginBottom: '0.65rem' }}>Documents</h3>
            <div className="entry-doc-list">
              {(entry.documents || []).map((doc) => {
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

                    {isOpen && (
                      <>
                        <div className="scan-edit-grid" style={{ marginTop: '0.85rem' }}>
                          {Object.keys(fields).length ? Object.entries(fields).map(([key, value]) => (
                            <label key={key} className="field">
                              {humanizeKey(key)}
                              <input value={value == null ? '' : String(value)} readOnly />
                            </label>
                          )) : (
                            <p className="hint">No text fields stored for this document.</p>
                          )}
                        </div>
                        {Object.keys(checks).length > 0 && (
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
                        )}
                        {doc.extracted_text ? (
                          <pre className="scan-ocr-text" style={{ marginTop: '0.85rem' }}>
                            {doc.extracted_text}
                          </pre>
                        ) : null}
                      </>
                    )}
                  </article>
                )
              })}
            </div>

            <div className="actions" style={{ marginTop: '1.1rem' }}>
              <Link className="btn btn-secondary" to="/branch/queue">Back to queue</Link>
              <Link className="btn btn-secondary" to="/branch/scan">Scan another</Link>
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
