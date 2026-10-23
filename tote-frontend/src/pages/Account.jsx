import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import ProductCard from '../components/ProductCard'
import { Empty, Field, Loading } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useShop } from '../context/ShopContext'
import { fieldErrors } from '../lib/api'

export function AuthPage({ mode }) {
  const { user, login, register } = useAuth()
  const [params] = useSearchParams()
  const next = params.get('next') || '/'
  const nav = useNavigate()
  const [f, setF] = useState({ name: '', email: '', password: '' })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={next} replace />
  const isLogin = mode === 'login'
  const up = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setErrors({}); setFormError(''); setBusy(true)
    try {
      if (isLogin) await login(f.email, f.password)
      else await register(f.name, f.email, f.password)
      nav(next, { replace: true })
    } catch (err) {
      setErrors(fieldErrors(err)); setFormError(err.message)
    } finally { setBusy(false) }
  }

  return (
    <div className="page auth">
      <div className="auth-card">
        <h1>{isLogin ? 'Welcome back' : 'Create your account'}</h1>
        <p className="muted">{isLogin ? 'Sign in to check out, track orders and keep a wishlist.' : 'Your bag, wishlist and orders, saved across devices.'}</p>
        <form onSubmit={submit} noValidate>
          {!isLogin && <Field label="Name" error={errors.name}><input className="input" value={f.name} onChange={up('name')} autoComplete="name" /></Field>}
          <Field label="Email" error={errors.email}><input className="input" type="email" value={f.email} onChange={up('email')} autoComplete="email" /></Field>
          <Field label="Password" error={errors.password} hint={isLogin ? null : 'At least 8 characters'}>
            <input className="input" type="password" value={f.password} onChange={up('password')} autoComplete={isLogin ? 'current-password' : 'new-password'} />
          </Field>
          {formError && <p className="field-error" role="alert">{formError}</p>}
          <button className="btn btn-wine btn-block" disabled={busy}>{busy ? 'Please wait…' : isLogin ? 'Sign in' : 'Create account'}</button>
        </form>
        <p className="small">
          {isLogin ? <>New to TOTE? <Link className="link-u" to={`/register?next=${encodeURIComponent(next)}`}>Create an account</Link></>
            : <>Already have an account? <Link className="link-u" to={`/login?next=${encodeURIComponent(next)}`}>Sign in</Link></>}
        </p>
      </div>
    </div>
  )
}

export function Wishlist() {
  const { user, ready } = useAuth()
  const { wishlist } = useShop()
  if (!ready) return <Loading />
  if (!user) return (
    <div className="page narrow"><Empty title="Save pieces for later" action={<Link className="btn btn-wine" to="/login?next=/wishlist">Sign in</Link>}>
      Sign in to keep a wishlist on every device.</Empty></div>
  )
  return (
    <div className="page">
      <h1>Wishlist</h1>
      {!wishlist.length ? <Empty title="Nothing saved yet" action={<Link className="btn btn-line" to="/shop">Browse the shop</Link>}>Tap the heart on any piece to keep it here.</Empty>
        : <div className="pgrid">{wishlist.map((p) => <ProductCard key={p.id} product={p} />)}</div>}
    </div>
  )
}

export function NotFound() {
  return <div className="page narrow"><Empty title="This page has moved on" action={<Link className="btn btn-wine" to="/">Back to TOTE</Link>}>The link may be old or mistyped.</Empty></div>
}
