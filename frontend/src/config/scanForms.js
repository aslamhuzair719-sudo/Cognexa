export const DOCUMENT_TYPES = [
  { value: 'remittance_slip', label: 'Remittance' },
  { value: 'cnic', label: 'CNIC' },
  { value: 'payslip', label: 'Pay Slip' },
]

export const REMITTANCE_TEXT_FIELDS = [
  { key: 'date', label: 'Date' },
  { key: 'applicant_name', label: 'Applicant Name' },
  { key: 'father_name', label: "Father's Name" },
  { key: 'cnic', label: 'CNIC' },
  { key: 'mobile', label: 'Mobile' },
  { key: 'beneficiary_name', label: 'Beneficiary Name' },
  { key: 'beneficiary_account', label: 'Beneficiary Account' },
  { key: 'amount_figures', label: 'Amount (Figures)' },
  { key: 'amount_words', label: 'Amount (Words)' },
  { key: 'branch_code', label: 'Branch Code' },
  { key: 'occupation', label: 'Occupation' },
]

export const REMITTANCE_CHECKBOXES = [
  { key: 'non_account_holder', label: 'Non Account Holder' },
  { key: 'cash_transfer', label: 'Cash Transfer' },
  { key: 'cashiers_cheque', label: "Cashier's Cheque" },
  { key: 'online_transfer', label: 'Online Transfer' },
  { key: 'currency_pkr', label: 'Currency PKR' },
]

export const CNIC_TEXT_FIELDS = [
  { key: 'name', label: 'Name' },
  { key: 'father_name', label: "Father's Name" },
  { key: 'gender', label: 'Gender' },
  { key: 'country_to_stay', label: 'Country to Stay' },
  { key: 'cnic_number', label: 'Identity Number / CNIC Number' },
  { key: 'date_of_birth', label: 'Date of Birth' },
  { key: 'issue_date', label: 'Date of Issuance' },
  { key: 'expiry_date', label: 'Date of Expiry' },
]

export const PAYSLIP_FIELD_GROUPS = [
  { id: 'identity', title: 'Employee & Employer' },
  { id: 'period', title: 'Pay Period' },
  { id: 'pay', title: 'Compensation' },
  { id: 'contact', title: 'Contact' },
  { id: 'authenticity', title: 'Document Authenticity' },
]

export const PAYSLIP_TEXT_FIELDS = [
  { key: 'company_name', label: 'Company Name', group: 'identity' },
  { key: 'employee_name', label: 'Employee Name', group: 'identity' },
  { key: 'employee_id', label: 'Employee ID', group: 'identity' },
  { key: 'designation', label: 'Designation', group: 'identity' },
  { key: 'department', label: 'Department', group: 'identity' },
  { key: 'employment_status', label: 'Employment Status', group: 'identity' },
  { key: 'payslip_period', label: 'Payslip Period', group: 'period', full: true },
  { key: 'period_start', label: 'Period Start', group: 'period' },
  { key: 'period_end', label: 'Period End', group: 'period' },
  { key: 'payment_date', label: 'Payment Date', group: 'period' },
  { key: 'payslip_date', label: 'Payslip Date', group: 'period' },
  { key: 'payslip_number', label: 'Payslip Number', group: 'period' },
  { key: 'basic_salary', label: 'Basic Salary', group: 'pay' },
  { key: 'gross_salary', label: 'Gross Salary', group: 'pay' },
  { key: 'overtime', label: 'Overtime', group: 'pay' },
  { key: 'deductions', label: 'Deductions', group: 'pay' },
  { key: 'net_pay', label: 'Net Pay', group: 'pay' },
  { key: 'net_salary', label: 'Net Salary', group: 'pay' },
  { key: 'email', label: 'Email', group: 'contact' },
  { key: 'phone', label: 'Phone', group: 'contact' },
  { key: 'validity_status', label: 'Validity Status', group: 'authenticity' },
  { key: 'validity_score', label: 'Validity Score', group: 'authenticity' },
  { key: 'validity_reason', label: 'Validity Reason', group: 'authenticity', full: true },
]

export const BANK_STATEMENT_TEXT_FIELDS = [
  { key: 'account_title', label: 'Account Title' },
  { key: 'account_number', label: 'Account Number' },
  { key: 'iban', label: 'IBAN' },
  { key: 'currency', label: 'Currency' },
  { key: 'from_date', label: 'From Date' },
  { key: 'to_date', label: 'To Date' },
  { key: 'address', label: 'Address', full: true },
]

const FORM_CONFIG = {
  remittance_slip: {
    mode: 'remittance',
    textFields: REMITTANCE_TEXT_FIELDS,
    checkboxes: REMITTANCE_CHECKBOXES,
    pipeline: 'remittance_llm_vision',
  },
  cnic: {
    mode: 'cnic',
    textFields: CNIC_TEXT_FIELDS,
    checkboxes: [],
    pipeline: 'document_llm',
  },
  payslip: {
    mode: 'payslip',
    textFields: PAYSLIP_TEXT_FIELDS,
    checkboxes: [],
    pipeline: 'document_llm',
  },
  bank_statement: {
    mode: 'bank_statement',
    textFields: BANK_STATEMENT_TEXT_FIELDS,
    checkboxes: [],
    pipeline: 'document_llm',
  },
}

export function docTypeLabel(value) {
  return DOCUMENT_TYPES.find((t) => t.value === value)?.label || value
}

export function isStructuredDocType(docType) {
  return Boolean(FORM_CONFIG[docType])
}

export function resolveFormMode(docType, pipeline = '') {
  const config = FORM_CONFIG[docType]
  if (config) return config.mode
  if (pipeline === 'remittance_llm_vision') return 'remittance'
  if (pipeline === 'document_llm') return docType
  return null
}

