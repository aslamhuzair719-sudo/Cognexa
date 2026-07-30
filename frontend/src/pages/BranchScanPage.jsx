import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { AiActivityPanel, buildScanSteps } from '../components/AiActivityPanel.jsx'
import {
  DOCUMENT_TYPES,
  buildDraftKeyFields,
  buildFormFromResult,
  customerNameGuess,
  docTypeLabel,
  getCheckboxesForMode,
  getTextFieldsForMode,
  isStructuredDocType,
} from '../config/scanForms.js'

const CONFIDENCE_COLOR = {
  high:   { bg: '#e5f7ec', color: '#1f9a5c', border: '#b7e4c7' },
  medium: { bg: '#fff4d6', color: '#b07d08', border: '#f0df9a' },
  low:    { bg: '#fce8e8', color: '#d64545', border: '#f0c0c0' },
}

function humanizeKey(key) {
  return String(key || '').replace(/_/g, ' ')
}

function buildDraftItem({ file, docType, result, fields, checkboxes, formMode, transactions = [] }) {
  const summary = {
    ...(result?.summary || {}),
    key_fields: buildDraftKeyFields(formMode, fields, checkboxes),
  }
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    file,
    document_type: docType,
    document_type_label: docTypeLabel(docType),
    original_filename: file?.name || 'document',
    fields: { ...fields },
    checkboxes: { ...checkboxes },
    transactions: [...transactions],
    extracted_text: result?.extracted_text || '',
    summary,
  }
}

function StructuredFieldGrid({ fields, editFields, onChange }) {
  return (
    <div className="scan-edit-grid">
      {fields.map(({ key, label, full }) => (
        <label key={key} className={`field${full ? ' full' : ''}`}>
          {label}
          {full ? (
            <textarea
              rows={2}
              value={editFields[key] || ''}
              onChange={(e) => onChange(key, e.target.value)}
            />
          ) : (
            <input
              value={editFields[key] || ''}
              onChange={(e) => onChange(key, e.target.value)}
            />
          )}
        </label>
      ))}
    </div>
  )
}

