export function Skeleton({ className = '', style }) {
  return <div className={`skeleton ${className}`.trim()} style={style} aria-hidden />
}

export function DashboardSkeleton() {
  return (
    <div className="page-enter">
      <div className="skeleton skeleton-hero" />
      <div className="dash-grid">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton skeleton-dash-card" />
        ))}
      </div>
      <div className="split-panels">
        <div className="skeleton skeleton-panel" />
        <div className="skeleton skeleton-panel" />
      </div>
    </div>
  )
}

export function TableSkeleton({ rows = 5, cols = 6 }) {
  return (
    <div className="table-skeleton">
      <div className="table-skeleton-head">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="skeleton-cell" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="table-skeleton-row">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="skeleton-cell" />
          ))}
        </div>
      ))}
    </div>
  )
}
