import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import AlertBanner from '../components/ui/AlertBanner.jsx'

const EMPTY = {
  full_name: '',
  age: '',
  email: '',
  mobile_number: '',
  cnic_full_name: '',
  father_name: '',
  cnic_number: '',
  date_of_birth: '',
  cnic_issue_date: '',
  cnic_expiry_date: '',
  country_to_stay: '',
  gender: '',
  company_name: '',
  employee_id: '',
  designation: '',
  monthly_income: '',
  branch_code: '',
}

const BRANCHES = [
  { code: 'airport', name: 'Airport Branch' },
  { code: 'shah_faisal', name: 'Shahrae Faisal Branch' },
]

const FILE_FIELDS = [
  ['cnic_front', 'CNIC front', 'Clear photo of the front side'],
  ['cnic_back', 'CNIC back', 'Clear photo of the back side'],
  ['payslip', 'Payslip', 'Latest salary slip'],
  ['bank_statement', 'Bank statement', 'Recent statement PDF/image'],
]

const DATE_FIELDS = new Set(['date_of_birth', 'cnic_issue_date', 'cnic_expiry_date'])

const STEPS = [
  {
    id: 'personal',
    label: 'Personal',
    title: 'Enter your personal details.',
    hint: 'Please share your basic contact information.',
  },
  {
    id: 'cnic',
    label: 'Identity',
    title: 'Enter your Identity Card details.',
    hint: 'Please share details about your Identity Card.',
  },
  {
    id: 'employment',
    label: 'Employment',
    title: 'Enter your employment details.',
    hint: 'Please share your company and income information.',
  },
  {
    id: 'branch',
    label: 'Branch',
    title: 'Select your preferred branch.',
    hint: 'Your selected branch will review this application.',
  },
  {
    id: 'documents',
    label: 'Documents',
    title: 'Upload your supporting documents.',
    hint: 'PDF, PNG, or JPG. Clear scans work best.',
  },
]

function digitsOnly(value, max) {
  const next = String(value || '').replace(/\D/g, '')
  return max ? next.slice(0, max) : next
}

/** Auto-format DD/MM/YYYY while typing digits only. */
function formatDateInput(raw) {
  const digits = digitsOnly(raw, 8)
  const parts = []
  if (digits.length > 0) parts.push(digits.slice(0, 2))
  if (digits.length > 2) parts.push(digits.slice(2, 4))
  if (digits.length > 4) parts.push(digits.slice(4, 8))
  return parts.join('/')
}

/** Auto-format XXXXX-XXXXXXX-X while typing digits only. */
function formatCnicInput(raw) {
  const digits = digitsOnly(raw, 13)
  if (digits.length <= 5) return digits
  if (digits.length <= 12) return `${digits.slice(0, 5)}-${digits.slice(5)}`
  return `${digits.slice(0, 5)}-${digits.slice(5, 12)}-${digits.slice(12)}`
}

function isValidDateDMY(value) {
  if (!/^\d{2}\/\d{2}\/\d{4}$/.test(value)) return false
  const [dd, mm, yyyy] = value.split('/').map(Number)
  if (mm < 1 || mm > 12 || dd < 1 || dd > 31 || yyyy < 1900 || yyyy > 2100) return false
  const d = new Date(yyyy, mm - 1, dd)
  return d.getFullYear() === yyyy && d.getMonth() === mm - 1 && d.getDate() === dd
}

