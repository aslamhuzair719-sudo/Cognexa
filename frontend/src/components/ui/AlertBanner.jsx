const ICONS = {
  success: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  error: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
      <path d="M12 8v5m0 3h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  warning: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  info: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
      <path d="M12 16v-4m0-4h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
}

/**
 * Inline success / error / warning banner for forms and page-level feedback.
 */
export default function AlertBanner({
  type = 'info',
  title,
  message,
  onDismiss,
  className = '',
  children,
}) {
  if (!title && !message && !children) return null

  return (
    <div
      className={`alert-banner alert-banner-${type} ${className}`.trim()}
      role={type === 'error' ? 'alert' : 'status'}
    >
      <span className="alert-banner-icon">{ICONS[type] || ICONS.info}</span>
      <div className="alert-banner-body">
        {title ? <strong className="alert-banner-title">{title}</strong> : null}
        {message ? <p className="alert-banner-message">{message}</p> : null}
        {children}
      </div>
      {onDismiss ? (
        <button type="button" className="alert-banner-dismiss" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      ) : null}
    </div>
  )
}
