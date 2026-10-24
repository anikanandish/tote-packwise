import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export function Logo({ light }) {
  return (
    <span className={`logo ${light ? 'logo-light' : ''}`}>
      <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden><path d="M5 11 16 5.5 27 11v11L16 27.5 5 22z" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" /><path d="M5 11l11 5.5L27 11M16 16.5v11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" /></svg>
      PackWise
    </span>
  )
}

export default function Shell() {
  const { session, isAdmin, logout } = useAuth()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const name = session?.user?.name
  useEffect(() => {
    const closeOnEscape = (event) => { if (event.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [])
  const toggleNavigation = () => {
    if (window.matchMedia('(max-width: 900px)').matches) setOpen((value) => !value)
    else setCollapsed((value) => !value)
  }
  const mobile = window.matchMedia('(max-width: 900px)').matches
  return (
    <div className={`shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className={`side ${open ? 'open' : ''}`}>
        <Link to="/queue" className="side-logo" onClick={() => setOpen(false)}><Logo light /></Link>
        <nav onClick={() => setOpen(false)}>
          <p className="side-group">Packing</p>
          <NavLink to="/queue">Order queue</NavLink>
          <NavLink to="/simulate">Algorithm simulator</NavLink>
          {isAdmin && (<>
            <p className="side-group">Admin</p>
            <NavLink to="/admin">Admin console ↗</NavLink>
          </>)}
        </nav>
        <div className="side-user">
          <p><strong>{name}</strong><br /><span>{isAdmin ? 'Administrator' : 'Warehouse worker'}</span></p>
          <button className="btn btn-quiet-dark" onClick={async () => { await logout(); nav(isAdmin ? '/admin/login' : '/') }}>Sign out</button>
        </div>
      </aside>
      {open && <button className="side-scrim" aria-label="Close navigation" onClick={() => setOpen(false)} />}
      <div className="main">
        <header className="topbar">
          <button className="icon-btn burger" onClick={toggleNavigation}
            aria-label={mobile ? (open ? 'Close navigation' : 'Open navigation') : (collapsed ? 'Expand navigation' : 'Collapse navigation')}
            aria-expanded={mobile ? open : !collapsed}>☰</button>
          <span className="topbar-who">{name} · {isAdmin ? 'admin' : 'worker'}</span>
        </header>
        <Outlet />
      </div>
    </div>
  )
}
