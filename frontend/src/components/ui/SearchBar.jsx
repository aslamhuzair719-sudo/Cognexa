export default function SearchBar({
  value,
  onChange,
  placeholder = 'Search…',
  onClear,
  className = '',
}) {
  return (
    <div className={`search-bar ${className}`.trim()}>
      <svg className="search-bar-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
        <path d="M20 20l-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <input
        type="search"
        className="search-bar-input"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        aria-label="Search"
      />
      {value ? (
        <button
          type="button"
          className="search-bar-clear"
          onClick={onClear || (() => onChange({ target: { value: '' } }))}
          aria-label="Clear search"
        >
          ×
        </button>
      ) : null}
    </div>
  )
}

export function FilterChip({ label, active, onClick }) {
  return (
    <button
      type="button"
      className={`filter-chip${active ? ' active' : ''}`}
      onClick={onClick}
    >
      {label}
    </button>
  )
}
