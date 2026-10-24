// Small fetch wrapper for the FastAPI backend.
const localApi = ['localhost', '127.0.0.1'].includes(window.location.hostname) ? 'http://localhost:8000' : ''
export const API_URL = (import.meta.env.VITE_API_URL || localApi).replace(/\/$/, '')
const TOKEN_KEY = 'tote.token'

export const tokenStore = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ } },
}

export class ApiError extends Error {
  constructor(status, message, data) {
    super(message)
    this.status = status
    this.data = data
  }
}

function messageFrom(data, status) {
  if (!data) return `Request failed (${status})`
  if (typeof data.detail === 'string') return data.detail
  if (data.detail && typeof data.detail === 'object') return data.detail.message || 'Request failed'
  return `Request failed (${status})`
}

export async function api(path, { method = 'GET', body, auth = true, headers: extra = {} } = {}) {
  const headers = { Accept: 'application/json', ...extra }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = tokenStore.get()
  if (auth && token) headers.Authorization = `Bearer ${token}`
  let res
  try {
    res = await fetch(API_URL + path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  } catch {
    throw new ApiError(0, `Cannot reach the TOTE server at ${API_URL}. Check that the backend is running.`)
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, messageFrom(data, res.status), data)
  return data
}

export function fieldErrors(err) {
  const out = {}
  for (const e of err?.data?.errors || []) out[e.field.split('.').pop()] = e.message
  return out
}
