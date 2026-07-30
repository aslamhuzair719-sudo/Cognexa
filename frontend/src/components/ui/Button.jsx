export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  className = '',
  type = 'button',
  ...props
}) {
  const cls = [
    'btn',
    variant !== 'primary' ? `btn-${variant}` : '',
    size !== 'md' ? `btn-${size}` : '',
    loading ? 'btn-loading' : '',
    className,
  ].filter(Boolean).join(' ')

  return (
    <button type={type} className={cls} disabled={disabled || loading} {...props}>
      {loading ? <span className="btn-spinner" aria-hidden /> : null}
      <span className="btn-label">{children}</span>
    </button>
  )
}
