import { getFieldGroupsForMode } from '../config/scanForms.js'

function FieldControl({ field, value, onChange, readOnly }) {
  const filled = Boolean(String(value || '').trim())
  const control = field.full ? (
    <textarea
      rows={2}
      value={value || ''}
      readOnly={readOnly}
      placeholder={filled ? undefined : 'Not found on document'}
      onChange={onChange ? (e) => onChange(field.key, e.target.value) : undefined}
    />
  ) : (
    <input
      value={value || ''}
      readOnly={readOnly}
      placeholder={filled ? undefined : 'Not found on document'}
      onChange={onChange ? (e) => onChange(field.key, e.target.value) : undefined}
    />
  )

  return (
    <label className={`field banking-field${filled ? ' is-filled' : ' is-empty'}${field.full ? ' full' : ''}`}>
      <span className="banking-field-label">{field.label}</span>
      {control}
    </label>
  )
}

export default function ExtractedFieldGrid({
  fields,
  values,
  onChange,
  readOnly = false,
  mode = '',
}) {
  const groups = getFieldGroupsForMode(mode)
  if (!fields?.length) return null

  if (!groups.length) {
    return (
      <div className="scan-edit-grid">
        {fields.map((field) => (
          <FieldControl
            key={field.key}
            field={field}
            value={values[field.key]}
            onChange={onChange}
            readOnly={readOnly}
          />
        ))}
      </div>
    )
  }

  return (
    <div className="extract-sections">
      {groups.map((group) => {
        const groupFields = fields.filter((f) => f.group === group.id)
        if (!groupFields.length) return null
        const filledCount = groupFields.filter((f) => String(values[f.key] || '').trim()).length
        return (
          <section key={group.id} className="extract-section">
            <header className="extract-section-head">
              <h3>{group.title}</h3>
              <span>{filledCount}/{groupFields.length} captured</span>
            </header>
            <div className="scan-edit-grid">
              {groupFields.map((field) => (
                <FieldControl
                  key={field.key}
                  field={field}
                  value={values[field.key]}
                  onChange={onChange}
                  readOnly={readOnly}
                />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
