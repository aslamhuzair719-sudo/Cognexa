import { useEffect, useState } from 'react'

/** Live AI activity timeline — used by scan + application review. */

export function AiActivityPanel({
  title = 'Cognexa AI Activity',
  message,
  steps = [],
  messages = [],
  aiWorking = false,
  compact = false,
  collapsible = false,
  defaultCollapsed = false,
}) {
  const [collapsed, setCollapsed] = useState(Boolean(defaultCollapsed && !aiWorking))

  useEffect(() => {
    if (aiWorking) {
      setCollapsed(false)
      return
    }
    if (collapsible && defaultCollapsed) setCollapsed(true)
  }, [aiWorking, collapsible, defaultCollapsed])

  if (!steps.length && !message && !messages.length) return null

  const isCollapsed = collapsible && collapsed && !aiWorking
  const doneCount = steps.filter((s) => s.state === 'done').length

  return (
    <div className={`ai-activity${compact ? ' compact' : ''}${aiWorking ? ' working' : ''}${isCollapsed ? ' is-collapsed' : ''}`}>
      <div className="ai-activity-head">
        <div>
          <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>{title}</p>
          <p className="ai-activity-live">
            {aiWorking ? (
              <>
                <span className="ai-pulse" aria-hidden="true" />
                <strong>Cognexa AI is working…</strong>
                {message ? <span> — {message}</span> : null}
              </>
            ) : (
              <span>{message || 'Cognexa AI finished this run.'}</span>
            )}
          </p>
        </div>
        {collapsible && !aiWorking ? (
          <button
            type="button"
            className="ai-activity-toggle"
            aria-expanded={!isCollapsed}
            onClick={() => setCollapsed((v) => !v)}
          >
            {isCollapsed ? `Show activity (${doneCount || steps.length} steps)` : 'Collapse'}
          </button>
        ) : null}
      </div>

      {isCollapsed ? null : (
        <>
          {steps.length > 0 && (
            <ol className="ai-step-list" aria-label="Cognexa AI processing steps">
              {steps.map((step) => (
                <li key={step.id} className={`ai-step ${step.state || 'todo'}`}>
                  <span className="ai-step-marker" aria-hidden="true">
                    {step.state === 'done' ? '✓' : step.state === 'active' ? '●' : '○'}
                  </span>
                  <span className="ai-step-label">{step.label}</span>
                  {step.state === 'active' && step.activeMsg ? (
                    <span className="ai-step-active-msg">{step.activeMsg}</span>
                  ) : null}
                </li>
              ))}
            </ol>
          )}

          {messages.length > 0 && (
            <ul className="ai-done-messages">
              {messages.map((m, i) => (
                <li key={`${i}-${m}`}>{m}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

export function buildScanSteps(docType, activeIndex, { finished = false } = {}) {
  const defs = [
    { id: 'upload', label: 'File uploaded' },
    { id: 'doc_detect', label: 'Stage 1: Checking whether image is a document', activeMsg: 'Cognexa AI is checking document presence…' },
    { id: 'doc_type', label: 'Stage 2: Detecting supported document type', activeMsg: 'Cognexa AI is verifying document support (CNIC, Payslip, Remittance)…' },
    { id: 'quality', label: 'Stage 3: Image Quality & Metadata Analysis' },
    { id: 'ocr', label: 'Stage 6: OCR / Field Extraction', activeMsg: 'Cognexa AI is extracting structured data…' },
    { id: 'done', label: 'Report Generated' },
  ]

  return defs.map((step, index) => {
    let state = 'todo'
    if (finished || index < activeIndex) state = 'done'
    else if (index === activeIndex) state = 'active'
    return { ...step, state }
  })
}
