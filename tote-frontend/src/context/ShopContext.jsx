// Cart, wishlist and recently-viewed state.
// Guests keep a local cart; once signed in, the cart lives on the server and the guest cart is merged into it.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { SHIPPING } from '../lib/format'
import { useAuth } from './AuthContext'
import { useToast } from './ToastContext'

const ShopContext = createContext(null)
const GUEST_CART = 'tote.guestCart'
const GUEST_RECENT = 'tote.guestRecent'

const readLocal = (k) => { try { return JSON.parse(localStorage.getItem(k)) || [] } catch { return [] } }
const writeLocal = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* storage unavailable */ } }

function guestSummary(lines) {
  const items = lines.map((l) => ({ product: l.product, quantity: l.quantity, line_total: l.product.price * l.quantity, stock_ok: l.quantity <= l.product.stock }))
  const subtotal = items.reduce((s, i) => s + i.line_total, 0)
  const shipping = items.length ? (subtotal >= SHIPPING.freeOver ? 0 : SHIPPING.flat) : 0
  return { items, subtotal, shipping, total: subtotal + shipping, count: items.reduce((s, i) => s + i.quantity, 0), issues: [] }
}

export function ShopProvider({ children }) {
  const { user, ready } = useAuth()
  const toast = useToast()
  const [cart, setCart] = useState(guestSummary(readLocal(GUEST_CART)))
  const [cartLoading, setCartLoading] = useState(false)
  // Whose server cart is loaded: a page opened directly (e.g. a reload on /checkout) waits for it.
  const [loadedFor, setLoadedFor] = useState(null)
  const [wishlist, setWishlist] = useState([])
  const [recent, setRecent] = useState(readLocal(GUEST_RECENT))

  // Load (and merge) the server cart when someone signs in.
  useEffect(() => {
    if (!ready) return
    if (!user) {
      setCart(guestSummary(readLocal(GUEST_CART)))
      setWishlist([])
      setRecent(readLocal(GUEST_RECENT))
      setLoadedFor(null)
      return
    }
    setCartLoading(true)
    const guest = readLocal(GUEST_CART)
    const load = guest.length
      ? api('/api/me/cart/merge', { method: 'POST', body: { items: guest.map((l) => ({ product_id: l.product.id, quantity: l.quantity })) } })
      : api('/api/me/cart')
    load.then((c) => { setCart(c); writeLocal(GUEST_CART, []) })
      .catch((e) => toast(e.message, 'error'))
      .finally(() => { setCartLoading(false); setLoadedFor(user.id) })
    api('/api/me/wishlist').then(setWishlist).catch(() => {})
    api('/api/me/recent').then(setRecent).catch(() => {})
  }, [user, ready, toast])

  const setQty = useCallback(async (product, quantity) => {
    if (quantity > product.stock) {
      toast(`Only ${product.stock} of ${product.name} in stock.`, 'error')
      return false
    }
    if (!user) {
      const lines = readLocal(GUEST_CART).filter((l) => l.product.id !== product.id)
      if (quantity > 0) lines.push({ product, quantity })
      writeLocal(GUEST_CART, lines)
      setCart(guestSummary(lines))
      return true
    }
    try {
      setCart(await api(`/api/me/cart/${product.id}`, { method: 'PUT', body: { quantity } }))
      return true
    } catch (e) {
      toast(e.message, 'error')
      return false
    }
  }, [user, toast])

  const add = useCallback(async (product, qty = 1) => {
    const current = cart.items.find((i) => i.product.id === product.id)?.quantity || 0
    const ok = await setQty(product, current + qty)
    if (ok) toast(`${product.name} added to your bag`)
    return ok
  }, [cart, setQty, toast])

  const refreshCart = useCallback(async () => {
    if (user) setCart(await api('/api/me/cart'))
    else { writeLocal(GUEST_CART, []); setCart(guestSummary([])) }
  }, [user])

  const inWishlist = useCallback((id) => wishlist.some((p) => p.id === id), [wishlist])
  const toggleWish = useCallback(async (product) => {
    if (!user) return false
    const has = wishlist.some((p) => p.id === product.id)
    try {
      await api(`/api/me/wishlist/${product.id}`, { method: has ? 'DELETE' : 'POST' })
      setWishlist(has ? wishlist.filter((p) => p.id !== product.id) : [product, ...wishlist])
      toast(has ? 'Removed from your wishlist' : 'Saved to your wishlist')
    } catch (e) { toast(e.message, 'error') }
    return true
  }, [user, wishlist, toast])

  const viewed = useCallback((product) => {
    if (user) {
      api(`/api/me/recent/${product.id}`, { method: 'POST' }).catch(() => {})
      setRecent((r) => [product, ...r.filter((p) => p.id !== product.id)].slice(0, 8))
    } else {
      const next = [product, ...readLocal(GUEST_RECENT).filter((p) => p.id !== product.id)].slice(0, 8)
      writeLocal(GUEST_RECENT, next)
      setRecent(next)
    }
  }, [user])

  const waitingForUserCart = !!user && loadedFor !== user.id
  const value = useMemo(() => ({ cart, cartLoading: cartLoading || waitingForUserCart, add, setQty, refreshCart, wishlist, inWishlist, toggleWish, recent, viewed }),
    [cart, cartLoading, waitingForUserCart, add, setQty, refreshCart, wishlist, inWishlist, toggleWish, recent, viewed])
  return <ShopContext.Provider value={value}>{children}</ShopContext.Provider>
}

export const useShop = () => useContext(ShopContext)
