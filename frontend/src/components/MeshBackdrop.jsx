export default function MeshBackdrop({ children, variant = 'public' }) {
  return (
    <div className={`mesh-page mesh-${variant}`}>
      <div className="mesh-bg" aria-hidden="true" />
      <div className="mesh-veil" aria-hidden="true" />
      <div className="mesh-grid" aria-hidden="true" />
      <div className="mesh-content">{children}</div>
    </div>
  )
}