export default function BranchScanPage() {
  const [docType, setDocType]   = useState('remittance_slip')
  const [file, setFile]         = useState(null)
  const [preview, setPreview]   = useState(null)
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading]   = useState(false)
  const [saving, setSaving]     = useState(false)
  const [result, setResult]     = useState(null)
  const [error, setError]       = useState(null)
  const [formMode, setFormMode] = useState(null)
  const [editFields, setEditFields] = useState({})
  const [editChecks, setEditChecks] = useState({})
  const [editTransactions, setEditTransactions] = useState([])
  const [savedNote, setSavedNote] = useState(null)
  const [scanStepIndex, setScanStepIndex] = useState(0)
  const [completionMessages, setCompletionMessages] = useState([])
  const [toast, setToast] = useState(null)
  const [draftDocs, setDraftDocs] = useState([])
  const [saveOpen, setSaveOpen] = useState(false)
  const [customerName, setCustomerName] = useState('')
  const [saveError, setSaveError] = useState(null)
  const inputRef                = useRef(null)
  const originalFormRef         = useRef(null)
  const toastTimerRef           = useRef(null)

  function showToast(title, message) {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    setToast({ title, message })
    toastTimerRef.current = setTimeout(() => setToast(null), 5000)
  }

  function pickFile(f) {
    if (!f) return
    setFile(f)
    setResult(null)
    setError(null)
    setFormMode(null)
    setEditFields({})
    setEditChecks({})
    setEditTransactions([])
    setSavedNote(null)
    setCompletionMessages([])
    originalFormRef.current = null
    if (f.type.startsWith('image/')) {
      setPreview(URL.createObjectURL(f))
    } else {
      setPreview(null)
    }
  }

  function onInputChange(e) { pickFile(e.target.files?.[0]) }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    pickFile(e.dataTransfer.files?.[0])
  }

  function onDragOver(e) { e.preventDefault(); setDragging(true) }
  function onDragLeave()  { setDragging(false) }

  async function handleScan(e) {
    e.preventDefault()
    if (!file) { setError('Please select a document file first.'); return }
    setLoading(true)
    setError(null)
    setResult(null)
    setFormMode(null)
    setEditFields({})
    setEditChecks({})
    setEditTransactions([])
    setSavedNote(null)
    setScanStepIndex(0)
    setCompletionMessages([])
    originalFormRef.current = null

    const form = new FormData()
    form.append('document_type', docType)
    form.append('file', file)

    try {
      const data = await api('/api/v1/branch/scan-document', {
        method: 'POST',
        body: form,
      })
      setResult(data)
      const built = buildFormFromResult(data, docType)
      setFormMode(built.mode)
      setEditFields(built.fields)
      setEditChecks(built.checkboxes)
      originalFormRef.current = {
        mode: built.mode,
        fields: { ...built.fields },
        checkboxes: { ...built.checkboxes },
        transactions: [],
      }
      const msgs = data?.ai_activity?.messages || [
        'Document parsing complete.',
        'LLM summary complete.',
      ]
      setCompletionMessages(msgs)
      setScanStepIndex(99)
      const fieldCount = Object.keys(built.fields).length
      showToast(
        'Extraction complete',
        fieldCount > 0
          ? `${fieldCount} field${fieldCount === 1 ? '' : 's'} ready to review in the form below.`
          : (msgs[msgs.length - 1] || 'AI finished this scan.'),
      )
    } catch (err) {
      setError(err.message || 'Scan failed. Please try again.')
      setCompletionMessages([])
    } finally {
      setLoading(false)
    }
  }

  function resetCurrentScan({ keepDraft = true } = {}) {
    setFile(null)
    setPreview(null)
    setResult(null)
    setError(null)
    setFormMode(null)
    setEditFields({})
    setEditChecks({})
    setEditTransactions([])
    setSavedNote(null)
    setScanStepIndex(0)
    setCompletionMessages([])
    originalFormRef.current = null
    if (inputRef.current) inputRef.current.value = ''
    if (!keepDraft) setDraftDocs([])
  }

  function reset() {
    resetCurrentScan({ keepDraft: false })
    setToast(null)
    setSaveOpen(false)
    setCustomerName('')
    setSaveError(null)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
  }

  useEffect(() => {
    if (!loading) return undefined
    setScanStepIndex(0)
    const structured = isStructuredDocType(docType)
    const timers = structured
      ? [
          setTimeout(() => setScanStepIndex(1), 700),
          setTimeout(() => setScanStepIndex(2), 1800),
        ]
      : [
          setTimeout(() => setScanStepIndex(1), 600),
          setTimeout(() => setScanStepIndex(2), 2200),
        ]
    return () => timers.forEach(clearTimeout)
  }, [loading, docType])

  useEffect(() => () => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
  }, [])

  function updateField(key, value) {
    setEditFields((prev) => ({ ...prev, [key]: value }))
    setSavedNote(null)
  }

  function updateCheck(key, checked) {
    setEditChecks((prev) => ({ ...prev, [key]: checked }))
    setSavedNote(null)
  }

  function updateTransaction(index, key, value) {
    setEditTransactions((prev) => prev.map((row, i) => (
      i === index ? { ...row, [key]: value } : row
    )))
    setSavedNote(null)
  }

  function resetToLlm() {
    const original = originalFormRef.current
    if (!original) return
    setEditFields({ ...original.fields })
    setEditChecks({ ...original.checkboxes })
    setEditTransactions([...(original.transactions || [])])
    setSavedNote('Restored LLM-extracted values.')
  }

  function stashCurrentIfReady() {
    if (!result || !file) return null
    return buildDraftItem({
      file,
      docType,
      result,
      fields: editFields,
      checkboxes: editChecks,
      formMode,
      transactions: editTransactions,
    })
  }

  function uploadNextDocument() {
    const item = stashCurrentIfReady()
    if (!item) {
      setError('Scan a document and review the form before uploading the next one.')
      return
    }
    setDraftDocs((prev) => [...prev, item])
    resetCurrentScan({ keepDraft: true })
    showToast('Document added', `${item.document_type_label} ready. Upload the next document, then Save.`)
  }

  function openSaveModal() {
    const current = stashCurrentIfReady()
    const total = draftDocs.length + (current ? 1 : 0)
    if (total < 1) {
      setError('Scan at least one document before saving.')
      return
    }
    setSaveError(null)
    if (!customerName.trim()) {
      const guess = customerNameGuess(editFields, formMode)
      setCustomerName(String(guess === 'Cash' ? '' : guess))
    }
    setSaveOpen(true)
  }

  async function confirmSave() {
    const name = customerName.trim()
    if (!name) {
      setSaveError('Please enter the customer name.')
      return
    }
    const current = stashCurrentIfReady()
    const allDocs = current ? [...draftDocs, current] : [...draftDocs]
    if (!allDocs.length) {
      setSaveError('No documents to save.')
      return
    }

    setSaving(true)
    setSaveError(null)
    try {
      const form = new FormData()
      form.append('customer_name', name)
      form.append('payload', JSON.stringify({
        documents: allDocs.map((d) => ({
          document_type: d.document_type,
          fields: d.fields,
          checkboxes: d.checkboxes,
          transactions: d.transactions || [],
          extracted_text: d.extracted_text,
          summary: d.summary,
          original_filename: d.original_filename,
        })),
      }))
      allDocs.forEach((d) => form.append('files', d.file, d.original_filename))

      const data = await api('/api/v1/branch/branch-entries', {
        method: 'POST',
        body: form,
      })
      setSaveOpen(false)
      setCustomerName('')
      reset()
      showToast(
        'Branch Entry saved',
        data.message || `Saved ${allDocs.length} document(s) for ${name}.`,
      )
    } catch (err) {
      setSaveError(err.message || 'Save failed. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  function removeDraft(id) {
    setDraftDocs((prev) => prev.filter((d) => d.id !== id))
  }

  const conf      = result?.summary?.confidence
  const confStyle = CONFIDENCE_COLOR[conf] || CONFIDENCE_COLOR.low
  const flags     = result?.summary?.flags || []
  const hasEditableForm = result && (
    Object.keys(editFields).length > 0 || editTransactions.length > 0
  )
  const liveSteps = buildScanSteps(docType, scanStepIndex, { finished: !loading && !!result })
  const liveMessage = loading
    ? (liveSteps.find((s) => s.state === 'active')?.activeMsg
      || liveSteps.find((s) => s.state === 'active')?.label
      || 'AI is working…')
    : (completionMessages[completionMessages.length - 1] || 'AI finished this scan.')
  const pendingSaveCount = draftDocs.length + (result && file ? 1 : 0)

  return (
    <div className="scan-page">
      {toast && (
        <div
          className="scan-toast"
          role="status"
          aria-live="polite"
        >
          <span className="scan-toast-icon" aria-hidden="true">✓</span>
          <div className="scan-toast-body">
            <p className="scan-toast-title">{toast.title}</p>
            <p className="scan-toast-msg">{toast.message}</p>
          </div>
          <button
            type="button"
            className="scan-toast-close"
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            ×
          </button>
        </div>
      )}

      {/* ── Header ── */}
      <div className="hero hero-branch" style={{ marginBottom: '1.25rem' }}>
        <p className="eyebrow">Branch Tools</p>
        <h1 style={{ fontSize: 'clamp(1.6rem,3.5vw,2.4rem)', maxWidth: '26ch' }}>
          Document Scan &amp; Review
        </h1>
        <p className="hint" style={{ maxWidth: '42rem' }}>
          Upload banking documents, correct extracted fields, add more documents for the same
          customer, then Save as a Branch Entry.
        </p>
      </div>

      <div className="scan-layout">
        {/* ── Upload panel ── */}
        <div className="panel scan-upload-panel">
          <div className="panel-head">
            <div>
              <h2>Upload Document</h2>
              <p className="hint" style={{ margin: 0 }}>PNG · JPG · WEBP · PDF · max 15 MB</p>
            </div>
          </div>

          {draftDocs.length > 0 && (
            <div className="scan-draft-list">
              <p className="eyebrow" style={{ marginBottom: '0.5rem' }}>
                Ready to save ({draftDocs.length})
              </p>
              <ul>
                {draftDocs.map((d) => (
                  <li key={d.id}>
                    <span>
                      <strong>{d.document_type_label}</strong>
                      <span className="meta"> · {d.original_filename}</span>
                    </span>
                    <button
                      type="button"
                      className="scan-remove-btn"
                      onClick={() => removeDraft(d.id)}
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <form onSubmit={handleScan} id="scan-form">
            <label className="field" style={{ marginBottom: '1.1rem' }}>
              Document Type
              <select
                id="scan-doc-type"
                value={docType}
                onChange={(e) => {
                  const next = e.target.value
                  setDocType(next)
                  // Changing type invalidates the previous extraction form
                  if (result) {
                    setResult(null)
                    setFormMode(null)
                    setEditFields({})
                    setEditChecks({})
                    setEditTransactions([])
                    setSavedNote(null)
                    setCompletionMessages([])
                    originalFormRef.current = null
                  }
                }}
                disabled={loading}
              >
                {DOCUMENT_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </label>

            <div
              id="scan-dropzone"
              className={`scan-dropzone${dragging ? ' dragging' : ''}${file ? ' has-file' : ''}`}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onClick={() => !file && inputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && !file && inputRef.current?.click()}
              aria-label="Drop zone — click or drag a document here"
            >
              <input
                ref={inputRef}
                id="scan-file-input"
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.pdf"
                onChange={onInputChange}
                style={{ display: 'none' }}
                disabled={loading}
              />

              {!file ? (
                <div className="scan-dropzone-inner">
                  <div className="scan-drop-icon">
                    <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" width="42" height="42">
                      <rect x="6" y="8" width="36" height="32" rx="4" stroke="currentColor" strokeWidth="2.2"/>
                      <path d="M16 28l6-7 5 6 4-4 7 9H10l6-4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                      <circle cx="18" cy="18" r="3" stroke="currentColor" strokeWidth="2"/>
                      <path d="M32 4v10M28 8l4-4 4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                  <p className="scan-drop-title">Drag &amp; drop your document here</p>
                  <p className="scan-drop-sub">or <span className="scan-link">browse files</span></p>
                  <p className="scan-drop-formats">PNG · JPG · WEBP · BMP · TIFF · PDF</p>
                </div>
              ) : (
                <div className="scan-file-preview" onClick={e => e.stopPropagation()}>
                  {preview
                    ? <img src={preview} alt="Document preview" className="scan-preview-img" />
                    : (
                      <div className="scan-pdf-placeholder">
                        <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" width="36" height="36">
                          <path d="M10 6h20l8 8v28H10V6z" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round"/>
                          <path d="M30 6v8h8" stroke="currentColor" strokeWidth="2.2"/>
                          <path d="M16 22h16M16 28h16M16 34h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                        </svg>
                        <span>{file.name}</span>
                      </div>
                    )
                  }
                  <div className="scan-file-name">
                    <span className="scan-fname-text">{file.name}</span>
                    <span className="scan-file-size">({(file.size / 1024).toFixed(0)} KB)</span>
                    <button
                      type="button"
                      className="scan-remove-btn"
                      onClick={reset}
                      aria-label="Remove file"
                    >✕ Remove</button>
                  </div>
                </div>
              )}
            </div>

            {error && (
              <p className="status-line error" style={{ marginTop: '0.75rem' }}>{error}</p>
            )}

            <div className="actions" style={{ marginTop: '1.1rem' }}>
              <button
                id="scan-submit-btn"
                type="submit"
                className="btn"
                disabled={loading || saving || !file}
              >
                {loading
                  ? <><span className="scan-spinner" aria-hidden="true" /> Scanning…</>
                  : <>Scan Document</>
                }
              </button>
              {pendingSaveCount > 0 && !loading && (
                <button
                  type="button"
                  className="btn"
                  disabled={saving}
                  onClick={openSaveModal}
                >
                  Save ({pendingSaveCount})
                </button>
              )}
              {(result || file || draftDocs.length > 0) && !loading && (
                <button type="button" className="btn btn-secondary" onClick={reset} disabled={saving}>
                  Clear
                </button>
              )}
            </div>
          </form>
        </div>

        {/* ── Results ── */}
        {result && (
          <div className="scan-results" id="scan-results">

            <div className="panel panel-accent scan-result-card">
              <AiActivityPanel
                title="AI Activity"
                message={liveMessage}
                steps={liveSteps}
                messages={completionMessages}
                aiWorking={false}
              />
            </div>

            <div className="panel panel-accent scan-result-card">
              <div className="panel-head" style={{ flexWrap: 'wrap', gap: '0.6rem' }}>
                <div>
                  <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>AI Extraction</p>
                  <h2 style={{ marginBottom: 0 }}>{result.document_type}</h2>
                </div>
                {conf && (
                  <span
                    className="scan-confidence-badge"
                    style={{
                      background: confStyle.bg,
                      color:      confStyle.color,
                      border:     `1px solid ${confStyle.border}`,
                    }}
                  >
                    {conf.toUpperCase()} CONFIDENCE
                  </span>
                )}
              </div>

              <p className="scan-summary-text">
                {result.summary?.summary || 'Review the extracted values below and correct any mistakes.'}
              </p>

              {flags.length > 0 && (
                <div className="scan-flags" style={{ marginTop: 0, marginBottom: '0.9rem' }}>
                  <p className="eyebrow" style={{ marginBottom: '0.5rem' }}>Flags &amp; Observations</p>
                  <ul className="scan-flag-list">
                    {flags.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                </div>
              )}
            </div>

            {/* Editable review form */}
            {hasEditableForm && (
              <div className="panel scan-result-card">
                <div className="panel-head" style={{ flexWrap: 'wrap', gap: '0.6rem' }}>
                  <div>
                    <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>Review &amp; Correct</p>
                    <h2 style={{ marginBottom: 0 }}>Extracted Form</h2>
                  </div>
                  <p className="hint" style={{ margin: 0, flex: '1 1 100%' }}>
                    Values below were filled by the LLM. Edit any incorrect field, then apply corrections.
                  </p>
                </div>

                {formMode && formMode !== 'generic' ? (
                  <>
                    <StructuredFieldGrid
                      fields={getTextFieldsForMode(formMode)}
                      editFields={editFields}
                      onChange={updateField}
                    />
                    {getCheckboxesForMode(formMode).length > 0 && (
                      <div className="scan-checkbox-section">
                        <p className="eyebrow" style={{ marginBottom: '0.65rem' }}>Checkboxes</p>
                        <div className="scan-checkbox-grid">
                          {getCheckboxesForMode(formMode).map(({ key, label }) => (
                            <label key={key} className="scan-check-item">
                              <input
                                type="checkbox"
                                checked={Boolean(editChecks[key])}
                                onChange={(e) => updateCheck(key, e.target.checked)}
                              />
                              <span>{label}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="scan-edit-grid">
                    {Object.keys(editFields).map((key) => (
                      <label key={key} className="field">
                        {humanizeKey(key)}
                        <input
                          value={editFields[key] || ''}
                          onChange={(e) => updateField(key, e.target.value)}
                        />
                      </label>
                    ))}
                  </div>
                )}

                <div className="actions scan-edit-actions">
                  <button type="button" className="btn" onClick={openSaveModal} disabled={saving}>
                    Save
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={uploadNextDocument}
                    disabled={saving}
                  >
                    Upload next document
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={resetToLlm} disabled={saving}>
                    Reset to LLM Values
                  </button>
                </div>

                {savedNote && (
                  <p className="status-line ok" style={{ marginTop: '0.75rem' }}>{savedNote}</p>
                )}
                <p className="hint" style={{ marginTop: '0.65rem' }}>
                  Correct any fields, then Save with a customer name — or add another document
                  for the same customer first. Saved records appear in{' '}
                  <Link to="/branch/queue">Queue</Link> as Branch Entry.
                </p>
              </div>
            )}

            {/* Extracted text card */}
            {result.extracted_text && (
              <div className="panel scan-result-card">
                <div className="panel-head">
                  <div>
                    <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>Raw Output</p>
                    <h2 style={{ marginBottom: 0 }}>Extracted Text</h2>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ fontSize: '0.78rem', padding: '0.55rem 0.9rem', flexShrink: 0 }}
                    onClick={() => navigator.clipboard?.writeText(result.extracted_text).catch(() => {})}
                  >
                    Copy
                  </button>
                </div>
                <pre className="scan-ocr-text" id="scan-ocr-output">{result.extracted_text}</pre>
              </div>
            )}
          </div>
        )}

        {/* ── Empty state ── */}
        {!result && !loading && (
          <div className="scan-empty-state">
            <div className="scan-empty-icon">
              <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" width="56" height="56">
                <rect x="8" y="10" width="48" height="44" rx="5" stroke="currentColor" strokeWidth="2.2"/>
                <path d="M20 24h24M20 32h24M20 40h16" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"/>
                <circle cx="50" cy="14" r="9" fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth="2"/>
                <path d="M47 14h6M50 11v6" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round"/>
              </svg>
            </div>
            <p style={{ color: 'var(--ink)', fontWeight: 600, fontSize: '0.95rem', margin: '0.85rem 0 0.35rem', textAlign: 'center' }}>
              {draftDocs.length
                ? `${draftDocs.length} document(s) ready — scan another or Save`
                : 'No document scanned yet'}
            </p>
            <p style={{ color: 'var(--ink-muted)', fontSize: '0.84rem', margin: 0, textAlign: 'center', maxWidth: '24rem' }}>
              {draftDocs.length
                ? <>Upload another file and scan it, or click <strong>Save</strong> to store all documents under one customer.</>
                : <>Select a document type, upload an image or PDF, then click <strong>Scan Document</strong>.</>}
            </p>
            {draftDocs.length > 0 && (
              <button
                type="button"
                className="btn"
                style={{ marginTop: '1rem' }}
                onClick={openSaveModal}
              >
                Save ({draftDocs.length})
              </button>
            )}
          </div>
        )}

        {/* ── Loading state ── */}
        {loading && (
          <div className="scan-loading-state scan-loading-activity">
            <div className="scan-loading-orb" aria-hidden="true" />
            <p style={{ color: 'var(--ink)', fontWeight: 700, fontSize: '1rem', margin: '1.1rem 0 0.35rem' }}>
              AI is working on your document…
            </p>
            <div className="scan-loading-panel">
              <AiActivityPanel
                title="Live progress"
                message={liveMessage}
                steps={liveSteps}
                aiWorking
              />
            </div>
          </div>
        )}
      </div>

      {saveOpen && (
        <div className="scan-modal-backdrop" role="presentation" onClick={() => !saving && setSaveOpen(false)}>
          <div
            className="scan-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="scan-save-title"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="eyebrow" style={{ marginBottom: '0.25rem' }}>Branch Entry</p>
            <h2 id="scan-save-title" style={{ marginTop: 0 }}>Save documents</h2>
            <p className="hint">
              Saving {pendingSaveCount} document{pendingSaveCount === 1 ? '' : 's'} against one customer.
              This will appear in Queue with source <strong>Branch Entry</strong>.
            </p>
            <label className="field full">
              Customer name
              <input
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                placeholder="Enter customer full name"
                autoFocus
                disabled={saving}
              />
            </label>
            {saveError && (
              <p className="status-line error" style={{ marginTop: '0.75rem' }}>{saveError}</p>
            )}
            <div className="actions" style={{ marginTop: '1.1rem' }}>
              <button type="button" className="btn" onClick={confirmSave} disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setSaveOpen(false)}
                disabled={saving}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
