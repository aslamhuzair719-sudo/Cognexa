import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

const ToastContext = createContext(null)

const ICONS = {
  success: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  error: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 8v5m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  warning: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  info: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 16v-4m0-4h.01M22 12c0 5.523-4.477 10-10 10S2 17.523 2 12 6.477 2 12 2s10 4.477 10 10z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef(new Map())

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const toast = useCallback((options) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const entry = {
      id,
      type: options.type || 'info',
      title: options.title || '',
      message: options.message || '',
      action: options.action || null,
      duration: options.duration ?? 5000,
    }
    setToasts((prev) => [...prev, entry])
    if (entry.duration > 0) {
      const timer = setTimeout(() => dismiss(id), entry.duration)
      timers.current.set(id, timer)
    }
    return id
  }, [dismiss])

  const api = useMemo(() => ({
    toast,
    success: (title, message, opts = {}) => toast({ ...opts, type: 'success', title, message }),
    error: (title, message, opts = {}) => toast({ ...opts, type: 'error', title, message, duration: opts.duration ?? 7000 }),
    warning: (title, message, opts = {}) => toast({ ...opts, type: 'warning', title, message }),
    info: (title, message, opts = {}) => toast({ ...opts, type: 'info', title, message }),
    dismiss,
  }), [toast, dismiss])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-relevant="additions">
        {toasts.map((item) => (
          <div key={item.id} className={`toast toast-${item.type}`} role="status">
            <span className="toast-icon">{ICONS[item.type]}</span>
            <div className="toast-body">
              {item.title ? <strong className="toast-title">{item.title}</strong> : null}
              {item.message ? <p className="toast-message">{item.message}</p> : null}
              {item.action ? (
                <button type="button" className="toast-action" onClick={item.action.onClick}>
                  {item.action.label}
                </button>
              ) : null}
            </div>
            <button type="button" className="toast-close" onClick={() => dismiss(item.id)} aria-label="Dismiss">
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
