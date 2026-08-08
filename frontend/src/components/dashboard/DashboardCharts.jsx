import { useEffect, useRef, useState } from 'react'

/* ── color palette ── */
const STATUS_META = {
  pending:   { color: '#f59e0b', glow: 'rgba(245,158,11,0.3)',  bg: '#fffbeb', label: 'Pending' },
  analyzing: { color: '#06b6d4', glow: 'rgba(6,182,212,0.3)',   bg: '#ecfeff', label: 'Analyzing' },
  completed: { color: '#3b82f6', glow: 'rgba(59,130,246,0.3)',  bg: '#eff6ff', label: 'Ready' },
  accepted:  { color: '#10b981', glow: 'rgba(16,185,129,0.3)',  bg: '#ecfdf5', label: 'Accepted' },
  rejected:  { color: '#ef4444', glow: 'rgba(239,68,68,0.3)',   bg: '#fef2f2', label: 'Rejected' },
}

/* ── animated counting number ── */
function CountUp({ value, duration = 900 }) {
  const [n, setN] = useState(0)
  const target = Number(value) || 0
  useEffect(() => {
    if (target === 0) { setN(0); return }
    const start = performance.now()
    let frame
    const tick = (now) => {
      const p = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - p, 3)
      setN(Math.round(target * eased))
      if (p < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, duration])
  return <>{n}</>
}

/* ── animated donut ── */
function DonutChart({ segments, size = 180, selected, onSelect }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1
  const r = 62, cx = size / 2, cy = size / 2
  const circ = 2 * Math.PI * r
  let offset = 0

  const arcs = segments.filter(s => s.value > 0).map(seg => {
    const pct  = seg.value / total
    const dash = pct * circ
    const gap  = circ - dash
    const el = (
      <circle
        key={seg.key}
        cx={cx} cy={cy} r={r}
        fill="none"
        stroke={seg.color}
        strokeWidth={selected === seg.key ? 16 : 13}
        strokeDasharray={`${dash} ${gap}`}
        strokeDashoffset={-offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`}
        style={{ transition: 'stroke-dasharray 0.7s cubic-bezier(0.22,1,0.36,1), stroke-width 0.2s ease', cursor: 'pointer', filter: selected === seg.key ? `drop-shadow(0 0 6px ${seg.color})` : 'none' }}
        onClick={() => onSelect(selected === seg.key ? null : seg.key)}
      />
    )
    offset += dash
    return el
  })

  const sel = selected ? segments.find(s => s.key === selected) : null

  return (
    <div className="chart-donut-wrap">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(99,102,241,0.07)" strokeWidth={13} />
        {arcs}
      </svg>
      <div className="chart-donut-center">
        <strong style={{ color: sel ? sel.color : undefined }}>
          <CountUp value={sel ? sel.value : total} />
        </strong>
        <span>{sel ? sel.label : 'Total'}</span>
      </div>
    </div>
  )
}

/* ── gradient bar chart ── */
function GradientBars({ items, maxHeight = 160 }) {
  const max = Math.max(...items.map(i => i.value), 1)
  return (
    <div className="chart-bars" role="img" aria-label="Application status bar chart">
      {items.map(item => (
        <div key={item.key} className="chart-bar-col">
          <div className="chart-bar-track" style={{ height: maxHeight }}>
            <div
              className="chart-bar-fill"
              style={{
                height: `${Math.max((item.value / max) * 100, item.value > 0 ? 6 : 0)}%`,
                background: `linear-gradient(180deg, ${item.color} 0%, ${item.color}aa 100%)`,
                boxShadow: item.value > 0 ? `0 -4px 12px ${item.glow}` : 'none',
              }}
              title={`${item.label}: ${item.value}`}
            />
          </div>
          <span className="chart-bar-value" style={{ color: item.value > 0 ? item.color : undefined }}>
            {item.value}
          </span>
          <span className="chart-bar-label">{item.label}</span>
        </div>
      ))}
    </div>
  )
}

/* ── acceptance ring ── */
function AcceptanceRing({ rate, size = 120 }) {
  const r = 46, circ = 2 * Math.PI * r
  const dash = Math.max((rate / 100) * circ, 0)
  const color = rate >= 70 ? '#10b981' : rate >= 40 ? '#f59e0b' : '#ef4444'

  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(99,102,241,0.08)" strokeWidth={10} />
        <circle
          cx={size/2} cy={size/2} r={r}
          fill="none" stroke={color} strokeWidth={10}
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${size/2} ${size/2})`}
          style={{ transition: 'stroke-dasharray 1s cubic-bezier(0.22,1,0.36,1)', filter: `drop-shadow(0 0 5px ${color})` }}
        />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <strong style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color, lineHeight: 1, letterSpacing: '-0.03em' }}>
          {rate}%
        </strong>
        <span style={{ fontSize: '0.58rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)', marginTop: '0.2rem' }}>Accept</span>
      </div>
    </div>
  )
}

/* ── main export ── */
export default function DashboardCharts({ counts = {}, acceptanceRate = 0 }) {
  const [selected, setSelected] = useState(null)

  const keys = ['pending', 'analyzing', 'completed', 'accepted', 'rejected']
  const segments = keys.map(key => ({
    key,
    value: Number(counts[key]) || 0,
    ...STATUS_META[key],
  }))

  const active  = (Number(counts.pending) || 0) + (Number(counts.analyzing) || 0)
  const decided = (Number(counts.accepted) || 0) + (Number(counts.rejected) || 0)

  return (
    <section className="dash-charts-panel panel">
      <div className="panel-head">
        <div>
          <h2 style={{ margin: '0 0 0.2rem', fontFamily: 'var(--font-display)', fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Pipeline analytics
          </h2>
          <p className="hint">Live breakdown of application status across your branch.</p>
        </div>
        <div className="chart-kpi-strip">
          <div className="chart-kpi">
            <span className="chart-kpi-label">In queue</span>
            <strong className="chart-kpi-value tone-amber"><CountUp value={active} /></strong>
          </div>
          <div className="chart-kpi">
            <span className="chart-kpi-label">Decided</span>
            <strong className="chart-kpi-value tone-blue"><CountUp value={decided} /></strong>
          </div>
          <div className="chart-kpi" style={{ minWidth: 110 }}>
            <span className="chart-kpi-label">Accept rate</span>
            <strong className="chart-kpi-value tone-green">{acceptanceRate}%</strong>
          </div>
        </div>
      </div>

      <div className="dash-charts-grid">
        {/* Donut + legend */}
        <div className="chart-card chart-card-donut">
          <h3 className="chart-card-title">Status distribution</h3>
          <DonutChart segments={segments} selected={selected} onSelect={setSelected} />
          <ul className="chart-legend">
            {segments.map(s => (
              <li
                key={s.key}
                style={{ cursor: 'pointer', background: selected === s.key ? s.bg : undefined }}
                onClick={() => setSelected(selected === s.key ? null : s.key)}
              >
                <span className="chart-legend-dot" style={{ background: s.color, boxShadow: selected === s.key ? `0 0 8px ${s.color}` : 'none' }} />
                <span style={{ fontWeight: selected === s.key ? 700 : 500 }}>{s.label}</span>
                <strong style={{ color: s.color }}>{s.value}</strong>
              </li>
            ))}
          </ul>
        </div>

        {/* Bar chart + acceptance ring */}
        <div className="chart-card chart-card-bars" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem' }}>
            <div style={{ flex: 1 }}>
              <h3 className="chart-card-title">Volume by status</h3>
              <GradientBars items={segments} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.35rem', paddingTop: '2.25rem' }}>
              <AcceptanceRing rate={acceptanceRate} />
              <span style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>Rate</span>
            </div>
          </div>

          {/* Progress bars per status */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {segments.map(s => {
              const totalSum = segments.reduce((a, x) => a + x.value, 0)
              const pct = totalSum === 0 ? 0 : Math.round((s.value / totalSum) * 100)
              return (
                <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', width: '5.5rem', flexShrink: 0 }}>{s.label}</span>
                  <div style={{ flex: 1, height: '7px', borderRadius: '999px', background: 'rgba(99,102,241,0.07)', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%',
                      width: `${pct}%`,
                      borderRadius: '999px',
                      background: s.color,
                      boxShadow: `0 0 6px ${s.glow}`,
                      transition: 'width 0.9s cubic-bezier(0.22,1,0.36,1)',
                    }} />
                  </div>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: s.color, width: '2.5rem', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{pct}%</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}
