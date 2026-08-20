import { useEffect, useState } from 'react'

export function formatEtaSeconds(seconds) {
  const value = Math.max(0, Math.ceil(Number(seconds) || 0))
  if (value <= 0) return null
  if (value < 60) return `~${value}s`
  const minutes = Math.floor(value / 60)
  const rest = value % 60
  if (minutes < 60) {
    return rest ? `~${minutes} min ${rest}s` : `~${minutes} min`
  }
  const hours = Math.floor(minutes / 60)
  const remainMinutes = minutes % 60
  return remainMinutes ? `~${hours}h ${remainMinutes} min` : `~${hours}h`
}

export default function QueueEta({ eta, syncedAt, compact = false }) {
  const [left, setLeft] = useState(eta?.eta_seconds ?? null)

  useEffect(() => {
    setLeft(eta?.eta_seconds ?? null)
  }, [eta?.eta_seconds, eta?.state, eta?.position, eta?.eta_kind, syncedAt])

  useEffect(() => {
    if (eta?.eta_seconds == null) return undefined
    const timer = setInterval(() => {
      setLeft((value) => (typeof value === 'number' ? Math.max(0, value - 1) : value))
    }, 1000)
    return () => clearInterval(timer)
  }, [eta?.eta_seconds, eta?.state, syncedAt])

  if (!eta || left == null) return null

  const remainingKind = eta.eta_kind === 'remaining'
  const formatted = formatEtaSeconds(left)
  let text
  if (!formatted) {
    text = remainingKind ? 'Finishing…' : 'Starting soon'
  } else if (compact) {
    text = remainingKind ? `${formatted} left` : formatted
  } else if (remainingKind) {
    text = `About ${formatted.replace('~', '')} remaining`
  } else {
    text = `Starts in ${formatted.replace('~', '')}`
  }

  return (
    <span className={`queue-eta${compact ? ' compact' : ''}${remainingKind ? ' remaining' : ' until-start'}`}>
      {text}
    </span>
  )
}
