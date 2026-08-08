import { useState } from 'react'

function badge(result) {
  const cls = String(result || '').toUpperCase()
  return <span className={`badge ${cls}`}>{cls}</span>
}

function escapeText(value) {
  return value == null || value === '' ? '—' : String(value)
}

function Comparisons({ comparisons }) {
  if (!comparisons?.length) return <p className="hint">No comparisons.</p>
  return (
    <div className="table-wrap">
      <table className="data-grid dense">
        <thead>
          <tr>
            <th>Field</th>
            <th>Customer</th>
            <th>Document</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {comparisons.map((c, idx) => {
            const result = String(c.result || '').toUpperCase()
            const rowClass = result === 'FAIL' ? 'comparison-mismatch' : result === 'PASS' ? 'comparison-match' : ''
            return (
              <tr key={`${c.field}-${idx}`} className={rowClass}>
                <td>{escapeText(c.field)}</td>
                <td>{escapeText(c.customer_value)}</td>
                <td>
                  {escapeText(c.document_value)}
                  {c.document_source ? (
                    <div className="meta">{c.document_source}</div>
                  ) : null}
                </td>
                <td>{badge(c.result)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

const SECTIONS = [
  ['customer_information_validation', 'Customer information'],
  ['cnic_validation', 'CNIC validation'],
  ['payslip_validation', 'Payslip validation'],
  ['bank_statement_validation', 'Bank statement validation'],
  ['cross_validation', 'Cross validation'],
]

const DOC_LABELS = {
  cnic_front: 'CNIC front',
  cnic_back: 'CNIC back',
  payslip: 'Payslip',
  bank_statement: 'Bank statement',
}

function sectionResultCounts(comparisons) {
  const counts = { pass: 0, fail: 0, warn: 0 }
  ;(comparisons || []).forEach((item) => {
    const value = String(item.result || '').toUpperCase()
    if (value === 'PASS') counts.pass += 1
    else if (value === 'FAIL') counts.fail += 1
    else counts.warn += 1
  })
  return counts
}

function SectionToggleHeader({ title, subtitle, isOpen, onToggle }) {
  return (
    <div className="section-toggle-header">
      <div>
        <h3>{title}</h3>
        {subtitle ? <p className="hint">{subtitle}</p> : null}
      </div>
      <button type="button" className="toggle-button" onClick={onToggle}>
        {isOpen ? 'Hide details' : 'Show details'}
      </button>
    </div>
  )
}

function SectionSummary({ comparisons }) {
  const { pass, fail, warn } = sectionResultCounts(comparisons)
  return (
    <div className="section-summary-grid">
      <div>
        <span className="summary-label">Pass</span>
        <strong>{pass}</strong>
      </div>
      <div>
        <span className="summary-label">Fail</span>
        <strong>{fail}</strong>
      </div>
      <div>
        <span className="summary-label">Warnings</span>
        <strong>{warn}</strong>
      </div>
    </div>
  )
}

function docKeyFromLabel(label) {
  const text = String(label || '').toLowerCase().replace(/\s+/g, '_')
  if (text.includes('cnic_front') || text === 'cnic front') return 'cnic_front'
  if (text.includes('cnic_back') || text === 'cnic back') return 'cnic_back'
  if (text.includes('payslip')) return 'payslip'
  if (text.includes('bank')) return 'bank_statement'
  return null
}

function isImageDoc(doc) {
  if (!doc) return false
  if (doc.is_image) return true
  const name = String(doc.filename || doc.path || '').toLowerCase()
  return /\.(png|jpe?g|webp|gif|bmp|tiff?)$/.test(name)
}

function isPdfDoc(doc) {
  if (!doc) return false
  if (doc.is_pdf) return true
  const name = String(doc.filename || doc.path || '').toLowerCase()
  return name.endsWith('.pdf')
}

function DocumentGallery({ documents, title = 'Attached documents' }) {
  if (!documents || !Object.keys(documents).length) return null

  return (
    <div className="section-block doc-gallery-block">
      <h3>{title}</h3>
      <div className="doc-gallery">
        {Object.entries(documents).map(([key, doc]) => (
          <figure key={key} className="doc-card">
            <figcaption>
              <span>{DOC_LABELS[key] || key}</span>
              <a href={`${doc.url}?download=true`} target="_blank" rel="noreferrer">
                Download
              </a>
            </figcaption>
            {isImageDoc(doc) ? (
              <a href={doc.url} target="_blank" rel="noreferrer" className="doc-preview-link">
                <img src={doc.url} alt={DOC_LABELS[key] || key} className="doc-preview-image" />
              </a>
            ) : isPdfDoc(doc) ? (
              <iframe
                title={DOC_LABELS[key] || key}
                src={doc.url}
                className="doc-preview-pdf"
              />
            ) : (
              <a className="doc-link" href={doc.url} target="_blank" rel="noreferrer">
                Open file
              </a>
            )}
          </figure>
        ))}
      </div>
    </div>
  )
}

function countResults(items, key = 'overall') {
  if (!items?.length) return { pass: 0, fail: 0, warn: 0 }
  return items.reduce((acc, item) => {
    const val = String(item[key] || '').toUpperCase()
    if (val === 'PASS') acc.pass += 1
    else if (val === 'FAIL') acc.fail += 1
    else acc.warn += 1
    return acc
  }, { pass: 0, fail: 0, warn: 0 })
}

export default function ReportView({ report, documents }) {
  if (!report) return null

  const qualityStats = countResults(report.image_quality, 'overall')
  const uploadCount = (report.uploaded_documents || []).filter((d) => d.uploaded).length
  const extractionOk = (report.uploaded_documents || []).filter((d) => d.extraction_ok).length
  const score = Number(report.overall_score) || 0
  const scoreTone = score >= 80 ? 'pass' : score >= 60 ? 'warn' : 'fail'

  const [expandedSections, setExpandedSections] = useState(() => ({
    uploaded_documents: false,
    image_quality: false,
    customer_information_validation: false,
    cnic_validation: false,
    payslip_validation: false,
    bank_statement_validation: false,
    cross_validation: false,
    documents: false,
  }))
  const [showAllDetails, setShowAllDetails] = useState(false)

  const toggleSection = (key) => {
    setExpandedSections((previous) => ({
      ...previous,
      [key]: !previous[key],
    }))
  }

  const warnings = report.warnings || []
  const missing = report.missing_information || []

  return (
    <section className="report">
      <header className="report-premium-header">
        <div>
          <p className="eyebrow">Cognexa AI Verification Report</p>
          <h2>{report.application_status}</h2>
          <p style={{ fontWeight: 700, color: 'var(--accent-deep)', margin: '0.35rem 0 0' }}>
            Recommendation: {report.recommendation}
          </p>
        </div>
        <div className="report-score-block">
          <div className="score-ring">{score}%</div>
          <span className="score-ring-label">Overall score</span>
        </div>
      </header>

      <div className="report-summary-grid">
        <article className="report-summary-card">
          <span className="summary-label">Documents uploaded</span>
          <strong>{uploadCount}</strong>
        </article>
        <article className="report-summary-card">
          <span className="summary-label">Extraction OK</span>
          <strong>{extractionOk}/{uploadCount || '—'}</strong>
        </article>
        <article className="report-summary-card">
          <span className="summary-label">Quality pass</span>
          <strong>{qualityStats.pass}</strong>
        </article>
        <article className="report-summary-card">
          <span className="summary-label">Warnings</span>
          <strong>{warnings.length}</strong>
        </article>
      </div>

      <div className="section-block report-summary-toggle">
        <button type="button" className="link-btn" onClick={() => setShowAllDetails((prev) => !prev)}>
          {showAllDetails ? 'Hide full report details' : 'Show full report details'}
        </button>
        <p className="hint" style={{ margin: '0.75rem 0 0' }}>
          By default, only top-level summaries are shown to reduce scrolling.
        </p>
      </div>

      {showAllDetails ? (
        <section className="section-block">
          <h3>Quick summary</h3>
          <ul className="report-summary-list">
            {(report.summary || []).slice(0, 3).map((item) => (
              <li key={item}>{item}</li>
            ))}
            {report.summary?.length > 3 ? (
              <li className="hint">{report.summary.length - 3} more summary points hidden</li>
            ) : null}
          </ul>
        </section>
      ) : (
        <section className="section-block">
          <h3>Full report details hidden</h3>
          <p className="hint" style={{ margin: 0 }}>
            Only the highest-level report summary is shown to keep this page short.
            Expand the full report to inspect warnings, missing items, documents, and validation results.
          </p>
        </section>
      )}

      {showAllDetails ? (
        <div className="report-block-grid">
          <article className="section-block compact-block">
            <SectionToggleHeader
              title="Uploaded documents"
              subtitle={`${uploadCount} file${uploadCount === 1 ? '' : 's'} uploaded`}
              isOpen={expandedSections.uploaded_documents}
              onToggle={() => toggleSection('uploaded_documents')}
            />
            {expandedSections.uploaded_documents ? (
              <div className="table-wrap">
                <table className="data-grid dense">
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Uploaded</th>
                      <th>Extracted</th>
                      <th>Preview</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(report.uploaded_documents || []).map((d) => {
                      const key = docKeyFromLabel(d.document_label)
                      const file = key && documents ? documents[key] : null
                      return (
                        <tr key={d.document_label}>
                          <td>{d.document_label}</td>
                          <td>{d.uploaded ? 'Yes' : 'No'}</td>
                          <td>{d.extraction_ok ? badge('PASS') : badge('FAIL')}</td>
                          <td>
                            {file?.url ? (
                              <a href={file.url} target="_blank" rel="noreferrer">
                                Open
                              </a>
                            ) : (
                              '—'
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <SectionSummary comparisons={report.uploaded_documents || []} />
            )}
          </article>

          <article className="section-block compact-block">
            <SectionToggleHeader
              title="Image quality"
              subtitle={`${report.image_quality?.length || 0} documents checked`}
              isOpen={expandedSections.image_quality}
              onToggle={() => toggleSection('image_quality')}
            />
            {expandedSections.image_quality ? (
              <div className="table-wrap">
                <table className="data-grid dense">
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Overall</th>
                      <th>Readable</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(report.image_quality || []).map((q) => (
                      <tr key={q.document_label}>
                        <td>{q.document_label}</td>
                        <td>{badge(q.overall)}</td>
                        <td>{q.readable ? 'Yes' : 'No'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <SectionSummary comparisons={report.image_quality || []} />
            )}
          </article>
        </div>
      ) : null}

      {showAllDetails ? (
        <>
          <SectionToggleHeader
            title="Customer documents"
            subtitle={`${Object.keys(documents || {}).length} asset${Object.keys(documents || {}).length === 1 ? '' : 's'}`}
            isOpen={expandedSections.documents}
            onToggle={() => toggleSection('documents')}
          />
          {expandedSections.documents ? <DocumentGallery documents={documents} /> : null}

          {SECTIONS.map(([key, title]) => {
            const section = report[key]
            if (!section) return null
            return (
              <article className="section-block" key={key}>
                <SectionToggleHeader
                  title={title}
                  subtitle={section.notes?.length ? section.notes.join(' · ') : undefined}
                  isOpen={expandedSections[key]}
                  onToggle={() => toggleSection(key)}
                />
                {!expandedSections[key] ? (
                  <SectionSummary comparisons={section.comparisons} />
                ) : (
                  <Comparisons comparisons={section.comparisons} />
                )}
              </article>
            )
          })}
        </>
      ) : null}

      {report.recommendation_detail ? (
        <p className="hint" style={{ marginTop: '1rem' }}>
          {report.recommendation_detail}
        </p>
      ) : null}
    </section>
  )
}
