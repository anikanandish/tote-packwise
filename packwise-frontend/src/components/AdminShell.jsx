// Layout for the admin console: its own navigation, separate from the worker screens.
import { useState } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Logo } from './Shell'
import { Loading } from './ui'

const NAV = [
  ['Operations', [['/admin', 'Overview', true], ['/admin/orders', 'Orders'], ['/admin/history', 'Packing results']]],
  ['Catalogue', [['/admin/cartons', 'Cartons'], ['/admin/products', 'Products'], ['/admin/materials', 'Protective materials']]],
  ['Insight', [['/admin/reports', 'Reports & sustainability'], ['/admin/settings', 'Settings']]],
]

export function RequireAdmin({ children }) {
  const { session, ready } = useAuth()
  const loc = useLocation()
  if (!ready) return <Loading />
  if (!session || session.role !== 'admin') return <Navigate to={`/admin/login?next=${encodeURIComponent(loc.pathname)}`} replace />
  return children
}

export default function AdminShell() {
  const { logout } = useAuth()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  return (
    <div className="shell admin-shell">
      <aside className={`side ${open ? 'open' : ''}`}>
        <Link to="/admin" className="side-logo" onClick={() => setOpen(false)}><Logo light /><span className="admin-chip">Admin</span></Link>
        <nav onClick={() => setOpen(false)}>
          {NAV.map(([group, links]) => (
            <div key={group}>
              <p className="side-group">{group}</p>
              {links.map(([to, label, end]) => <NavLink key={to} to={to} end={end}>{label}</NavLink>)}
            </div>
          ))}
          <p className="side-group">Warehouse</p>
          <NavLink to="/queue">Worker queue ↗</NavLink>
        </nav>
        <div className="side-user">
          <p><strong>Administrator</strong><br /><span>Signed in with the admin code</span></p>
          {confirm ? (
            <div className="logout-confirm">
              <span>Sign out of the admin console?</span>
              <button className="btn btn-peach" onClick={async () => { await logout(); nav('/admin/login', { replace: true }) }}>Sign out</button>
              <button className="btn btn-quiet-dark" onClick={() => setConfirm(false)}>Stay</button>
            </div>
          ) : <button className="btn btn-quiet-dark" onClick={() => setConfirm(true)}>Sign out</button>}
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="icon-btn burger" onClick={() => setOpen(!open)} aria-label="Menu" aria-expanded={open}>≡</button>
          <span className="topbar-who">PackWise admin console</span>
        </header>
        <Outlet />
      </div>
    </div>
  )
}
