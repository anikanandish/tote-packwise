import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Logo } from '../../components/Shell'
import { Field } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'

export default function AdminLogin() {
  const { session, adminLogin } = useAuth()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const [code, setCode] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const next = params.get('next')?.startsWith('/admin') ? params.get('next') : '/admin'

  if (session?.role === 'admin') return <Navigate to={next} replace />

  const submit = async (e) => {
    e.preventDefault()
    setError(''); setBusy(true)
    try { await adminLogin(code.trim()); nav(next, { replace: true }) }
    catch (err) { setError(err.message); setCode('') }
    finally { setBusy(false) }
  }

  return (
    <div className="login admin-login">
      <div className="login-logo"><Logo light /><span className="admin-chip">Admin console</span></div>
      <form className="login-card" onSubmit={submit}>
        <h1>Admin access</h1>
        <p className="muted">Cartons, products, orders, packing results and reports. Enter the admin access code set on the server.</p>
        {session?.role === 'worker' && <p className="alert small">You are signed in as a worker. Entering the admin code switches this browser to an admin session.</p>}
        <Field label="Admin access code" hint="Set as ADMIN_ACCESS_CODE in backend/.env">
          <div className="code-row">
            <input className="input input-code" type={show ? 'text' : 'password'} value={code} onChange={(e) => setCode(e.target.value)}
              autoComplete="off" spellCheck="false" autoFocus />
            <button type="button" className="btn btn-quiet" onClick={() => setShow(!show)}>{show ? 'Hide' : 'Show'}</button>
          </div>
        </Field>
        {error && <p className="err" role="alert">{error}</p>}
        <button className="btn btn-ink btn-block btn-lg" disabled={busy || !code.trim()}>{busy ? 'Checking…' : 'Open admin console'}</button>
      </form>
      <Link to="/login" className="login-alt">Warehouse worker? Start your shift →</Link>
    </div>
  )
}
