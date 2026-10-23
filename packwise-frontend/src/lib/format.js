const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const money = (n) => (n == null ? 'Unavailable' : inr.format(n))
export const signedMoney = (n) => (n == null ? 'Unavailable' : (n < 0 ? '−' : '') + inr.format(Math.abs(n)))
export const pct = (n) => (n == null ? '—' : `${(n * 100).toFixed(1)}%`)
export const cm = (n) => (n == null ? '—' : `${Number(n).toFixed(1)}`)
export const dims = (a) => a.map((v) => Number(v).toFixed(1)).join(' × ') + ' cm'
export const vol = (n) => (n == null ? '—' : n >= 1000 ? `${(n / 1000).toFixed(2)} L` : `${Math.round(n)} cm³`)
export const kg = (g) => (g == null ? '—' : g >= 1000 ? `${(g / 1000).toFixed(2)} kg` : `${g} g`)
export const when = (iso) => iso ? new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '—'

export const ORDER_STATUS = {
  placed: 'Placed', awaiting_packing: 'Awaiting packing', packing_in_progress: 'Packing in progress',
  packed: 'Packed', ready_for_dispatch: 'Ready for dispatch', dispatched: 'Dispatched',
}
export const PLAN_STATUS = {
  recommended: 'Recommended', accepted: 'Accepted · stock reserved', completed: 'Completed',
  cancelled: 'Cancelled', superseded: 'Superseded', no_fit: 'No carton fits',
}
export const ACTION_LABEL = {
  recommended: 'Recommendation made', no_fit: 'No carton fits', accepted: 'Plan accepted', cancelled: 'Plan cancelled',
  completed: 'Packing completed', override: 'Worker override', superseded: 'Plan superseded',
  recommendation_failed: 'Engine unavailable', accept_failed: 'Reservation failed', override_rejected: 'Override rejected',
  status_change: 'Order status changed', created: 'Created', updated: 'Updated', stock_adjusted: 'Stock adjusted',
  priority_set: 'Marked priority', priority_cleared: 'Priority cleared', worker_login: 'Worker signed in',
  worker_login_failed: 'Worker sign-in failed', seed_demo_order: 'Demo order seeded',
  admin_login: 'Admin signed in', admin_login_failed: 'Admin sign-in failed', deleted: 'Deleted',
  retire_legacy_cartons: 'Old cartons retired', retire_six_box_cartons: 'Six-box cartons retired',
}
export const mm3 = (a) => (a ? a.join(' × ') + ' mm' : '—')
export const litres = (cm3) => (cm3 == null ? '—' : `${(cm3 / 1000).toFixed(cm3 < 10000 ? 2 : 1)} L`)
export const dateOnly = (iso) => iso ? new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
