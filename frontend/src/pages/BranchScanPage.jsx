import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { AiActivityPanel, buildScanSteps } from '../components/AiActivityPanel.jsx'
import AlertBanner from '../components/ui/AlertBanner.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import {
  DOCUMENT_TYPES,
  buildDraftKeyFields,
  buildFormFromResult,
  customerNameGuess,
  docTypeLabel,
  getCheckboxesForMode,
  getTextFieldsForMode,
} from '../config/scanForms.js'

const CONFIDENCE_COLOR = {
  high:   { bg: '#e5f7ec', color: '#1f9a5c', border: '#b7e4c7' },
  medium: { bg: '#fff4d6', color: '#b07d08', border: '#f0df9a' },
  low:    { bg: '#fce8e8', color: '#d64545', border: '#f0c0c0' },
}

function humanizeKey(key) {
  return String(key || '').replace(/_/g, ' ')
}

/** Strip provider/model names from API summary text before showing in UI. */
function publicSummaryText(text) {
  if (!text) return ''
  return String(text)
    .replace(/\s*\([^)]*(?:gemini|groq|ollama|gpt-?|claude|flash|models\/)[^)]*\)/gi, '')
    .replace(/\bvia\s+Gemini(?:\s+vision)?\b/gi, 'via Cognexa AI')
    .replace(/\bvia\s+(?:Groq|Ollama)\b/gi, 'via Cognexa AI')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s+\./g, '.')
    .trim()
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
  const navigate = useNavigate()
  const [docType, setDocType]   = useState('remittance_slip')
  const [file, setFile]         = useState(null)
  const [preview, setPreview]   = useState(null)
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading]   = useState(false)
  const [workflowLoading, setWorkflowLoading] = useState(false)
  const [saving, setSaving]     = useState(false)
  const [result, setResult]     = useState(null)
  const [workflowResult, setWorkflowResult] = useState(null)
  const [workflowError, setWorkflowError] = useState(null)
  const [error, setError]       = useState(null)
  const [processingMode, setProcessingMode] = useState('single')
  const [workflowType, setWorkflowType] = useState('account_opening')
  const [reviewingGroupIndex, setReviewingGroupIndex] = useState(null)
  const [groupAnalyzeLoading, setGroupAnalyzeLoading] = useState(false)
  const [workflowAnalyzeAllLoading, setWorkflowAnalyzeAllLoading] = useState(false)
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
  const [editingWarning, setEditingWarning] = useState(null)
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
    setWorkflowResult(null)
    setWorkflowError(null)
    setEditingWarning(null)
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

  function resetWorkflow() {
    setWorkflowResult(null)
    setWorkflowError(null)
    setFile(null)
    setPreview(null)
    setWorkflowLoading(false)
  }

  function resetCurrentScan({ keepDraft = true } = {}) {
    setFile(null)
    setPreview(null)
    setResult(null)
    setError(null)
    setEditingWarning(null)
    setFormMode(null)
    setEditFields({})
    setEditChecks({})
    setEditTransactions([])
    setSavedNote(null)
    setScanStepIndex(0)
    setCompletionMessages([])
    originalFormRef.current = null
    resetWorkflow()
    if (inputRef.current) inputRef.current.value = ''
    if (!keepDraft) setDraftDocs([])
  }

  function onDragOver(e) { e.preventDefault(); setDragging(true) }
  function onDragLeave()  { setDragging(false) }

  async function handleScan(e, forceExtract = false) {
    if (processingMode !== 'single') {
      return
    }
    if (e && e.preventDefault) e.preventDefault()
    if (!file) { setError('Please select a document file first.'); return }
    setLoading(true)
    setError(null)
    if (!forceExtract) {
      setEditingWarning(null)
      setResult(null)
    }
    setFormMode(null)
    setEditFields({})
    setEditChecks({})
    setEditTransactions([])
    setSavedNote(null)
    setScanStepIndex(0)
    setCompletionMessages([])
    originalFormRef.current = null

    // Check for software editing metadata first if not forced
    if (!forceExtract) {
      const detectForm = new FormData()
      detectForm.append('selected_type', docType)
      detectForm.append('file', file)
      try {
        const detectData = await api('/api/v1/branch/detect-document', {
          method: 'POST',
          body: detectForm,
        })
        if (detectData?.editing_detected || (detectData?.flags && detectData.flags.length > 0)) {
          setEditingWarning(detectData)
          setLoading(false)
          showToast(
            'Software Editing Detected',
            'Image metadata indicates software editing. Click "Extract anyway" to proceed.',
          )
          return
        }
      } catch (err) {
        // Continue to scan if detect check fails
      }
    }

    setEditingWarning(null)
    const form = new FormData()
    form.append('document_type', docType)
    form.append('file', file)

    try {
      const data = await api('/api/v1/branch/scan-document', {
        method: 'POST',
        body: form,
      })
      setResult(data)

      if (data?.type_mismatch) {
        setFormMode(null)
        setEditFields({})
        setEditChecks({})
        setEditTransactions([])
        originalFormRef.current = null
        const msgs = data?.ai_activity?.messages || [
          data?.type_check?.message || 'Wrong document type.',
        ]
        setCompletionMessages(msgs)
        setScanStepIndex(99)
        showToast(
          'Wrong document type',
          data?.type_check?.message
            || `Selected ${docTypeLabel(docType)}, but the file looks different.`,
        )
        return
      }

      const built = buildFormFromResult(data, docType)
      setFormMode(built.mode)
      setEditFields(built.fields)
      setEditChecks(built.checkboxes)
      setEditTransactions(built.transactions || [])
      originalFormRef.current = {
        mode: built.mode,
        fields: { ...built.fields },
        checkboxes: { ...built.checkboxes },
        transactions: [...(built.transactions || [])],
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
          : (msgs[msgs.length - 1] || 'Cognexa AI finished this scan.'),
      )
    } catch (err) {
      setError(err.message || 'Scan failed. Please try again.')
      setCompletionMessages([])
    } finally {
      setLoading(false)
    }
  }

  async function handleWorkflowProcess(e) {
    if (e && e.preventDefault) e.preventDefault()
    if (processingMode !== 'workflow') {
      return
    }
    if (!file) {
      setWorkflowError('Please select a PDF file first.')
      return
    }
    const suffix = file.name.split('.').pop()?.toLowerCase()
    if (suffix !== 'pdf') {
      setWorkflowError('Workflow uploads must be a PDF file.')
      return
    }

    setWorkflowLoading(true)
    setWorkflowError(null)
    setWorkflowResult(null)
    try {
      const form = new FormData()
      form.append('workflow_type', workflowType)
      form.append('file', file)
      const data = await api('/api/v1/branch/process-workflow', {
        method: 'POST',
        body: form,
      })
      setWorkflowResult(data)
      setError(null)
      setResult(null)
    } catch (err) {
      setWorkflowError(err.message || 'Workflow processing failed. Please try again.')
    } finally {
      setWorkflowLoading(false)
    }
  }

  async function commitWorkflowGroup(groupIndex) {
    if (!file || !workflowResult) return
    setGroupAnalyzeLoading(true)
    try {
      const form = new FormData()
      form.append('workflow_type', workflowResult.workflow_type)
      form.append('group_index', String(groupIndex))
      form.append('file', file)
      await api('/api/v1/branch/process-workflow/commit-group', {
        method: 'POST',
        body: form,
      })
      showToast(
        'Queued for analysis',
        `${workflowResult.customer_groups[groupIndex]?.customer_id || 'Customer'} queued — OCR, extraction, and cross-check will run shortly.`,
      )
      navigate('/branch/queue')
    } catch (err) {
      showToast('Analyze failed', err.message || 'Failed to queue workflow group.')
    } finally {
      setGroupAnalyzeLoading(false)
    }
  }

  async function commitAllWorkflowGroups() {
    if (!file || !workflowResult?.customer_groups?.length) return
    setWorkflowAnalyzeAllLoading(true)
    try {
      const form = new FormData()
      form.append('workflow_type', workflowResult.workflow_type)
      form.append('file', file)
      const res = await api('/api/v1/branch/process-workflow/commit-all', {
        method: 'POST',
        body: form,
      })
      showToast(
        'All customers queued',
        res.message || `Queued ${res.count} customer(s) for sequential analysis.`,
      )
      navigate('/branch/queue')
    } catch (err) {
      showToast('Analyze all failed', err.message || 'Failed to queue workflow groups.')
    } finally {
      setWorkflowAnalyzeAllLoading(false)
    }
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
    const timers = [
      setTimeout(() => setScanStepIndex(1), 600),
      setTimeout(() => setScanStepIndex(2), 1600),
      setTimeout(() => setScanStepIndex(3), 2800),
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
    if (!result || !file || result.type_mismatch) return null
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
  const typeCheck = result?.type_check || null
  const typeMismatch = Boolean(result?.type_mismatch)
  const hasEditableForm = result && !typeMismatch && (
    Object.keys(editFields).length > 0 || editTransactions.length > 0
  )
  const liveSteps = buildScanSteps(docType, scanStepIndex, { finished: !loading && !!result })
  const liveMessage = loading
    ? (liveSteps.find((s) => s.state === 'active')?.activeMsg
      || liveSteps.find((s) => s.state === 'active')?.label
      || 'Cognexa AI is working…')
    : (completionMessages[completionMessages.length - 1] || 'Cognexa AI finished this scan.')
  const pendingSaveCount = draftDocs.length + (result && file && !typeMismatch ? 1 : 0)

  function useDetectedDocumentType() {
    const detected = typeCheck?.detected
    if (!detected || detected === 'unknown') return
    setDocType(detected)
    setResult(null)
    setFormMode(null)
    setEditFields({})
    setEditChecks({})
    setEditTransactions([])
    setCompletionMessages([])
    setError(null)
    originalFormRef.current = null
    showToast(
      'Document type updated',
      `Switched to ${typeCheck.detected_label}. Click Scan Document to extract.`,
    )
  }

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

      <PageHeader
        eyebrow="Branch tools"
        title="Document Scan & Review"
        badge="CNIC · Payslip · Remittance"
        description="Upload banking documents, run the Cognexa AI verification pipeline, correct extracted fields, and save multi-document Branch Entries."
      />

      <div className="scan-layout">
        {/* ── Upload panel ── */}
        <div className="panel scan-upload-panel">
          <div className="panel-head">
            <div>
              <h2>Upload Document</h2>
              <p className="hint" style={{ margin: 0 }}>PNG · JPG · WEBP · PDF · max 15 MB</p>
            </div>
          </div>
          <div style={{ marginBottom: '1rem' }}>
            <label className="field" style={{ marginBottom: '1rem' }}>
              Processing Mode
              <select
                value={processingMode}
                onChange={(e) => {
                  const nextMode = e.target.value
                  setProcessingMode(nextMode)
                  setError(null)
                  setWorkflowError(null)
                  setResult(null)
                  setWorkflowResult(null)
                  setEditingWarning(null)
                  setScanStepIndex(0)
                  setCompletionMessages([])
                  originalFormRef.current = null
                }}
                disabled={loading || workflowLoading}
              >
                <option value="single">Single Document</option>
                <option value="workflow">Workflow</option>
              </select>
            </label>

            {processingMode === 'workflow' && (
              <label className="field" style={{ marginBottom: '1rem' }}>
                Workflow
                <select
                  value={workflowType}
                  onChange={(e) => setWorkflowType(e.target.value)}
                  disabled={loading || workflowLoading}
                >
                  <option value="account_opening">Account Opening Workflow</option>
                </select>
                <p className="hint" style={{ marginTop: '0.5rem' }}>
                  Per customer: Account Opening Form, then Payslip, then CNIC.
                  Separate customers with a blank page (a page labelled "Blank Page" also works).
                  CNIC back is not required.
                </p>
              </label>
            )}
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
            {processingMode === 'single' && (
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
            )}

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

            {(error || workflowError) ? (
              <AlertBanner
                type="error"
                title="Scan failed"
                message={processingMode === 'workflow' ? (workflowError || error) : error}
              />
            ) : null}

            <div className="actions" style={{ marginTop: '1.1rem' }}>
              {processingMode === 'workflow' ? (
                <button
                  type="button"
                  className="btn"
                  onClick={handleWorkflowProcess}
                  disabled={workflowLoading || loading || !file}
                >
                  {workflowLoading
                    ? <><span className="scan-spinner" aria-hidden="true" /> Processing…</>
                    : <>Process Workflow</>
                  }
                </button>
              ) : (
                <>
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
                </>
              )}
              {(workflowResult || result || file || draftDocs.length > 0) && !loading && (
                <button type="button" className="btn btn-secondary" onClick={reset} disabled={saving || workflowLoading || workflowAnalyzeAllLoading}>
                  Clear
                </button>
              )}
            </div>
          </form>
        </div>

        {/* ── Editing Warning Gating Card ── */}
        {editingWarning && (
          <div className="scan-results" id="scan-editing-warning">
            <div className="panel scan-result-card scan-editing-warning-card">
              <div className="panel-head" style={{ flexWrap: 'wrap', gap: '0.6rem' }}>
                <div>
                  <p className="eyebrow amber-tag" style={{ marginBottom: '0.2rem' }}>
                    Metadata &amp; Forgery Security Alert
                  </p>
                  <h2 style={{ marginBottom: 0 }}>Digital Editing Software Detected</h2>
                </div>
                <span className="scan-type-badge bad">EDITING DETECTED</span>
              </div>
              <p className="scan-summary-text" style={{ marginTop: '0.75rem', marginBottom: '0.75rem' }}>
                Image metadata indicates that this document was created or modified using digital editing software (e.g. Canva / Photoshop). Extraction is paused to prevent unverified processing.
              </p>
              {editingWarning.flags && editingWarning.flags.length > 0 && (
                <ul className="scan-flags-list" style={{ margin: '0.5rem 0 1rem 0', paddingLeft: '1.2rem' }}>
                  {editingWarning.flags.map((flag, idx) => (
                    <li key={idx} className="scan-flag-item error" style={{ color: '#eab308', fontWeight: 600, fontSize: '0.9rem' }}>
                      {flag}
                    </li>
                  ))}
                </ul>
              )}
              <div className="actions" style={{ marginTop: '1.25rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="btn btn-warning-extract"
                  onClick={(e) => handleScan(e, true)}
                >
                  ⚡ Extract anyway
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={reset}
                >
                  Cancel / Clear
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Results ── */}
        {workflowResult && (
          <div className="scan-results" id="workflow-results">
            <div className="panel panel-accent scan-result-card">
              <div className="panel-head" style={{ flexWrap: 'wrap', gap: '0.6rem' }}>
                <div>
                  <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>Workflow Summary</p>
                  <h2 style={{ marginBottom: 0 }}>{workflowResult.workflow_label}</h2>
                </div>
                <span className={`scan-type-badge${workflowResult.status === 'COMPLETE' ? ' good' : ' bad'}`}>
                  {workflowResult.status}
                </span>
              </div>
              <div className="scan-type-compare">
                <div className="scan-type-col">
                  <span className="scan-type-label">Workflow ID</span>
                  <strong>{workflowResult.workflow_id}</strong>
                </div>
                <div className="scan-type-col">
                  <span className="scan-type-label">Pages</span>
                  <strong>{workflowResult.total_pages}</strong>
                </div>
              </div>
              {workflowResult.separator_pages?.length > 0 && (
                <p className="scan-summary-text" style={{ marginTop: '0.75rem' }}>
                  Separator pages detected: {workflowResult.separator_pages.join(', ')}.
                </p>
              )}
            </div>

            <div className="panel scan-result-card">
              <div className="panel-head" style={{ flexWrap: 'wrap', gap: '0.6rem' }}>
                <div>
                  <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>Customer Groups</p>
                  <h2 style={{ marginBottom: 0 }}>Detected document clusters</h2>
                </div>
              </div>
              <div style={{ margin: '1rem 0', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                <span className="eyebrow" style={{ margin: 0 }}>Workflow upload complete — grouped and classified.</span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={commitAllWorkflowGroups}
                  disabled={!file || workflowAnalyzeAllLoading || groupAnalyzeLoading || !workflowResult?.customer_groups?.length}
                >
                  {workflowAnalyzeAllLoading ? 'Queuing all…' : 'Analyze All & Open Queue'}
                </button>
              </div>
              {workflowResult.customer_groups.map((group, gidx) => (
                <div key={group.customer_id} className="scan-group-card" style={{ marginTop: '1rem', padding: '1rem', border: '1px solid #e2e8f0', borderRadius: '10px' }}>
                  <p className="eyebrow" style={{ marginBottom: '0.5rem' }}>Group {group.customer_id}</p>
                  <p style={{ margin: 0 }}><strong>Pages:</strong> {group.pages.map((doc) => doc.page).join(', ')}</p>
                  <p style={{ margin: '0.5rem 0' }}><strong>Validation:</strong> {group.validation.status}</p>
                  {group.validation.messages?.map((msg, idx) => (
                    <p key={idx} className="scan-summary-text" style={{ margin: '0.25rem 0' }}>{msg}</p>
                  ))}
                  {group.cross_document_checks?.length > 0 && (
                    <div style={{ marginTop: '0.75rem' }}>
                      <p className="eyebrow" style={{ marginBottom: '0.35rem' }}>Cross-document checks</p>
                      <ul className="scan-flag-list">
                        {group.cross_document_checks.map((check, idx) => (
                          <li key={idx}>
                            <strong>{check.field}</strong>: {check.match ? 'Match' : 'Mismatch'}
                            {check.values ? ` — ${check.values.join(', ')}` : ''}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem' }}>
                    <button type="button" className="btn" onClick={() => setReviewingGroupIndex(gidx)}>
                      Review
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => commitWorkflowGroup(gidx)}
                      disabled={!file || groupAnalyzeLoading || workflowAnalyzeAllLoading}
                    >
                      {groupAnalyzeLoading ? 'Queuing…' : 'Analyze & Open Queue'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Review modal for selected group */}
        {workflowResult && reviewingGroupIndex != null && (
          <div className="modal-overlay" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="panel" style={{ width: '720px', maxHeight: '80vh', overflow: 'auto' }}>
              <div className="panel-head">
                <h3>Review Group {workflowResult.customer_groups[reviewingGroupIndex].customer_id}</h3>
                <button type="button" className="scan-toast-close" onClick={() => setReviewingGroupIndex(null)}>×</button>
              </div>
              <div style={{ padding: '1rem' }}>
                <p><strong>Pages:</strong> {workflowResult.customer_groups[reviewingGroupIndex].pages.map(p => p.page).join(', ')}</p>
                <p><strong>Validation:</strong> {workflowResult.customer_groups[reviewingGroupIndex].validation.status}</p>
                <div style={{ marginTop: '0.75rem' }}>
                  {workflowResult.customer_groups[reviewingGroupIndex].pages.map((doc) => (
                    <div key={doc.page} style={{ padding: '0.5rem 0', borderBottom: '1px dashed #e6eef6' }}>
                      <strong>Page {doc.page}</strong>
                      <p style={{ margin: 0 }}>{doc.document_type_label} — Confidence: {Math.round((doc.confidence || 0) * 100)}</p>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                  <button type="button" className="btn" onClick={() => setReviewingGroupIndex(null)}>Close</button>
                  <button type="button" className="btn btn-ghost" onClick={() => commitWorkflowGroup(reviewingGroupIndex)} disabled={!file || groupAnalyzeLoading}>{groupAnalyzeLoading ? 'Queuing…' : 'Analyze & Open Queue'}</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {result && (
          <div className="scan-results" id="scan-results">

            <div className="panel panel-accent scan-result-card">
              <AiActivityPanel
                title="Cognexa AI Activity"
                message={liveMessage}
                steps={liveSteps}
                messages={completionMessages}
                aiWorking={false}
              />
            </div>

            {typeCheck && (
              <div
                className={`panel scan-result-card scan-type-check${
                  typeMismatch ? ' is-mismatch' : ' is-match'
                }`}
              >
                <div className="panel-head" style={{ flexWrap: 'wrap', gap: '0.6rem' }}>
                  <div>
                    <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>
                      Stage 1 &amp; Stage 2 Document Gate
                    </p>
                    <h2 style={{ marginBottom: 0 }}>
                      {!typeMismatch
                        ? 'Supported Document Confirmed'
                        : result?.gate?.status === 'not_a_document'
                          ? 'Invalid Upload — Not a Document'
                          : result?.gate?.status === 'unsupported_document'
                            ? 'Unsupported Document'
                            : 'Wrong Document Type'}
                    </h2>
                  </div>
                  <span
                    className={`scan-type-badge${typeMismatch ? ' bad' : ' good'}`}
                  >
                    {!typeMismatch
                      ? 'SUPPORTED'
                      : result?.gate?.status === 'not_a_document'
                        ? 'INVALID UPLOAD'
                        : result?.gate?.status === 'unsupported_document'
                          ? 'UNSUPPORTED'
                          : 'MISMATCH'}
                  </span>
                </div>

                <div className="scan-type-compare">
                  <div className="scan-type-col">
                    <span className="scan-type-label">Selected Document Type</span>
                    <strong>{typeCheck.selected_label || docTypeLabel(docType)}</strong>
                  </div>
                  <div className="scan-type-col">
                    <span className="scan-type-label">Detected by Cognexa AI</span>
                    <strong>{typeCheck.detected_label || 'Unknown'}</strong>
                  </div>
                </div>

                <p className="scan-summary-text" style={{ marginBottom: typeMismatch ? '0.85rem' : 0 }}>
                  {typeCheck.message}
                  {typeCheck.reason ? ` ${typeCheck.reason}` : ''}
                </p>

                {typeMismatch && (
                  <div className="scan-supported-banner" style={{ marginTop: '0.75rem', padding: '0.75rem', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <p className="eyebrow" style={{ marginBottom: '0.3rem', fontSize: '0.75rem', color: '#64748b' }}>
                      Supported Banking Documents (Demo Scope)
                    </p>
                    <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.85rem', color: '#334155' }}>
                      <li><strong>CNIC</strong> (Pakistani National Identity Card)</li>
                      <li><strong>Payslip</strong> (Salary / Pay Slip)</li>
                      <li><strong>Remittance</strong> (UBL Remittance / Transfer Slip)</li>
                    </ul>
                  </div>
                )}

                {typeMismatch && (
                  <div className="actions scan-edit-actions" style={{ marginTop: '1rem' }}>
                    {typeCheck.detected && !['unknown', 'not_a_document', 'other'].includes(typeCheck.detected) && ['cnic', 'payslip', 'remittance_slip'].includes(typeCheck.detected) ? (
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={useDetectedDocumentType}
                      >
                        Use as {typeCheck.detected_label}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => resetCurrentScan({ keepDraft: true })}
                    >
                      Upload different file
                    </button>
                  </div>
                )}
              </div>
            )}

            {!typeMismatch && (
            <div className="panel panel-accent scan-result-card">
              <div className="panel-head" style={{ flexWrap: 'wrap', gap: '0.6rem' }}>
                <div>
                  <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>Cognexa AI Extraction</p>
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
                {publicSummaryText(result.summary?.summary)
                  || 'Review the extracted values below and correct any mistakes.'}
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
            )}

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
                  <AlertBanner type="success" message={savedNote} className="alert-banner-compact" />
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
              Cognexa AI is working on your document…
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
              <AlertBanner type="error" message={saveError} className="alert-banner-compact" />
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
