import { useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Field, Loading } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useShop } from '../context/ShopContext'
import { useToast } from '../context/ToastContext'
import { api, fieldErrors } from '../lib/api'
import { money } from '../lib/format'

// Checkout autofill: the details of the last order placed in this browser are filled in again,
// and "Fill sample details" fills a clearly fake demo address for quick demos.
const SAVED_KEY = (user) => `tote.checkout.${user?.id ?? user?.email ?? 'guest'}`
const SAMPLE = { phone: '9876543210', line1: '12 MG Road', line2: 'Demo building, 2nd floor', city: 'Bengaluru',
  state: 'Karnataka', postal_code: '560001' }
const FIELDS = ['name', 'email', 'phone', 'line1', 'line2', 'city', 'state', 'postal_code']
function readSaved(user) {
  try { return JSON.parse(localStorage.getItem(SAVED_KEY(user))) || null } catch { return null }
}
function saveDetails(user, f, method) {
  try { localStorage.setItem(SAVED_KEY(user), JSON.stringify({ ...Object.fromEntries(FIELDS.map((k) => [k, f[k]])), method })) } catch { /* ignore */ }
}

export default function Checkout() {
  const { user } = useAuth()
  const { cart, cartLoading, refreshCart } = useShop()
  const toast = useToast()
  const nav = useNavigate()
  const saved = readSaved(user)
  const [f, setF] = useState(() => ({ name: user.name, email: user.email, phone: '', line1: '', line2: '', city: '', state: '',
    postal_code: '', ...(saved ? Object.fromEntries(FIELDS.filter((k) => saved[k]).map((k) => [k, saved[k]])) : {}) }))
  const [method, setMethod] = useState(saved?.method || 'card')
  const [confirm, setConfirm] = useState(!!saved)
  const fillSample = () => { setF({ ...f, ...SAMPLE, name: f.name || user.name, email: f.email || user.email }); setConfirm(true); setErrors({}) }
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState('')
  const placed = useRef(false)
  // One key per checkout attempt: a double click or a retry after a network error never creates a second order.
  const idemKey = useRef(globalThis.crypto?.randomUUID?.() || `chk-${Date.now()}-${Math.random().toString(36).slice(2)}`)

  if (cartLoading) return <Loading />
  if (!cart.items.length && !placed.current) return <Navigate to="/cart" replace />

  const up = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    setErrors({}); setFormError('')
    if (!confirm) { setErrors({ confirm_simulated: 'Tick this box to place the simulated order' }); return }
    setBusy(true)
    try {
      const order = await api('/api/orders/checkout', {
        method: 'POST',
        headers: { 'Idempotency-Key': idemKey.current },
        body: {
          contact: { name: f.name, email: f.email, phone: f.phone },
          address: { line1: f.line1, line2: f.line2, city: f.city, state: f.state, postal_code: f.postal_code, country: 'India' },
          payment: { method, confirm_simulated: confirm },
        },
      })
      placed.current = true
      saveDetails(user, f, method)
      nav(`/order/${order.code}?placed=1`, { replace: true })
      refreshCart().catch(() => {})
    } catch (err) {
      setErrors(fieldErrors(err))
      setFormError(err.message)
      toast(err.message, 'error')
    } finally { setBusy(false) }
  }

  return (
    <div className="page checkout">
      <h1>Checkout</h1>
      <form className="checkout-grid" onSubmit={submit} noValidate>
        <div className="checkout-form">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
            <button type="button" className="btn btn-ghost" onClick={fillSample}>Fill sample details</button>
            {saved && <span className="muted">Filled in from your last order.</span>}
          </div>
          <fieldset>
            <legend>Contact</legend>
            <Field label="Full name" error={errors.name}><input className="input" value={f.name} onChange={up('name')} autoComplete="name" required /></Field>
            <div className="two">
              <Field label="Email" error={errors.email}><input className="input" type="email" value={f.email} onChange={up('email')} autoComplete="email" required /></Field>
              <Field label="Phone" error={errors.phone}><input className="input" value={f.phone} onChange={up('phone')} autoComplete="tel" inputMode="tel" required /></Field>
            </div>
          </fieldset>
          <fieldset>
            <legend>Delivery address</legend>
            <Field label="Address" error={errors.line1}><input className="input" value={f.line1} onChange={up('line1')} autoComplete="address-line1" required /></Field>
            <Field label="Apartment, floor (optional)" error={errors.line2}><input className="input" value={f.line2} onChange={up('line2')} autoComplete="address-line2" /></Field>
            <div className="three">
              <Field label="City" error={errors.city}><input className="input" value={f.city} onChange={up('city')} autoComplete="address-level2" required /></Field>
              <Field label="State" error={errors.state}><input className="input" value={f.state} onChange={up('state')} autoComplete="address-level1" required /></Field>
              <Field label="PIN code" error={errors.postal_code}><input className="input" value={f.postal_code} onChange={up('postal_code')} autoComplete="postal-code" inputMode="numeric" required /></Field>
            </div>
          </fieldset>
          <fieldset>
            <legend>Payment</legend>
            <div className="notice">This is a demonstration store. Payment is <strong>simulated</strong>: no card details are collected and no money is charged.</div>
            <div className="pay-options" role="radiogroup">
              {[['card', 'Card (simulated)'], ['upi', 'UPI (simulated)'], ['cod', 'Cash on delivery (simulated)']].map(([v, l]) => (
                <label key={v} className={`pay ${method === v ? 'on' : ''}`}>
                  <input type="radio" name="pay" value={v} checked={method === v} onChange={() => setMethod(v)} />{l}
                </label>
              ))}
            </div>
            <label className={`checkbox ${errors.confirm_simulated ? 'has-error' : ''}`}>
              <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
              I understand this payment is simulated and no money will be charged.
            </label>
            {errors.confirm_simulated && <p className="field-error">{errors.confirm_simulated}</p>}
          </fieldset>
          {formError && <p className="field-error" role="alert">{formError}</p>}
        </div>

        <aside className="summary">
          <h2>Order summary</h2>
          <ul className="sum-lines">
            {cart.items.map((i) => (
              <li key={i.product.id}><span>{i.product.name} <span className="muted">× {i.quantity}</span></span><span>{money(i.line_total)}</span></li>
            ))}
          </ul>
          <dl>
            <div><dt>Subtotal</dt><dd>{money(cart.subtotal)}</dd></div>
            <div><dt>Delivery</dt><dd>{cart.shipping ? money(cart.shipping) : 'Free'}</dd></div>
            <div className="summary-total"><dt>Total</dt><dd>{money(cart.total)}</dd></div>
          </dl>
          <button className="btn btn-wine btn-block" disabled={busy}>{busy ? 'Placing order…' : `Place order · ${money(cart.total)}`}</button>
          <Link to="/cart" className="link-u small">Edit bag</Link>
        </aside>
      </form>
    </div>
  )
}
