import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Logo } from '../components/Shell'
import { Field } from '../components/ui'
import { useAuth } from '../context/AuthContext'

// Warehouse worker sign-in. Administrators use the separate admin console at /admin/login.
export default function Login() {
  const { session, workerLogin } = useAuth()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const [f, setF] = useState({ name: '', code: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (session) return <Navigate to={params.get('next') || (session.role === 'admin' ? '/admin' : '/queue')} replace />
  const up = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      if (f.name.trim().length < 2) throw new Error('Enter your name so your work is recorded against it.')
      await workerLogin(f.name.trim(), f.code.trim())
      nav(params.get('next') || '/queue', { replace: true })
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <div className="login">
      <Link to="/" className="login-logo"><Logo light /></Link>
      <form className="login-card" onSubmit={submit}>
        <h1>Start your shift</h1>
        <p className="muted">Use the shared code from your supervisor. It is checked by the server.</p>
        <Field label="Your name"><input className="input" value={f.name} onChange={up('name')} autoComplete="name" /></Field>
        <Field label="Worker code"><input className="input input-code" value={f.code} onChange={up('code')} autoComplete="off" spellCheck="false" /></Field>
        {error && <p className="err" role="alert">{error}</p>}
        <button className="btn btn-peach btn-block btn-lg" disabled={busy}>{busy ? 'Checking…' : 'Open the queue'}</button>
      </form>
      <Link to="/admin/login" className="login-alt">Administrator? Open the admin console →</Link>
    </div>
  )
}
