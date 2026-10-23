import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useShop } from '../context/ShopContext'
import { Icon } from './ui'

export const CATEGORIES = ['Beauty', 'Fashion', 'Electronics', 'Home & Living', 'Books & Stationery']

function Header() {
  const { user, logout } = useAuth()
  const { cart } = useShop()
  const nav = useNavigate()
  const loc = useLocation()
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => setOpen(false), [loc.pathname, loc.search])
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8)
    on()
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])

  const search = (e) => {
    e.preventDefault()
    nav(`/shop?q=${encodeURIComponent(q.trim())}`)
  }

  return (
    <header className={`hdr ${scrolled ? 'hdr-scrolled' : ''}`}>
      <div className="hdr-row">
        <button className="hdr-burger" onClick={() => setOpen(!open)} aria-label="Menu" aria-expanded={open}>
          {open ? <Icon.close /> : <Icon.menu />}
        </button>
        <Link to="/" className="wordmark" aria-label="TOTE home">TOTE</Link>
        <nav className={`hdr-nav ${open ? 'open' : ''}`} aria-label="Categories">
          <NavLink to="/shop" end>Shop all</NavLink>
          {CATEGORIES.map((c) => <NavLink key={c} to={`/shop?category=${encodeURIComponent(c)}`}>{c}</NavLink>)}
        </nav>
        <form className="hdr-search" onSubmit={search} role="search">
          <Icon.search aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search lipstick, candles, pens…" aria-label="Search products" />
        </form>
        <div className="hdr-actions">
          <Link to="/wishlist" aria-label="Wishlist"><Icon.heart /></Link>
          {user ? (
            <div className="hdr-user">
              <Link to="/orders" aria-label="Your orders"><Icon.user /><span className="hdr-user-name">{user.name.split(' ')[0]}</span></Link>
              <div className="hdr-menu">
                <Link to="/orders">Orders</Link>
                <Link to="/wishlist">Wishlist</Link>
                <button onClick={async () => { await logout(); nav('/') }}>Sign out</button>
              </div>
            </div>
          ) : (
            <Link to="/login" className="hdr-signin">Sign in</Link>
          )}
          <Link to="/cart" className="hdr-bag" aria-label={`Bag, ${cart.count} items`}>
            <Icon.bag />{cart.count > 0 && <span className="hdr-count">{cart.count}</span>}
          </Link>
        </div>
      </div>
    </header>
  )
}

function Footer() {
  return (
    <footer className="ftr">
      <div className="ftr-grid">
        <div>
          <p className="wordmark wordmark-lg">TOTE</p>
          <p className="ftr-lede">Fewer, better things — beauty, objects and tech, chosen slowly and packed with care.</p>
        </div>
        <div>
          <h4>Shop</h4>
          {CATEGORIES.map((c) => <Link key={c} to={`/shop?category=${encodeURIComponent(c)}`}>{c}</Link>)}
        </div>
        <div>
          <h4>Your account</h4>
          <Link to="/orders">Track an order</Link>
          <Link to="/wishlist">Wishlist</Link>
          <Link to="/cart">Bag</Link>
        </div>
        <div>
          <h4>Good to know</h4>
          <p className="muted">Free delivery on orders over ₹1,999. Every order is packed in the smallest carton that keeps it safe.</p>
        </div>
      </div>
      <p className="ftr-note">TOTE is a hackathon demonstration store. Payments are simulated and no money is ever charged. Reviews are demo content.</p>
    </footer>
  )
}

export default function Layout() {
  const loc = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [loc.pathname])
  return (
    <>
      <a href="#main" className="skip">Skip to content</a>
      <Header />
      <main id="main"><Outlet /></main>
      <Footer />
    </>
  )
}
