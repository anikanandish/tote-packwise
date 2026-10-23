import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, tokenStore } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!tokenStore.get()) { setReady(true); return }
    api('/api/auth/me')
      .then((d) => setUser(d.user))
      .catch(() => tokenStore.set(null))
      .finally(() => setReady(true))
  }, [])

  const finish = (d) => { tokenStore.set(d.token); setUser(d.user); return d.user }
  const login = useCallback((email, password) => api('/api/auth/login', { method: 'POST', body: { email, password }, auth: false }).then(finish), [])
  const register = useCallback((name, email, password) => api('/api/auth/register', { method: 'POST', body: { name, email, password }, auth: false }).then(finish), [])
  const logout = useCallback(async () => {
    try { await api('/api/auth/logout', { method: 'POST' }) } catch { /* session may already be gone */ }
    tokenStore.set(null)
    setUser(null)
  }, [])

  return <AuthContext.Provider value={{ user, ready, login, register, logout }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
