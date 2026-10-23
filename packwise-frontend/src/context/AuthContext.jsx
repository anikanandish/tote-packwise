import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, tokenStore } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null) // { role, user }
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!tokenStore.get()) { setReady(true); return }
    api('/api/auth/me')
      .then((d) => (d.role === 'worker' || d.role === 'admin') ? setSession(d) : tokenStore.set(null))
      .catch(() => tokenStore.set(null))
      .finally(() => setReady(true))
  }, [])

  const workerLogin = useCallback(async (worker_name, code) => {
    const d = await api('/api/auth/worker', { method: 'POST', body: { worker_name, code }, auth: false })
    tokenStore.set(d.token); setSession({ role: d.role, user: d.user })
  }, [])
  // Admin console: the access code is sent once to the server, which checks it and returns a session token.
  const adminLogin = useCallback(async (code) => {
    const d = await api('/api/auth/admin', { method: 'POST', body: { code }, auth: false })
    tokenStore.set(d.token); setSession({ role: d.role, user: d.user })
  }, [])
  const logout = useCallback(async () => {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {})
    tokenStore.set(null); setSession(null)
  }, [])

  return <AuthContext.Provider value={{ session, ready, workerLogin, adminLogin, logout,
    isAdmin: session?.role === 'admin' }}>{children}</AuthContext.Provider>
}
export const useAuth = () => useContext(AuthContext)
