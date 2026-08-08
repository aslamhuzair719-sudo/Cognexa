import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import Button from '../components/ui/Button.jsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'

function formatWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 16)
  return d.toLocaleString()
}

function SignatureDropzone({ file, preview, onPick, onClear, inputRef, dragging, setDragging }) {
  function onInputChange(e) {
    onPick(e.target.files?.[0])
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    onPick(e.dataTransfer.files?.[0])
  }

  return (
    <div
      className={`scan-dropzone${dragging ? ' dragging' : ''}${file ? ' has-file' : ''}`}
      role="button"
      tabIndex={0}
      onClick={() => !file && inputRef.current?.click()}
      onKeyDown={(e) => {
        if (!file && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={onInputChange}
      />
      {file && preview ? (
        <div className="scan-file-preview">
          <img src={preview} alt="Signature preview" className="scan-preview-img" />
          <div className="scan-file-name">
            <span className="scan-fname-text">{file.name}</span>
            <span className="scan-file-size">{(file.size / 1024).toFixed(1)} KB</span>
            <button
              type="button"
              className="scan-remove-btn"
              onClick={(e) => {
                e.stopPropagation()
                onClear()
              }}
            >
              Remove
            </button>
          </div>
        </div>
      ) : (
        <div className="scan-dropzone-inner">
          <svg className="scan-drop-icon" width="36" height="36" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <p className="scan-drop-title">Drop signature image here</p>
          <p className="scan-drop-sub">or click to browse</p>
          <p className="scan-drop-formats">PNG · JPG · WEBP</p>
        </div>
      )}
    </div>
  )
}

function MatchMeter({ percentage, verdict }) {
  const tone =
    verdict === 'match' ? 'match' : verdict === 'uncertain' ? 'uncertain' : 'mismatch'
  return (
    <div className={`sig-match-meter tone-${tone}`}>
      <div className="sig-match-ring" style={{ '--pct': `${percentage}%` }}>
        <strong>{percentage}%</strong>
        <span>match</span>
      </div>
    </div>
  )
}

function formatScoreLabel(key) {
  const normalized = String(key || '').toLowerCase()
  if (normalized === 'visual_similarity') return 'Visual Similarity'
  if (normalized === 'similarity' || normalized === 'gemini_similarity') return 'Similarity'
  const label = String(key || '').replace(/_/g, ' ')
  return label ? label.charAt(0).toUpperCase() + label.slice(1) : label
}

const REPORT_SCORE_KEYS = ['visual_similarity', 'similarity']

export default function BranchSignaturesPage() {
  const [view, setView] = useState('scan')

  const [accountNumber, setAccountNumber] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [compareResult, setCompareResult] = useState(null)
  const compareInputRef = useRef(null)

  const [registerOpen, setRegisterOpen] = useState(false)
  const [regAccount, setRegAccount] = useState('')
  const [regName, setRegName] = useState('')
  const [regFile, setRegFile] = useState(null)
  const [regPreview, setRegPreview] = useState(null)
  const [regDragging, setRegDragging] = useState(false)
  const [regLoading, setRegLoading] = useState(false)
  const [regError, setRegError] = useState('')
  const [regSuccess, setRegSuccess] = useState('')
  const registerInputRef = useRef(null)

  const [records, setRecords] = useState([])
  const [recordsLoading, setRecordsLoading] = useState(false)
  const [recordsError, setRecordsError] = useState('')
  const [viewRecord, setViewRecord] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(null)
  const toast = useToast()

  function pickCompareFile(f) {
    if (!f) return
    if (!f.type.startsWith('image/')) {
      setError('Please upload an image file.')
      return
    }
    setFile(f)
    setError('')
    setCompareResult(null)
    setPreview(URL.createObjectURL(f))
  }

  function clearCompareFile() {
    setFile(null)
    setPreview(null)
    setCompareResult(null)
    if (compareInputRef.current) compareInputRef.current.value = ''
  }

  function resetCompareForm() {
    setAccountNumber('')
    clearCompareFile()
    setError('')
    setCompareResult(null)
  }

  function pickRegisterFile(f) {
    if (!f) return
    if (!f.type.startsWith('image/')) {
      setRegError('Please upload an image file.')
      return
    }
    setRegFile(f)
    setRegError('')
    setRegSuccess('')
    setRegPreview(URL.createObjectURL(f))
  }

  function clearRegisterForm() {
    setRegAccount('')
    setRegName('')
    setRegFile(null)
    setRegPreview(null)
    setRegError('')
    setRegSuccess('')
    if (registerInputRef.current) registerInputRef.current.value = ''
  }

  function closeRegisterModal() {
    if (regLoading) return
    setRegisterOpen(false)
    clearRegisterForm()
  }

  async function refreshRecords() {
    setRecordsLoading(true)
    setRecordsError('')
    try {
      const data = await api('/api/v1/branch/signatures')
      setRecords(data.items || [])
    } catch (err) {
      setRecordsError(err.message || 'Could not load records.')
    } finally {
      setRecordsLoading(false)
    }
  }

  useEffect(() => {
    if (view === 'database') refreshRecords()
  }, [view])

  async function onCompare(e) {
    e.preventDefault()
    if (!accountNumber.trim()) {
      setError('Account number is required.')
      return
    }
    if (!file) {
      setError('Please upload a signature image to compare.')
      return
    }
    setLoading(true)
    setError('')
    setCompareResult(null)
    try {
      const body = new FormData()
      body.append('account_number', accountNumber.trim())
      body.append('file', file)
      const data = await api('/api/v1/branch/signatures/compare', {
        method: 'POST',
        body,
      })
      setCompareResult(data)
    } catch (err) {
      setError(err.message || 'Comparison failed.')
    } finally {
      setLoading(false)
    }
  }

  async function onRegister(e) {
    e.preventDefault()
    if (!regAccount.trim()) {
      setRegError('Account number is required.')
      return
    }
    if (!regFile) {
      setRegError('Please upload a signature image.')
      return
    }
    setRegLoading(true)
    setRegError('')
    setRegSuccess('')
    try {
      const body = new FormData()
      body.append('account_number', regAccount.trim())
      body.append('customer_name', regName.trim())
      body.append('file', regFile)
      const data = await api('/api/v1/branch/signatures/register', {
        method: 'POST',
        body,
      })
      setRegSuccess(
        data.updated
          ? `Signature updated for account ${data.record.account_number}.`
          : `Signature registered for account ${data.record.account_number}.`,
      )
      toast.success(
        data.updated ? 'Signature updated' : 'Signature registered',
        `Account ${data.record.account_number} is ready for comparison.`,
      )
      if (view === 'database') refreshRecords()
      setTimeout(() => {
        closeRegisterModal()
      }, 1200)
    } catch (err) {
      setRegError(err.message || 'Registration failed.')
    } finally {
      setRegLoading(false)
    }
  }

  function requestDeleteRecord(record) {
    setConfirmDelete(record)
  }

  async function confirmDeleteRecord() {
    if (!confirmDelete) return
    const record = confirmDelete
    setDeletingId(record.id)
    setRecordsError('')
    try {
      await api(`/api/v1/branch/signatures/${record.id}`, { method: 'DELETE' })
      setRecords((prev) => prev.filter((row) => row.id !== record.id))
      if (viewRecord?.id === record.id) setViewRecord(null)
      toast.success('Signature deleted', `Account ${record.account_number} removed from database.`)
      setConfirmDelete(null)
    } catch (err) {
      toast.error('Delete failed', err.message || 'Could not delete signature.')
      setRecordsError(err.message || 'Delete failed.')
    } finally {
      setDeletingId(null)
    }
  }

  async function onDeleteRecord(record) {
    requestDeleteRecord(record)
  }

  return (
    <div className="scan-page sig-page">
      <section className="hero hero-branch">
        <span className="ai-badge">Cognexa Signature Scan</span>
        <h1>Signature verification</h1>
        <p>
          Compare signatures against registered specimens, or manage the signature
          database for your branch.
        </p>
      </section>

      <div className="sig-view-toggle" role="tablist" aria-label="Signature scan views">
        <button
          type="button"
          role="tab"
          aria-selected={view === 'scan'}
          className={`sig-view-tab${view === 'scan' ? ' active' : ''}`}
          onClick={() => setView('scan')}
        >
          Scan
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === 'database'}
          className={`sig-view-tab${view === 'database' ? ' active' : ''}`}
          onClick={() => setView('database')}
        >
          Signature Database
        </button>
      </div>

      {view === 'scan' ? (
        <div className="scan-layout">
          <aside className="scan-upload-panel panel">
            <form onSubmit={onCompare}>
              <label className="field">
                Account number
                <input
                  value={accountNumber}
                  onChange={(e) => setAccountNumber(e.target.value)}
                  placeholder="e.g. 0123456789"
                  autoComplete="off"
                  required
                />
              </label>

              <p className="field-label">Signature image</p>
              <SignatureDropzone
                file={file}
                preview={preview}
                onPick={pickCompareFile}
                onClear={clearCompareFile}
                inputRef={compareInputRef}
                dragging={dragging}
                setDragging={setDragging}
              />

              {error ? <p className="status-line error">{error}</p> : null}

              <div className="sig-actions">
                <button type="submit" className="btn" disabled={loading}>
                  {loading ? 'Comparing…' : 'Compare signature'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={resetCompareForm}
                  disabled={loading}
                >
                  Clear
                </button>
              </div>
            </form>
          </aside>

          <section className="scan-results">
            {compareResult ? (
              <article className="scan-result-card panel panel-accent sig-report">
                <header className="sig-report-header">
                  <div className="sig-report-title">
                    <p className="sig-report-eyebrow">Signature verification report</p>
                    <h2>Comparison result</h2>
                    <span className={`sig-verdict sig-verdict-${compareResult.verdict}`}>
                      {compareResult.verdict_label}
                    </span>
                  </div>
                  <MatchMeter
                    percentage={compareResult.match_percentage}
                    verdict={compareResult.verdict}
                  />
                </header>

                <div className="sig-report-metrics">
                  <div className="sig-report-metric">
                    <span className="sig-report-metric-label">Account</span>
                    <span className="sig-report-metric-value">{compareResult.account_number}</span>
                  </div>
                  <div className="sig-report-metric">
                    <span className="sig-report-metric-label">Customer</span>
                    <span className="sig-report-metric-value">
                      {compareResult.customer_name || '—'}
                    </span>
                  </div>
                  <div className="sig-report-metric">
                    <span className="sig-report-metric-label">Threshold</span>
                    <span className="sig-report-metric-value">{compareResult.threshold}%</span>
                  </div>
                  <div className="sig-report-metric">
                    <span className="sig-report-metric-label">Probe file</span>
                    <span className="sig-report-metric-value sig-report-metric-file">
                      {compareResult.probe_filename}
                    </span>
                  </div>
                </div>

                {compareResult.scores ? (
                  <section className="sig-report-section">
                    <h3>Score breakdown</h3>
                    <div className="sig-score-bars">
                      {REPORT_SCORE_KEYS.filter((key) => compareResult.scores[key] != null).map((key) => {
                        const value = compareResult.scores[key]
                        return (
                          <div key={key} className="sig-score-row">
                            <span>{formatScoreLabel(key)}</span>
                            <div className="sig-score-track">
                              <i style={{ width: `${value}%` }} />
                            </div>
                            <strong>{value}%</strong>
                          </div>
                        )
                      })}
                    </div>
                  </section>
                ) : null}

                {compareResult.registered?.image_url && preview ? (
                  <section className="sig-report-section">
                    <h3>Signature comparison</h3>
                    <div className="sig-side-by-side">
                      <figure>
                        <img src={compareResult.registered.image_url} alt="Registered signature" />
                        <figcaption>Registered on file</figcaption>
                      </figure>
                      <figure>
                        <img src={preview} alt="Uploaded signature" />
                        <figcaption>Uploaded for compare</figcaption>
                      </figure>
                    </div>
                  </section>
                ) : null}
              </article>
            ) : (
              <article className="scan-empty-state panel">
                <div className="scan-empty-icon" aria-hidden>
                  ✎
                </div>
                <h2>Compare a signature</h2>
                <p>
                  Enter the account number and upload a signature image. The system looks up
                  the registered specimen and returns a match percentage.
                </p>
              </article>
            )}
          </section>
        </div>
      ) : (
        <section className="panel sig-database-panel">
          <div className="panel-head">
            <div>
              <h2>Signature database</h2>
              <p className="hint">All registered specimen signatures for this branch.</p>
            </div>
            <div className="sig-modal-actions">
              <button type="button" className="btn btn-secondary" onClick={refreshRecords}>
                Refresh
              </button>
              <button type="button" className="btn" onClick={() => setRegisterOpen(true)}>
                Register
              </button>
            </div>
          </div>

          {recordsLoading ? (
            <p className="hint">Loading signatures…</p>
          ) : recordsError ? (
            <p className="status-line error">{recordsError}</p>
          ) : records.length === 0 ? (
            <EmptyState
              icon="✎"
              title="No signatures yet"
              description="Register a specimen signature to start building the database."
              actionLabel="Register signature"
              onAction={() => setRegisterOpen(true)}
            />
          ) : (
            <div className="sig-records-grid">
              {records.map((row) => (
                <article key={row.id} className="sig-record-card">
                  <img src={row.image_url} alt="" className="sig-record-img" />
                  <div className="sig-record-body">
                    <strong>{row.account_number}</strong>
                    <span>{row.customer_name || 'No name on file'}</span>
                    <span className="hint">{formatWhen(row.updated_at || row.created_at)}</span>
                    <div className="sig-card-actions">
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setViewRecord(row)}
                      >
                        View
                      </button>
                      <button
                        type="button"
                        className="btn btn-danger"
                        onClick={() => onDeleteRecord(row)}
                        disabled={deletingId === row.id}
                      >
                        {deletingId === row.id ? 'Deleting…' : 'Delete'}
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {registerOpen ? (
        <div
          className="scan-modal-backdrop"
          role="presentation"
          onClick={closeRegisterModal}
        >
          <div
            className="scan-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="sig-register-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-head">
              <h2 id="sig-register-title">Register signature</h2>
              <button
                type="button"
                className="scan-remove-btn"
                onClick={closeRegisterModal}
                disabled={regLoading}
              >
                Close
              </button>
            </div>
            <p className="hint">
              Store a specimen signature against an account number for future comparisons.
            </p>

            <form onSubmit={onRegister}>
              <label className="field">
                Account number
                <input
                  value={regAccount}
                  onChange={(e) => setRegAccount(e.target.value)}
                  placeholder="e.g. 0123456789"
                  autoComplete="off"
                  required
                />
              </label>

              <label className="field">
                Customer name <span className="hint-inline">(optional)</span>
                <input
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  placeholder="Account holder name"
                  autoComplete="off"
                />
              </label>

              <p className="field-label">Signature image</p>
              <SignatureDropzone
                file={regFile}
                preview={regPreview}
                onPick={pickRegisterFile}
                onClear={() => {
                  setRegFile(null)
                  setRegPreview(null)
                  if (registerInputRef.current) registerInputRef.current.value = ''
                }}
                inputRef={registerInputRef}
                dragging={regDragging}
                setDragging={setRegDragging}
              />

              {regError ? <p className="status-line error">{regError}</p> : null}
              {regSuccess ? <p className="status-line success">{regSuccess}</p> : null}

              <div className="sig-actions">
                <button type="submit" className="btn" disabled={regLoading}>
                  {regLoading ? 'Saving…' : 'Register signature'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={closeRegisterModal}
                  disabled={regLoading}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {viewRecord ? (
        <div
          className="scan-modal-backdrop"
          role="presentation"
          onClick={() => setViewRecord(null)}
        >
          <div
            className="scan-modal sig-view-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="sig-view-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-head">
              <h2 id="sig-view-title">Signature details</h2>
              <button
                type="button"
                className="scan-remove-btn"
                onClick={() => setViewRecord(null)}
              >
                Close
              </button>
            </div>

            <div className="sig-view-content">
              <img
                src={viewRecord.image_url}
                alt={`Signature for ${viewRecord.account_number}`}
                className="sig-view-img"
              />
              <dl className="scan-kv-grid">
                <div className="scan-kv-item">
                  <dt>Account</dt>
                  <dd>{viewRecord.account_number}</dd>
                </div>
                <div className="scan-kv-item">
                  <dt>Customer</dt>
                  <dd>{viewRecord.customer_name || '—'}</dd>
                </div>
                <div className="scan-kv-item">
                  <dt>File</dt>
                  <dd>{viewRecord.original_filename || '—'}</dd>
                </div>
                <div className="scan-kv-item">
                  <dt>Registered</dt>
                  <dd>{formatWhen(viewRecord.created_at)}</dd>
                </div>
                <div className="scan-kv-item">
                  <dt>Updated</dt>
                  <dd>{formatWhen(viewRecord.updated_at)}</dd>
                </div>
              </dl>
            </div>

            <div className="sig-actions">
              <Button
                variant="danger"
                loading={deletingId === viewRecord.id}
                onClick={() => onDeleteRecord(viewRecord)}
              >
                Delete signature
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="Delete signature?"
        message={`Remove the registered signature for account ${confirmDelete?.account_number || ''}? This cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        loading={Boolean(deletingId)}
        onConfirm={confirmDeleteRecord}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  )
}
