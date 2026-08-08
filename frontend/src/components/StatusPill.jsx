const LABELS = {
  pending: 'Pending',
  analyzing: 'Cognexa AI Reviewing',
  completed: 'Ready',
  accepted: 'Approved',
  rejected: 'Rejected',
  saved: 'Saved',
  submitted: 'Pending',
  analyzed: 'Ready',
  approved: 'Approved',
}

export default function StatusPill({ status }) {
  const value = String(status || 'pending').toLowerCase()
  const normalized =
    value === 'submitted' ? 'pending'
      : value === 'analyzed' ? 'completed'
        : value === 'approved' ? 'accepted'
          : value
  return (
    <span className={`status-pill ${normalized}`}>
      <span className="status-pill-dot" aria-hidden />
      {LABELS[value] || LABELS[normalized] || normalized}
    </span>
  )
}

export function SourcePill({ source }) {
  const value = String(source || '').toLowerCase()
  const label = value === 'branch_entry'
    ? 'Branch Entry'
    : value === 'customer_portal'
      ? 'Customer Portal'
      : (source || '—')
  return (
    <span className={`source-pill ${value || 'unknown'}`}>
      {label}
    </span>
  )
}
