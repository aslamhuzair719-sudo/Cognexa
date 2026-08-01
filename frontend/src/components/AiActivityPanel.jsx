/** Live AI activity timeline — used by scan + application review. */

export function AiActivityPanel({
  title = 'AI Activity',
  message,
  steps = [],
  messages = [],
  aiWorking = false,
  compact = false,
}) {
  if (!steps.length && !message && !messages.length) return null

  return (
    <div className={`ai-activity${compact ? ' compact' : ''}${aiWorking ? ' working' : ''}`}>
      <div className="ai-activity-head">
        <div>
          <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>{title}</p>
          <p className="ai-activity-live">
            {aiWorking ? (
              <>
                <span className="ai-pulse" aria-hidden="true" />
                <strong>AI is working…</strong>
                {message ? <span> — {message}</span> : null}
              </>
            ) : (
              <span>{message || 'AI finished this run.'}</span>
            )}
          </p>
        </div>
      </div>

      {steps.length > 0 && (
        <ol className="ai-step-list" aria-label="AI processing steps">
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
    </div>
  )
}

export function buildScanSteps(docType, activeIndex, { finished = false } = {}) {
  const structured = ['remittance_slip', 'cnic', 'payslip', 'bank_statement'].includes(docType)
  const defs = structured
    ? [
        { id: 'upload', label: 'Document received' },
        { id: 'type', label: 'Checking document type', activeMsg: 'AI is identifying the document…' },
        { id: 'prepare', label: 'Preparing image for AI' },
        {
          id: 'llm',
          label: 'LLM is reading the document',
          activeMsg: 'AI is working on field extraction…',
        },
        { id: 'parse', label: 'Parsing structured fields' },
        { id: 'done', label: 'Extraction complete' },
      ]
    : [
        { id: 'upload', label: 'Document received' },
        { id: 'type', label: 'Checking document type', activeMsg: 'AI is identifying the document…' },
        { id: 'ocr', label: 'Parsing document text (OCR)' },
        { id: 'llm', label: 'LLM generating summary', activeMsg: 'AI is working on the summary…' },
        { id: 'done', label: 'Summary complete' },
      ]

  return defs.map((step, index) => {
    let state = 'todo'
    if (finished || index < activeIndex) state = 'done'
    else if (index === activeIndex) state = 'active'
    return { ...step, state }
  })
}
