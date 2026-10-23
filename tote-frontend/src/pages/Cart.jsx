import { Link, useNavigate } from 'react-router-dom'
import ProductArt from '../components/ProductArt'
import { Empty, Loading, Qty } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useShop } from '../context/ShopContext'
import { money, SHIPPING } from '../lib/format'

export default function Cart() {
  const { cart, cartLoading, setQty } = useShop()
  const { user } = useAuth()
  const nav = useNavigate()

  if (cartLoading) return <Loading label="Opening your bag" />
  if (!cart.items.length) {
    return <div className="page narrow"><Empty title="Your bag is empty" action={<Link to="/shop" className="btn btn-wine">Start shopping</Link>}>
      Pieces you add will stay here{user ? ' on any device you sign in from' : ' on this device'}.</Empty></div>
  }
  const blocked = cart.items.some((i) => !i.stock_ok)
  const toFree = SHIPPING.freeOver - cart.subtotal

  return (
    <div className="page cart">
      <h1>Your bag</h1>
      <div className="cart-grid">
        <ul className="cart-lines">
          {cart.items.map(({ product: p, quantity, line_total, stock_ok }) => (
            <li key={p.id} className="cart-line">
              <Link to={`/product/${p.slug}`} className="cart-thumb"><ProductArt product={p} /></Link>
              <div className="cart-info">
                <p className="pcard-brand">{p.brand}</p>
                <Link to={`/product/${p.slug}`} className="cart-name">{p.name}</Link>
                <p className="muted">{money(p.price)} each</p>
                {!stock_ok && <p className="field-error">Only {p.stock} left. Lower the quantity to continue.</p>}
                <div className="cart-ctrl">
                  <Qty value={quantity} onChange={(q) => setQty(p, q)} max={p.stock} />
                  <button className="link-u" onClick={() => setQty(p, 0)}>Remove</button>
                </div>
              </div>
              <p className="cart-total">{money(line_total)}</p>
            </li>
          ))}
        </ul>
        <aside className="summary">
          <h2>Summary</h2>
          <dl>
            <div><dt>Subtotal</dt><dd>{money(cart.subtotal)}</dd></div>
            <div><dt>Delivery</dt><dd>{cart.shipping ? money(cart.shipping) : 'Free'}</dd></div>
            <div className="summary-total"><dt>Total</dt><dd>{money(cart.total)}</dd></div>
          </dl>
          {toFree > 0 && <p className="muted small">Add {money(toFree)} more for free delivery.</p>}
          <button className="btn btn-wine btn-block" disabled={blocked}
            onClick={() => nav(user ? '/checkout' : '/login?next=/checkout')}>
            {user ? 'Continue to checkout' : 'Sign in to check out'}
          </button>
          <p className="muted small">Payment is simulated. No real money is charged.</p>
        </aside>
      </div>
    </div>
  )
}
