export default function EmptyState({
  icon = '◌',
  title,
  description,
  actionLabel,
  onAction,
  children,
}) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon" aria-hidden>{icon}</div>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {children}
      {actionLabel && onAction ? (
        <button type="button" className="btn" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  )
}
