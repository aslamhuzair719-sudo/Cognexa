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

  return (
    <section className="report">
      <header className="report-premium-header">
        <div>
          <p className="eyebrow">AI Verification Report</p>
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

      <div className="report-metrics">
        <div className="report-metric">
          <span className="report-metric-label">Documents uploaded</span>
          <span className="report-metric-value">{uploadCount}</span>
        </div>
        <div className="report-metric">
          <span className="report-metric-label">Extraction success</span>
          <span className={`report-metric-value ${extractionOk === uploadCount && uploadCount > 0 ? 'pass' : 'warn'}`}>
            {extractionOk}/{uploadCount || '—'}
          </span>
        </div>
        <div className="report-metric">
          <span className="report-metric-label">Quality checks passed</span>
          <span className={`report-metric-value ${qualityStats.fail === 0 ? 'pass' : 'fail'}`}>
            {qualityStats.pass}
          </span>
        </div>
        <div className="report-metric">
          <span className="report-metric-label">Confidence</span>
          <span className={`report-metric-value ${scoreTone}`}>{score}%</span>
        </div>
      </div>

      <ul>
        {(report.summary || []).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <DocumentGallery documents={documents} title="Customer documents" />

      <div className="report-grid">
        <article className="section-block">
          <h3>Uploaded documents</h3>
          <table>
            <thead>
              <tr>
                <th>Document</th>
                <th>Uploaded</th>
                <th>Classified</th>
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
                    <td>
                      {escapeText(d.classified_as)}
                      {d.classification_confidence != null
                        ? ` (${d.classification_confidence})`
                        : ''}
                    </td>
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
        </article>
        <article className="section-block">
          <h3>Image quality</h3>
          <table>
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
        </article>
      </div>

      {SECTIONS.map(([key, title]) => {
        const section = report[key]
        if (!section) return null
        return (
          <div className="section-block" key={key}>
            <h3>
              <span>{title}</span>
              {badge(section.status)}
            </h3>
            <Comparisons comparisons={section.comparisons} />
          </div>
        )
      })}

      <div className="report-grid">
        <article className="section-block">
          <h3>Missing information</h3>
          <ul>
            {(report.missing_information || []).length
              ? report.missing_information.map((m) => <li key={m}>{m}</li>)
              : <li>None</li>}
          </ul>
        </article>
        <article className="section-block">
          <h3>Warnings</h3>
          <ul>
            {(report.warnings || []).length
              ? report.warnings.map((w) => <li key={w}>{w}</li>)
              : <li>None</li>}
          </ul>
        </article>
      </div>
      {report.recommendation_detail ? (
        <p className="hint" style={{ marginTop: '1rem' }}>
          {report.recommendation_detail}
        </p>
      ) : null}
    </section>
  )
}
