// Small shared UI pieces.
import { Link, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export const Icon = {
  bag: (p) => <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M5 8h14l-1 13H6L5 8Z" /><path d="M9 8V6a3 3 0 0 1 6 0v2" /></svg>,
  heart: ({ filled, ...p }) => <svg viewBox="0 0 24 24" width="20" height="20" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.6" {...p}><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" /></svg>,
  user: (p) => <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" /></svg>,
  search: (p) => <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>,
  menu: (p) => <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M4 7h16M4 12h16M4 17h16" /></svg>,
  close: (p) => <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M6 6l12 12M18 6 6 18" /></svg>,
  check: (p) => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" {...p}><path d="m5 12 4 4 10-10" /></svg>,
}

export function Stars({ value, count }) {
  const pct = Math.max(0, Math.min(100, (value / 5) * 100))
  return (
    <span className="stars" aria-label={`Rated ${value} out of 5`}>
      <span className="stars-track">★★★★★<span className="stars-fill" style={{ width: `${pct}%` }}>★★★★★</span></span>
      <span className="stars-num">{value.toFixed(1)}{count != null && <span className="muted"> ({count})</span>}</span>
    </span>
  )
}

export function Qty({ value, onChange, max = 99, min = 1, disabled }) {
  return (
    <div className="qty" role="group" aria-label="Quantity">
      <button type="button" onClick={() => onChange(value - 1)} disabled={disabled || value <= min} aria-label="Decrease">−</button>
      <span aria-live="polite">{value}</span>
      <button type="button" onClick={() => onChange(value + 1)} disabled={disabled || value >= max} aria-label="Increase">+</button>
    </div>
  )
}

export function Loading({ label = 'Loading' }) {
  return <div className="state"><span className="spinner" aria-hidden />{label}…</div>
}

export function ErrorState({ error, retry }) {
  return (
    <div className="state state-error" role="alert">
      <p>{error?.message || String(error)}</p>
      {retry && <button className="btn btn-ghost" onClick={retry}>Try again</button>}
    </div>
  )
}

export function Empty({ title, children, action }) {
  return (
    <div className="state state-empty">
      <h3>{title}</h3>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  )
}

export function RequireAuth({ children, admin = false }) {
  const { user, ready } = useAuth()
  const loc = useLocation()
  if (!ready) return <Loading />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname)}`} replace />
  if (admin && user.role !== 'admin') {
    return <div className="page narrow"><Empty title="Admins only" action={<Link className="btn" to="/">Back to the shop</Link>}>This area needs an administrator account.</Empty></div>
  }
  return children
}

export function Field({ label, error, children, hint }) {
  return (
    <label className={`field ${error ? 'has-error' : ''}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && !error && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </label>
  )
}
