/**
 * Accessible labelled form control with hint and error states.
 */
export default function FormField({
  label,
  htmlFor,
  required = false,
  hint,
  error,
  success,
  className = '',
  children,
  full = false,
}) {
  const id = htmlFor || undefined
  return (
    <label
      className={[
        'form-field',
        full ? 'form-field-full' : '',
        error ? 'has-error' : '',
        success ? 'has-success' : '',
        className,
      ].filter(Boolean).join(' ')}
      htmlFor={id}
    >
      {label ? (
        <span className="form-field-label">
          {label}
          {required ? <span className="form-field-required" aria-hidden> *</span> : null}
        </span>
      ) : null}
      <div className="form-field-control">{children}</div>
      {error ? <span className="form-field-error" role="alert">{error}</span> : null}
      {!error && hint ? <span className="form-field-hint">{hint}</span> : null}
    </label>
  )
}
