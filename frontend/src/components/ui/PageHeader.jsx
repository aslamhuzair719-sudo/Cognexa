/**
 * Consistent page heading for branch console screens.
 */
export default function PageHeader({
  eyebrow,
  title,
  description,
  badge,
  actions,
  children,
  className = '',
}) {
  return (
    <header className={`page-header ${className}`.trim()}>
      <div className="page-header-main">
        {eyebrow ? <p className="page-header-eyebrow">{eyebrow}</p> : null}
        <div className="page-header-title-row">
          <h1 className="page-header-title">{title}</h1>
          {badge ? <span className="page-header-badge">{badge}</span> : null}
        </div>
        {description ? <p className="page-header-desc">{description}</p> : null}
        {children}
      </div>
      {actions ? <div className="page-header-actions">{actions}</div> : null}
    </header>
  )
}