export function emptyFieldsForDocType(docType) {
  const config = FORM_CONFIG[docType]
  if (!config) return {}
  const fields = Object.fromEntries(config.textFields.map(({ key }) => [key, '']))
  if (config.checkboxes.length) {
    for (const { key } of config.checkboxes) fields[key] = false
  }
  return fields
}

const PAYSLIP_ALIASES = {
  employee_email: 'email',
  employee_phone: 'phone',
  company_email: 'email',
  company_phone: 'phone',
  pay_period_start: 'period_start',
  pay_period_end: 'period_end',
  pay_period: 'payslip_period',
  gross_pay_current: 'gross_salary',
  gross_pay: 'gross_salary',
  net_pay_current: 'net_pay',
  total_deduction_current: 'deductions',
  overtime_amount_current: 'overtime',
  overtime_pay: 'overtime',
}

function applyPayslipAliases(source, fields) {
  for (const [from, to] of Object.entries(PAYSLIP_ALIASES)) {
    const raw = source[from]
    if (!fields[to] && raw != null && String(raw).trim()) {
      fields[to] = String(raw)
    }
  }
  if (!fields.payslip_period && (fields.period_start || fields.period_end)) {
    fields.payslip_period = [fields.period_start, fields.period_end].filter(Boolean).join(' - ')
  }
  if (!fields.net_salary && fields.net_pay) fields.net_salary = fields.net_pay
  if (!fields.net_pay && fields.net_salary) fields.net_pay = fields.net_salary
  if (!fields.designation && source.department) fields.designation = String(source.department)
  return fields
}

export function buildFormFromResult(data, selectedDocType) {
  const docType = String(selectedDocType || '').trim()
  const pipeline = String(data?.pipeline || '')
  const mode = resolveFormMode(docType, pipeline)
  const config = FORM_CONFIG[docType]
  const hasFields = data?.fields && typeof data.fields === 'object'

  if (hasFields && config) {
    const fields = Object.fromEntries(config.textFields.map(({ key }) => [key, '']))
    for (const { key } of config.textFields) {
      const value = data.fields[key]
      fields[key] = value == null ? '' : String(value)
    }
    if (docType === 'payslip') applyPayslipAliases(data.fields, fields)
    const checkboxes = {}
    if (config.checkboxes.length) {
      const sourceChecks = data.checkboxes || data.fields || {}
      for (const { key } of config.checkboxes) {
        checkboxes[key] = Boolean(sourceChecks[key])
      }
    }
    return { mode: config.mode, fields, checkboxes, transactions: data.transactions || [] }
  }

  const keyFields = data?.summary?.key_fields || {}
  const fields = {}
  for (const [key, value] of Object.entries(keyFields)) {
    if (typeof value === 'boolean') {
      fields[key] = value ? 'true' : 'false'
    } else if (value != null && value !== '' && value !== 'null') {
      fields[key] = String(value)
    } else {
      fields[key] = ''
    }
  }
  return { mode: 'generic', fields, checkboxes: {}, transactions: [] }
}

export function buildDraftKeyFields(formMode, fields, checkboxes) {
  if (formMode === 'remittance') {
    return {
      amount: fields.amount_figures || null,
      date: fields.date || null,
      parties: fields.beneficiary_name || null,
      bank: 'UBL',
      payment_cash: Boolean(checkboxes.cash_transfer),
      payment_cheque: Boolean(checkboxes.cashiers_cheque),
      checked_options: Object.entries(checkboxes)
        .filter(([, v]) => v)
        .map(([k]) => k)
        .join(', ') || null,
    }
  }
  if (formMode === 'cnic') {
    return {
      parties: fields.name || null,
      reference_number: fields.cnic_number || null,
      date: fields.date_of_birth || null,
      ...fields,
    }
  }
  if (formMode === 'payslip') {
    return {
      parties: fields.employee_name || null,
      amount: fields.net_pay || fields.gross_salary || null,
      date: fields.payment_date || fields.payslip_date || fields.payslip_period || null,
      reference_number: fields.payslip_number || fields.employee_id || null,
      ...fields,
    }
  }
  if (formMode === 'bank_statement') {
    return {
      parties: fields.account_title || null,
      amount: fields.ending_balance || null,
      date: fields.from_date && fields.to_date
        ? `${fields.from_date} - ${fields.to_date}`
        : fields.from_date || fields.to_date || null,
      ...fields,
    }
  }
  return { ...fields }
}

export function customerNameGuess(fields, formMode) {
  if (formMode === 'cnic') return fields.name || ''
  if (formMode === 'payslip') return fields.employee_name || ''
  if (formMode === 'bank_statement') return fields.account_title || ''
  if (formMode === 'remittance') {
    return fields.applicant_name || fields.beneficiary_name || ''
  }
  return fields.applicant_name || fields.beneficiary_name || fields.parties || ''
}

export function getFieldGroupsForMode(mode) {
  if (mode === 'payslip') return PAYSLIP_FIELD_GROUPS
  return []
}

export function getTextFieldsForMode(mode) {
  if (mode === 'remittance') return REMITTANCE_TEXT_FIELDS
  if (mode === 'cnic') return CNIC_TEXT_FIELDS
  if (mode === 'payslip') return PAYSLIP_TEXT_FIELDS
  if (mode === 'bank_statement') return BANK_STATEMENT_TEXT_FIELDS
  return []
}

export function getCheckboxesForMode(mode) {
  if (mode === 'remittance') return REMITTANCE_CHECKBOXES
  return []
}
