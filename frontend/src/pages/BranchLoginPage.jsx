import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import BrandHeader from '../components/BrandHeader.jsx'
import MeshBackdrop from '../components/MeshBackdrop.jsx'
import AlertBanner from '../components/ui/AlertBanner.jsx'
import Button from '../components/ui/Button.jsx'
import FormField from '../components/ui/FormField.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'

export default function BranchLoginPage() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/api/v1/auth/me')
      .then(() => navigate('/branch', { replace: true }))
      .catch(() => {})
  }, [navigate])

  async function onSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      navigate('/branch')
    } catch (err) {
      setError(err.message || 'Login failed. Check your username and password.')
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

        <PageHeader
          eyebrow="Secure access"
          title="Branch sign in"
          badge="Cognexa Console"
          description="Sign in to Cognexa Verification System — queue, scan, review, and decide with a full audit trail for your branch."
        />

        <form className="panel login-card login-card-v2" onSubmit={onSubmit}>
          <h2>Operator credentials</h2>
          <p className="hint">Authorized branch users only. Sessions are protected.</p>

          {error ? (
            <AlertBanner type="error" title="Sign in failed" message={error} />
          ) : null}

          <div className="grid">
            <FormField label="Username" htmlFor="branch-username" required full>
              <input
                id="branch-username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your branch username"
                required
              />
            </FormField>
            <FormField label="Password" htmlFor="branch-password" required full>
              <input
                id="branch-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                required
              />
            </FormField>
          </div>

          <div className="actions">
            <Button type="submit" loading={busy} size="lg">
              {busy ? 'Signing in…' : 'Enter workspace'}
            </Button>
          </div>

          <AlertBanner
            type="info"
            title="Cognexa AI analysis queue"
            message="Customer submissions are analyzed in a serial queue. Live status updates appear in your branch dashboard after sign in."
          />
        </form>
      </div>
    </MeshBackdrop>
  )
}
