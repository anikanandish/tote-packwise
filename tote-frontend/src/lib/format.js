const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
export const money = (n) => (n == null ? '—' : inr.format(n))

export const date = (iso) =>
  new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })

export const STATUS_LABEL = {
  placed: 'Order placed',
  awaiting_packing: 'Awaiting packing',
  packing_in_progress: 'Packing in progress',
  packed: 'Packed',
  ready_for_dispatch: 'Ready for dispatch',
  dispatched: 'Dispatched',
}
export const STATUS_FLOW = Object.keys(STATUS_LABEL)

export const SHIPPING = { flat: 79, freeOver: 1999 }
