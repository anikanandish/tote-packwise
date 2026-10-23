import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { RequireAuth } from './components/ui'
import { AuthPage, NotFound, Wishlist } from './pages/Account'
import Cart from './pages/Cart'
import Checkout from './pages/Checkout'
import Home from './pages/Home'
import { OrderList, OrderTrack } from './pages/Orders'
import Product from './pages/Product'
import Shop from './pages/Shop'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="shop" element={<Shop />} />
        <Route path="product/:slug" element={<Product />} />
        <Route path="cart" element={<Cart />} />
        <Route path="checkout" element={<RequireAuth><Checkout /></RequireAuth>} />
        <Route path="orders" element={<RequireAuth><OrderList /></RequireAuth>} />
        <Route path="order/:code" element={<RequireAuth><OrderTrack /></RequireAuth>} />
        <Route path="wishlist" element={<Wishlist />} />
        <Route path="login" element={<AuthPage mode="login" />} />
        <Route path="register" element={<AuthPage mode="register" />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
