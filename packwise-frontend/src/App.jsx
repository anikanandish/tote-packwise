import { Route, Routes } from 'react-router-dom'
import AdminShell, { RequireAdmin } from './components/AdminShell'
import Shell from './components/Shell'
import { Empty, RequireStaff } from './components/ui'
import AdminLogin from './pages/admin/AdminLogin'
import Cartons from './pages/admin/Cartons'
import Dashboard from './pages/admin/Dashboard'
import History from './pages/admin/History'
import Inventory from './pages/admin/Inventory'
import OrderDetail from './pages/admin/OrderDetail'
import Orders from './pages/admin/Orders'
import Products from './pages/admin/Products'
import { Reports, Settings } from './pages/admin/Reports'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Queue from './pages/Queue'
import Simulator from './pages/Simulator'
import Workspace from './pages/Workspace'

const notFound = <div className="pagepad"><Empty title="Page not found" /></div>

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/admin/login" element={<AdminLogin />} />
      {/* Warehouse worker screens */}
      <Route element={<RequireStaff><Shell /></RequireStaff>}>
        <Route path="/queue" element={<Queue />} />
        <Route path="/orders/:id" element={<Workspace />} />
        <Route path="/simulate" element={<Simulator />} />
      </Route>
      {/* Admin console (admin session only; every API call is checked again on the server) */}
      <Route path="/admin" element={<RequireAdmin><AdminShell /></RequireAdmin>}>
        <Route index element={<Dashboard />} />
        <Route path="orders" element={<Orders />} />
        <Route path="orders/:id" element={<OrderDetail />} />
        <Route path="history" element={<History />} />
        <Route path="cartons" element={<Cartons />} />
        <Route path="products" element={<Products />} />
        <Route path="materials" element={<Inventory type="material" />} />
        <Route path="reports" element={<Reports />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={notFound} />
      </Route>
      <Route path="*" element={notFound} />
    </Routes>
  )
}
