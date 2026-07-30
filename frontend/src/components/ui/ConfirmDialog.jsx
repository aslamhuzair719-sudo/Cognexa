import Button from './Button.jsx'

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  loading = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null

  return (
    <div className="scan-modal-backdrop modal-enter" role="presentation" onClick={onCancel}>
      <div
        className="scan-modal confirm-dialog modal-content-enter"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="confirm-dialog-icon" aria-hidden>
          {variant === 'danger' ? '!' : '?'}
        </div>
        <h2 id="confirm-title">{title}</h2>
        <p className="hint">{message}</p>
        <div className="sig-actions">
          <Button variant={variant} loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
