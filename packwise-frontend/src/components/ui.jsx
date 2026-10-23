import { useEffect } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ORDER_STATUS, PLAN_STATUS } from '../lib/format'

export function Loading({ label = 'Loading' }) {
  return <div className="state"><span className="spinner" aria-hidden />{label}…</div>
}

export function ErrorBox({ error, retry }) {
  if (!error) return null
  const offline = error.status === 503
  return (
    <div className={`errorbox ${offline ? 'offline' : ''}`} role="alert">
      <strong>{offline ? 'Packing engine offline' : error.status === 0 ? 'API not reachable' : 'Something needs attention'}</strong>
      <p>{error.message}</p>
      {error.data?.detail?.reasons?.length > 0 && <ul>{error.data.detail.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
      {error.data?.detail?.missing?.length > 0 && <ul>{error.data.detail.missing.map((r, i) => <li key={i}>{r}</li>)}</ul>}
      {retry && <button className="btn btn-quiet" onClick={retry}>Try again</button>}
    </div>
  )
}

export function Empty({ title, children, action }) {
  return <div className="empty"><h3>{title}</h3>{children && <p>{children}</p>}{action}</div>
}

export function Stat({ label, value, note, tone }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ''}`}>
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {note && <p className="stat-note">{note}</p>}
    </div>
  )
}

export function OrderBadge({ status }) {
  return <span className={`badge b-${status}`}>{ORDER_STATUS[status] || status}</span>
}
export function PlanBadge({ status }) {
  return <span className={`badge p-${status}`}>{PLAN_STATUS[status] || status}</span>
}

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const on = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [onClose])
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal-card ${wide ? 'wide' : ''}`}>
        <div className="modal-head"><h2>{title}</h2><button className="icon-btn" onClick={onClose} aria-label="Close">×</button></div>
        {children}
      </div>
    </div>
  )
}

export function Field({ label, children, error, hint }) {
  return (
    <label className={`field ${error ? 'has-error' : ''}`}>
      <span>{label}</span>{children}
      {hint && !error && <small>{hint}</small>}
      {error && <small className="err">{error}</small>}
    </label>
  )
}

export function RequireStaff({ children, admin }) {
  const { session, ready } = useAuth()
  const loc = useLocation()
  if (!ready) return <Loading />
  if (!session) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname)}`} replace />
  if (admin && session.role !== 'admin') return <div className="pagepad"><Empty title="Admins only">Your worker session cannot open admin pages. Ask a supervisor to sign in.</Empty></div>
  return children
}

// Very small SVG bar chart. Only renders bars for real data points.
export function Bars({ data, x, y, format = (v) => v, height = 160 }) {
  if (!data?.length) return <p className="muted">No completed orders yet, so there is nothing to chart.</p>
  const max = Math.max(...data.map((d) => d[y])) || 1
  const bw = 100 / Math.max(data.length, 6)
  return (
    <div className="bars">
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" style={{ height }} aria-hidden>
        {data.map((d, i) => {
          const h = (d[y] / max) * (height - 4)
          return <rect key={i} x={i * bw + bw * 0.18} width={bw * 0.64} y={height - h} height={h} rx="0.6" className="bar" />
        })}
      </svg>
      <div className="bars-labels" style={{ width: `${(data.length / Math.max(data.length, 6)) * 100}%` }}>{data.map((d, i) => <span key={i} style={{ width: `${100 / data.length}%` }}><b>{format(d[y])}</b>{d[x]}</span>)}</div>
    </div>
  )
}

// Confirmation step built into the page (browser confirm() dialogs are not used).
export function Confirm({ title, children, confirmLabel = 'Confirm', danger = false, busy = false, error, onConfirm, onClose }) {
  return (
    <Modal title={title} onClose={onClose}>
      <div className="confirm-body">{children}</div>
      {error && <ErrorBox error={error} />}
      <div className="modal-actions">
        <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
        <button type="button" className={`btn ${danger ? 'btn-danger' : 'btn-ink'}`} disabled={busy} onClick={onConfirm}>{busy ? 'Working…' : confirmLabel}</button>
      </div>
    </Modal>
  )
}

// Small label that marks how trustworthy a value is: calculated, estimate, sample, not verified…
export function Tag({ kind = 'info', children, title }) {
  return <span className={`tag tag-${kind}`} title={title}>{children}</span>
}