export default function CustomerPage() {
  const [step, setStep] = useState(0)
  const [animKey, setAnimKey] = useState(0)
  const [form, setForm] = useState(EMPTY)
  const [files, setFiles] = useState({})
  const [status, setStatus] = useState('')
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [cnicChecking, setCnicChecking] = useState(false)
  const [cnicVerified, setCnicVerified] = useState(null) // null | true | false
  const [cnicCheckMsg, setCnicCheckMsg] = useState('')

  const fileNames = useMemo(() => {
    const map = {}
    for (const [key] of FILE_FIELDS) {
      map[key] = files[key]?.name || 'No file selected'
    }
    return map
  }, [files])

  function updateField(name, value) {
    let next = value
    if (name === 'cnic_number') {
      next = formatCnicInput(value)
      setCnicVerified(null)
      setCnicCheckMsg('')
    } else if (DATE_FIELDS.has(name)) {
      next = formatDateInput(value)
    } else if (name === 'age') {
      next = digitsOnly(value, 3)
    } else if (name === 'mobile_number') {
      next = digitsOnly(value, 11)
    } else if (name === 'monthly_income') {
      next = digitsOnly(value, 12)
    }

    setForm((prev) => ({ ...prev, [name]: next }))
  }

  function goToStep(next) {
    setStatus('')
    setError(false)
    setStep(next)
    setAnimKey((k) => k + 1)
  }

  function validateStep(index) {
    if (index === 0) {
      for (const [key, label] of Object.entries({
        full_name: 'full name',
        age: 'age',
        email: 'email',
        mobile_number: 'phone number',
      })) {
        if (!String(form[key] || '').trim()) return `Please fill in ${label}`
      }
      const ageNum = Number(form.age)
      if (!Number.isFinite(ageNum) || ageNum < 18 || ageNum > 120) {
        return 'Age must be a number between 18 and 120'
      }
      if (!/^\d{11}$/.test(form.mobile_number) && !/^03\d{9}$/.test(form.mobile_number)) {
        if (!/^\d{10,11}$/.test(form.mobile_number)) {
          return 'Phone number must be 10–11 digits'
        }
      }
      return null
    }

    if (index === 1) {
      for (const [key, label] of Object.entries({
        cnic_full_name: 'full name (as on CNIC)',
        father_name: 'father name',
        cnic_number: 'CNIC number',
        date_of_birth: 'date of birth',
        cnic_issue_date: 'issue date',
        cnic_expiry_date: 'expiry date',
        country_to_stay: 'country to stay',
        gender: 'gender',
      })) {
        if (!String(form[key] || '').trim()) return `Please fill in ${label}`
      }
      if (!/^\d{5}-\d{7}-\d$/.test(form.cnic_number.trim())) {
        return 'CNIC must be 13 digits (auto-formatted as XXXXX-XXXXXXX-X)'
      }
      for (const [key, label] of [
        ['date_of_birth', 'Date of Birth'],
        ['cnic_issue_date', 'Date of Issuance'],
        ['cnic_expiry_date', 'Date of Expiry'],
      ]) {
        if (!isValidDateDMY(form[key])) {
          return `${label} must be a valid date in DD/MM/YYYY`
        }
      }
      return null
    }

    if (index === 2) {
      for (const [key, label] of Object.entries({
        company_name: 'company name',
        designation: 'designation',
        monthly_income: 'monthly salary',
        employee_id: 'employee ID',
      })) {
        if (!String(form[key] || '').trim()) return `Please fill in ${label}`
      }
      if (!/^\d+$/.test(form.monthly_income)) {
        return 'Monthly salary must be numbers only'
      }
      return null
    }

    if (index === 3) {
      if (!String(form.branch_code || '').trim()) return 'Please select a branch'
      return null
    }

    if (index === 4) {
      for (const [key, label] of FILE_FIELDS) {
        if (!files[key]) return `Please upload ${label}`
      }
      if (cnicChecking) return 'Please wait — Cognexa AI is verifying CNIC against your upload…'
      if (cnicVerified !== true) {
        return cnicCheckMsg
          || 'Please upload a clear CNIC front so we can verify it matches your entered CNIC.'
      }
      return null
    }
    return null
  }

  async function verifyCnicUpload(frontFile, backFile = null) {
    if (!frontFile) return
    if (!/^\d{5}-\d{7}-\d$/.test(form.cnic_number.trim())) {
      setCnicVerified(false)
      setCnicCheckMsg('Enter a valid CNIC on the Identity step before uploading.')
      setError(true)
      setStatus('Enter a valid CNIC on the Identity step before uploading.')
      return
    }

    setCnicChecking(true)
    setCnicCheckMsg('Cognexa AI is checking CNIC against uploaded document…')
    setError(false)
    setStatus('')
    try {
      const body = new FormData()
      body.append('cnic_number', form.cnic_number.trim())
      body.append('cnic_front', frontFile)
      if (backFile) body.append('cnic_back', backFile)

      const data = await api('/api/v1/cnic/verify', { method: 'POST', body })
      setCnicVerified(Boolean(data.match))
      setCnicCheckMsg(data.message || '')
      if (!data.match) {
        setError(true)
        setStatus(data.message || 'CNIC does not match the uploaded document.')
      } else {
        setError(false)
        setStatus(data.message || 'CNIC matched.')
      }
    } catch (err) {
      setCnicVerified(false)
      setCnicCheckMsg(err.message || 'CNIC verification failed.')
      setError(true)
      setStatus(err.message || 'CNIC verification failed.')
    } finally {
      setCnicChecking(false)
    }
  }

  async function onFileChange(key, file) {
    setFiles((prev) => {
      const next = { ...prev, [key]: file || null }
      return next
    })

    if (key === 'cnic_front') {
      setCnicVerified(null)
      setCnicCheckMsg('')
      if (file) {
        // Use current back file if already selected
        await verifyCnicUpload(file, files.cnic_back || null)
      }
    }

    if (key === 'cnic_back' && files.cnic_front && cnicVerified !== true) {
      await verifyCnicUpload(files.cnic_front, file)
    }
  }

  function confirmStep() {
    const message = validateStep(step)
    if (message) {
      setStatus(message)
      setError(true)
      return
    }
    if (step < STEPS.length - 1) goToStep(step + 1)
  }

  function backStep() {
    if (step > 0) goToStep(step - 1)
  }

  async function onSubmit(event) {
    event.preventDefault()
    const message = validateStep(4)
    if (message) {
      setStatus(message)
      setError(true)
      return
    }
    setBusy(true)
    setError(false)
    setStatus('Submitting application…')
    try {
      const body = new FormData()
      Object.entries(form).forEach(([key, value]) => body.append(key, String(value).trim()))
      FILE_FIELDS.forEach(([key]) => body.append(key, files[key]))
      const data = await api('/api/v1/applications', { method: 'POST', body })
      setResult(data)
      setStatus('')
      setForm(EMPTY)
      setFiles({})
      setCnicVerified(null)
      setCnicCheckMsg('')
      setStep(0)
      setAnimKey((k) => k + 1)
    } catch (err) {
      setError(true)
      setStatus(err.message || 'Submission failed')
    } finally {
      setBusy(false)
    }
  }

  function startNew() {
    setResult(null)
    setForm(EMPTY)
    setFiles({})
    setStep(0)
    setStatus('')
    setError(false)
    setCnicVerified(null)
    setCnicCheckMsg('')
    setAnimKey((k) => k + 1)
  }

  return (
    <div className="ubl-app">
      <header className="ubl-appbar">
        <div className="ubl-appbar-left">
          <img src="/ubl-logo.png" alt="UBL" className="ubl-appbar-logo" />
          <p className="ubl-appbar-title">
            You&apos;re applying for <strong>UBL Account</strong>
          </p>
        </div>
        <div className="ubl-appbar-right">
          <span className="ubl-secure">
            <span className="ubl-lock" aria-hidden="true" />
            Your details are secure
          </span>
          <span className="ubl-appbar-divider" aria-hidden="true" />
          <Link className="ubl-appbar-link" to="/branch/login">Branch</Link>
        </div>
      </header>

      {result ? (
        <main className="ubl-stage">
          <section className="ubl-card ubl-success" key={animKey}>
            <div className="ubl-orbit" aria-hidden="true" />
            <p className="ubl-q">Application received</p>
            <h1>Submission confirmed</h1>
            <p className="ubl-sub">{result.message}</p>
            <div className="ubl-ref">{result.application_id}</div>
            <p className="ubl-sub">
              Sent to <strong>{result.branch?.name || 'your branch'}</strong> for review.
            </p>
            <div className="ubl-actions">
              <button type="button" className="btn" onClick={startNew}>
                Submit another application
              </button>
            </div>
          </section>
        </main>
      ) : (
        <>
          <nav className="ubl-stepper" aria-label="Application progress">
            {STEPS.map((item, index) => {
              const state = index < step ? 'done' : index === step ? 'active' : 'todo'
              return (
                <div key={item.id} className="ubl-step-wrap">
                  <button
                    type="button"
                    className={`ubl-step ${state}`}
                    disabled={index > step}
                    onClick={() => index < step && goToStep(index)}
                    aria-current={index === step ? 'step' : undefined}
                  >
                    <span className="ubl-step-num">
                      {index < step ? '✓' : index + 1}
                    </span>
                    <span className="ubl-step-label">{item.label}</span>
                  </button>
                  {index < STEPS.length - 1 ? (
                    <span className="ubl-step-chevron" aria-hidden="true">›</span>
                  ) : null}
                </div>
              )
            })}
          </nav>

          <main className="ubl-stage">
            <form className="ubl-card" onSubmit={onSubmit} key={animKey}>
              <p className="ubl-q">
                Question <strong>{step + 1}</strong> / {STEPS.length}
              </p>
              <h1>{STEPS[step].title}</h1>
              <p className="ubl-sub">{STEPS[step].hint}</p>

              {step === 0 && (
                <div className="ubl-fields">
                  <label className="ubl-field">
                    <span>Full name</span>
                    <input value={form.full_name} onChange={(e) => updateField('full_name', e.target.value)} placeholder="Your full name" />
                  </label>
                  <label className="ubl-field">
                    <span>Age</span>
                    <input value={form.age} onChange={(e) => updateField('age', e.target.value)} placeholder="28" inputMode="numeric" />
                  </label>
                  <label className="ubl-field">
                    <span>Email</span>
                    <input type="email" value={form.email} onChange={(e) => updateField('email', e.target.value)} placeholder="name@example.com" />
                  </label>
                  <label className="ubl-field">
                    <span>Phone number</span>
                    <input value={form.mobile_number} onChange={(e) => updateField('mobile_number', e.target.value)} placeholder="03XXXXXXXXX" inputMode="numeric" />
                  </label>
                </div>
              )}

              {step === 1 && (
                <div className="ubl-fields">
                  <label className="ubl-field">
                    <span>Full name (as on CNIC)</span>
                    <input value={form.cnic_full_name} onChange={(e) => updateField('cnic_full_name', e.target.value)} placeholder="Exactly as printed" />
                  </label>
                  <label className="ubl-field">
                    <span>Father name</span>
                    <input value={form.father_name} onChange={(e) => updateField('father_name', e.target.value)} placeholder="Father's name" />
                  </label>
                  <label className="ubl-field">
                    <span>Identity Card Number</span>
                    <input
                      value={form.cnic_number}
                      onChange={(e) => updateField('cnic_number', e.target.value)}
                      placeholder="XXXXX-XXXXXXX-X"
                      inputMode="numeric"
                      autoComplete="off"
                    />
                  </label>
                  <label className="ubl-field">
                    <span>Date of Birth</span>
                    <input
                      value={form.date_of_birth}
                      onChange={(e) => updateField('date_of_birth', e.target.value)}
                      placeholder="DD/MM/YYYY"
                      inputMode="numeric"
                      autoComplete="off"
                    />
                  </label>
                  <label className="ubl-field">
                    <span>Identity Card Date of Issuance</span>
                    <input
                      value={form.cnic_issue_date}
                      onChange={(e) => updateField('cnic_issue_date', e.target.value)}
                      placeholder="DD/MM/YYYY"
                      inputMode="numeric"
                      autoComplete="off"
                    />
                  </label>
                  <label className="ubl-field">
                    <span>Identity Card Date of Expiry</span>
                    <input
                      value={form.cnic_expiry_date}
                      onChange={(e) => updateField('cnic_expiry_date', e.target.value)}
                      placeholder="DD/MM/YYYY"
                      inputMode="numeric"
                      autoComplete="off"
                    />
                  </label>
                  <label className="ubl-field">
                    <span>Country to stay</span>
                    <input value={form.country_to_stay} onChange={(e) => updateField('country_to_stay', e.target.value)} placeholder="e.g. Pakistan" />
                  </label>
                  <label className="ubl-field">
                    <span>Gender</span>
                    <select value={form.gender} onChange={(e) => updateField('gender', e.target.value)}>
                      <option value="">Select gender</option>
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                      <option value="Other">Other</option>
                    </select>
                  </label>
                </div>
              )}

              {step === 2 && (
                <div className="ubl-fields">
                  <label className="ubl-field">
                    <span>Company name</span>
                    <input value={form.company_name} onChange={(e) => updateField('company_name', e.target.value)} placeholder="Company name" />
                  </label>
                  <label className="ubl-field">
                    <span>Designation</span>
                    <input value={form.designation} onChange={(e) => updateField('designation', e.target.value)} placeholder="e.g. Software Engineer" />
                  </label>
                  <label className="ubl-field">
                    <span>Monthly salary</span>
                    <input
                      value={form.monthly_income}
                      onChange={(e) => updateField('monthly_income', e.target.value)}
                      placeholder="150000"
                      inputMode="numeric"
                    />
                  </label>
                  <label className="ubl-field">
                    <span>Employee ID</span>
                    <input value={form.employee_id} onChange={(e) => updateField('employee_id', e.target.value)} placeholder="Employee ID" />
                  </label>
                </div>
              )}

              {step === 3 && (
                <div className="ubl-fields">
                  <label className="ubl-field full">
                    <span>Branch</span>
                    <select value={form.branch_code} onChange={(e) => updateField('branch_code', e.target.value)}>
                      <option value="">Select a branch</option>
                      {BRANCHES.map((b) => (
                        <option key={b.code} value={b.code}>{b.name}</option>
                      ))}
                    </select>
                  </label>
                </div>
              )}

              {step === 4 && (
                <>
                  <div className="ubl-uploads">
                    {FILE_FIELDS.map(([key, label, hint]) => (
                      <label className="ubl-upload" key={key}>
                        <strong>{label}</strong>
                        <span>{hint}</span>
                        <input
                          type="file"
                          accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp,.webp"
                          onChange={(e) => onFileChange(key, e.target.files?.[0] || null)}
                        />
                        <em>{fileNames[key]}</em>
                      </label>
                    ))}
                  </div>
                  {(cnicChecking || cnicCheckMsg) && (
                    <p
                      className={`ubl-cnic-check ${
                        cnicChecking ? 'pending' : cnicVerified ? 'ok' : 'bad'
                      }`}
                    >
                      {cnicChecking ? 'Cognexa AI is verifying CNIC against document…' : cnicCheckMsg}
                    </p>
                  )}
                </>
              )}

              <div className="ubl-actions">
                {step > 0 ? (
                  <button type="button" className="btn btn-secondary" onClick={backStep}>
                    Back
                  </button>
                ) : (
                  <span />
                )}

                {step < STEPS.length - 1 ? (
                  <button type="button" className="btn" onClick={confirmStep}>
                    Continue
                  </button>
                ) : (
                  <button className="btn" type="submit" disabled={busy || cnicChecking || cnicVerified !== true}>
                    {busy ? 'Submitting…' : cnicChecking ? 'Verifying…' : 'Submit application'}
                  </button>
                )}
              </div>

              {status ? (
                <AlertBanner
                  type={error ? 'error' : cnicVerified === true ? 'success' : 'info'}
                  title={error ? 'Something went wrong' : cnicVerified === true ? 'CNIC verified' : 'Status'}
                  message={status}
                />
              ) : null}
            </form>
          </main>
        </>
      )}
    </div>
  )
}
