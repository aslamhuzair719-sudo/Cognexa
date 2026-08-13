import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { SourcePill } from '../components/StatusPill.jsx'
import AlertBanner from '../components/ui/AlertBanner.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import FormField from '../components/ui/FormField.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import SearchBar from '../components/ui/SearchBar.jsx'

function highlightSnippet(snippet, query) {
  if (!snippet || !query.trim()) return snippet
  const terms = query.trim().split(/\s+/).filter(Boolean)
  let html = snippet
  for (const term of terms) {
    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    html = html.replace(new RegExp(`(${escaped})`, 'gi'), '<mark>$1</mark>')
  }
  return html
}

export default function BranchArchivePage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [results, setResults] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState(null)

  const selected = useMemo(
    () => results.find((row) => row.id === selectedId) || results[0] || null,
    [results, selectedId],
  )

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setResults([])
      setTotal(0)
      setError('')
      return undefined
    }

    const timer = setTimeout(() => {
      setLoading(true)
      setError('')
      const params = new URLSearchParams({ q })
      if (sourceFilter !== 'all') params.set('source', sourceFilter)
      api(`/api/v1/branch/archive/search?${params.toString()}`)
        .then((data) => {
          setResults(data.results || [])
          setTotal(data.total || 0)
          setSelectedId((prev) => {
            if (prev && (data.results || []).some((row) => row.id === prev)) return prev
            return data.results?.[0]?.id || null
          })
        })
        .catch((err) => {
          setError(err.message || 'Search failed')
          setResults([])
          setTotal(0)
        })
        .finally(() => setLoading(false))
    }, 350)

    return () => clearTimeout(timer)
  }, [query, sourceFilter])

  function openRecord(row) {
    if (!row) return
    navigate(row.record_path)
  }

  return (
    <>
      <PageHeader
        eyebrow="Document archive"
        title="Archival search"
        badge={query.trim().length >= 2 ? `${total} match${total === 1 ? '' : 'es'}` : 'Ready'}
        description="Search OCR and AI-extracted text across branch scans, workflow customers, and customer portal documents."
      />

      {error ? <AlertBanner type="error" title="Search error" message={error} /> : null}

      <section className="panel panel-accent">
        <div className="search-toolbar">
          <SearchBar
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search names, CNIC, company, OCR text… e.g. Syed Huzair Aslam"
          />
          <FormField label="Source">
            <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
              <option value="all">All sources</option>
              <option value="branch_entry">Branch scans / workflow</option>
              <option value="customer_portal">Customer portal</option>
            </select>
          </FormField>
        </div>
        <p className="hint" style={{ marginTop: '0.75rem' }}>
          Type at least 2 characters. Each result is one document whose extracted text matched your query.
        </p>
      </section>

      <div className="dashboard-grid archive-search-grid" style={{ marginTop: '1rem' }}>
        <section className="panel archive-results-panel">
          <div className="panel-head">
            <h3 style={{ margin: 0 }}>Matching documents</h3>
            {loading ? <span className="hint">Searching…</span> : null}
          </div>

          {query.trim().length < 2 ? (
            <EmptyState
              icon="🔎"
              title="Start typing to search the archive"
              description="Extracted text from scanned documents is indexed automatically after OCR and AI extraction."
            />
          ) : loading ? (
            <p className="hint">Searching archived documents…</p>
          ) : results.length ? (
            <ul className="archive-result-list">
              {results.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    className={`archive-result-item${selected?.id === row.id ? ' active' : ''}`}
                    onClick={() => setSelectedId(row.id)}
                  >
                    <div className="archive-result-head">
                      <strong>{row.customer_name || 'Unknown customer'}</strong>
                      <SourcePill source={row.source} />
                    </div>
                    <p className="archive-result-meta">
                      {row.document_label || row.document_type}
                      {row.original_filename ? ` · ${row.original_filename}` : ''}
                    </p>
                    <p
                      className="archive-result-snippet"
                      dangerouslySetInnerHTML={{
                        __html: highlightSnippet(row.snippet, query),
                      }}
                    />
                    <p className="archive-result-date meta">
                      {(row.created_at || '').slice(0, 10) || '—'}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon="📄"
              title="No documents found"
              description={`No archived extracted text matched "${query.trim()}".`}
            />
          )}
        </section>

        <section className="panel archive-preview-panel">
          {selected ? (
            <>
              <div className="panel-head" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
                <div>
                  <p className="eyebrow" style={{ marginBottom: '0.2rem' }}>Selected document</p>
                  <h3 style={{ margin: 0 }}>{selected.document_label || selected.document_type}</h3>
                  <p className="hint" style={{ marginTop: '0.25rem' }}>
                    {selected.customer_name}
                    {selected.original_filename ? ` · ${selected.original_filename}` : ''}
                  </p>
                </div>
                <div className="actions" style={{ margin: 0 }}>
                  <a
                    className="btn btn-secondary"
                    href={selected.document_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open file
                  </a>
                  <button type="button" className="btn" onClick={() => openRecord(selected)}>
                    Open record
                  </button>
                </div>
              </div>

              <div className="archive-preview-frame">
                {selected.is_image ? (
                  <a href={selected.document_url} target="_blank" rel="noreferrer" className="doc-preview-link">
                    <img
                      src={selected.document_url}
                      alt={selected.document_label || 'Document preview'}
                      className="doc-preview-image"
                    />
                  </a>
                ) : selected.is_pdf ? (
                  <iframe
                    title={selected.document_label || 'Document preview'}
                    src={selected.document_url}
                    className="doc-preview-pdf"
                  />
                ) : (
                  <div className="empty-pane">
                    <p className="hint">Preview not available for this file type.</p>
                    <a className="btn btn-secondary" href={selected.document_url} target="_blank" rel="noreferrer">
                      Download document
                    </a>
                  </div>
                )}
              </div>

              <div className="archive-snippet-block">
                <p className="eyebrow">Matched text excerpt</p>
                <p
                  className="archive-result-snippet block"
                  dangerouslySetInnerHTML={{
                    __html: highlightSnippet(selected.snippet, query),
                  }}
                />
              </div>

              <p className="hint">
                Record:{' '}
                <Link to={selected.record_path}>{selected.record_id}</Link>
              </p>
            </>
          ) : (
            <EmptyState
              icon="📂"
              title="Select a document"
              description="Choose a search result to preview the file and matched OCR text."
            />
          )}
        </section>
      </div>
    </>
  )
}
