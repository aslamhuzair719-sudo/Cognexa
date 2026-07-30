import { Link } from 'react-router-dom'

export default function BrandHeader({
  subtitle = '',
  actionTo,
  actionLabel,
  rightSlot,
  variant = 'light', // light | bar
}) {
  const isBar = variant === 'bar'
  return (
    <header className={`topbar ${isBar ? 'topbar-bar' : 'topbar-light'}`}>
      <div className="brand">
        <img
          src="/ubl-logo.png"
          alt="UBL"
          className={`ubl-logo ${isBar ? 'ubl-logo-on-bar' : 'ubl-logo-on-light'}`}
        />
        <div className="brand-text">
          <p className="brand-product">Application Verification System</p>
          <p className="brand-product-abbr">AVS</p>
          {subtitle ? <p className="brand-sub">{subtitle}</p> : null}
        </div>
      </div>
      <div className="topbar-right">
        {rightSlot}
        {actionTo && actionLabel ? (
          <Link className="nav-chip" to={actionTo}>{actionLabel}</Link>
        ) : null}
      </div>
    </header>
  )
}
