import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import BrandHeader from '../components/BrandHeader.jsx'
import MeshBackdrop from '../components/MeshBackdrop.jsx'

export default function BranchLoginPage() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/api/v1/auth/me')
      .then(() => navigate('/branch', { replace: true }))
      .catch(() => {})
  }, [navigate])

  async function onSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setStatus('Authenticating…')
    try {
      await api('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      navigate('/branch')
    } catch (err) {
      setStatus(err.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <MeshBackdrop>
      <div className="shell narrow login-stage">
        <BrandHeader
          variant="bar"
          subtitle="Branch operations"
          actionTo="/"
          actionLabel="Customer portal"
          rightSlot={<span className="ai-badge">Staff access</span>}
        />

        <section className="hero">
          <span className="ai-badge">Secure access</span>
          <h1>Branch sign in</h1>
          <p>
            Sign in to Application Verification System (AVS) — queue, scan, review, and decide
            with a clear audit trail for your branch.
          </p>
        </section>

        <form className="panel login-card" onSubmit={onSubmit}>
          <h2>Operator credentials</h2>
          <p className="hint">Authorized branch users only. Sessions are protected.</p>
          <div className="grid">
            <label className="field full">Username
              <input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </label>
            <label className="field full">Password
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
          </div>
          <div className="actions">
            <button className="btn" type="submit" disabled={busy}>
              {busy ? 'Signing in…' : 'Enter workspace'}
            </button>
            <p className={`status-line ${status && status !== 'Authenticating…' ? 'error' : ''}`}>
              {status}
            </p>
          </div>
          <p className="login-side-note">
            AI analysis runs in a serial queue after each customer submission. Live status
            updates appear in your branch workspace.
          </p>
        </form>
      </div>
    </MeshBackdrop>
  )
}
