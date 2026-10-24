// Turns a stored packing plan into worker-friendly packing slides.
//
// Everything here is DERIVED from the C++ engine's placements (carton frame, cm):
//   x  along the carton length  -> shown to the worker as left (0) to right
//   y  along the carton width   -> shown as back (0) to front (your side)
//   dx, dy  padded slot footprint, dz padded height, z is always 0 (single layer)
// The worker stands at the front edge, so the carton's LENGTH side faces them.
// Nothing is invented: positions come from the slot edges and the neighbours that
// genuinely touch them in the engine's output.

const EPS = 0.05

export function shortName(name) {
  return name.replace(/\s+\d+(\.\d+)?\s?(ml|g|m)\b.*$/i, '').replace(/\s*\((.*)\)\s*$/, '')
}

const fmt = (n) => (Math.round(n * 10) / 10).toFixed(1).replace(/\.0$/, '')

function walls(p, L, W) {
  const w = []
  if (p.y <= EPS) w.push('back')
  if (p.y + p.dy >= W - EPS) w.push('front')
  if (p.x <= EPS) w.push('left')
  if (p.x + p.dx >= L - EPS) w.push('right')
  return w
}

const overlap = (a0, a1, b0, b1) => Math.min(a1, b1) - Math.max(a0, b0) > EPS

// Earlier placements whose edge touches this one.
function neighbours(p, earlier) {
  const out = []
  for (const q of earlier) {
    if (Math.abs(q.x + q.dx - p.x) <= EPS && overlap(p.y, p.y + p.dy, q.y, q.y + q.dy)) out.push({ rel: 'right of', q })
    else if (Math.abs(q.y + q.dy - p.y) <= EPS && overlap(p.x, p.x + p.dx, q.x, q.x + q.dx)) out.push({ rel: 'in front of', q })
  }
  return out
}

export function describePosition(p, earlier, carton) {
  const [L, W] = carton
  const ws = walls(p, L, W)
  const v = ws.find((w) => w === 'back' || w === 'front')
  const h = ws.find((w) => w === 'left' || w === 'right')
  let where
  if (v && h) where = `${v[0].toUpperCase()}${v.slice(1)}-${h} corner`
  else if (v || h) where = `Against the ${v || h} wall`
  else where = null

  const n = neighbours(p, earlier)[0]
  const next = n ? `${n.rel} ${n.q.seq} (${shortName(n.q.name)})` : null

  let headline
  if (where && next) headline = `${where}, ${next}`
  else if (where) headline = where
  else if (next) headline = `${next[0].toUpperCase()}${next.slice(1)}`
  else headline = `${fmt(p.x + p.padding_cm)} cm from the left, ${fmt(p.y + p.padding_cm)} cm from the back`
  // Exact edge of the product itself (slot minus padding), measured from the back-left corner.
  const exact = `${fmt(p.x + p.padding_cm)} cm from the left wall, ${fmt(p.y + p.padding_cm)} cm from the back wall`
  return { headline, exact }
}

export function describeOrientation(p) {
  const pad = p.padding_cm || 0
  const fx = p.dx - 2 * pad
  const fy = p.dy - 2 * pad
  const tall = p.dz - 2 * pad
  let turn
  if (Math.abs(fx - fy) < EPS) turn = 'Square base, any way round'
  else if (fx > fy) turn = `Long side (${fmt(fx)} cm) runs left to right`
  else turn = `Long side (${fmt(fy)} cm) runs front to back`
  return { turn, upright: `Stand it upright, ${fmt(tall)} cm tall`, footprint: `${fmt(fx)} × ${fmt(fy)} cm` }
}

const PROTECT = {
  BUBBLE: (it) => `Wrap ${it} in bubble wrap`,
  POLYBAG: (it) => `Seal ${it} in a poly bag, cap up`,
  FOAM: (it) => `Fit a foam insert around ${it}`,
  TISSUE: (it) => `Stuff and wrap ${it} with tissue paper`,
}
function protectLine(mat, perUnit, count) {
  const it = count > 1 ? 'each one' : 'it'
  const base = (PROTECT[mat.code] || ((x) => `Protect ${x} with ${mat.name.toLowerCase()}`))(it)
  return perUnit > 1 ? `${base} (${perUnit} ${mat.unit}s${count > 1 ? ' each' : ''})` : base
}

// Build slides. Consecutive placements of the same product are grouped into one slide,
// which keeps the engine's sequence intact (nothing is reordered).
export function buildSlides(plan, order) {
  const placements = [...(plan?.placements || [])].sort((a, b) => a.seq - b.seq)
  const carton = plan?.selected?.carton?.dims_cm
  const units = Object.fromEntries((plan?.units || []).map((u) => [u.ref, u]))
  const items = Object.fromEntries((order?.items || []).map((i) => [i.product_id, i]))
  const materials = Object.fromEntries((plan?.selected?.materials || []).map((m) => [m.code, m]))

  const groups = []
  for (const p of placements) {
    const last = groups[groups.length - 1]
    if (last && last.product_id === p.product_id) last.placements.push(p)
    else groups.push({ product_id: p.product_id, placements: [p] })
  }

  return groups.map((g, i) => {
    const first = g.placements[0]
    const unit = units[first.unit_ref] || {}
    const earlierAll = placements.filter((q) => q.seq < first.seq)
    const spots = g.placements.map((p) => {
      const earlier = placements.filter((q) => q.seq < p.seq)
      return { seq: p.seq, ref: p.unit_ref, ...describePosition(p, earlier, carton), ...describeOrientation(p) }
    })
    const mat = unit.protection_material_code ? materials[unit.protection_material_code] : null
    const wrap = mat ? protectLine(mat, unit.protection_qty_per_unit, g.placements.length) : null
    return {
      index: i,
      product_id: g.product_id,
      name: unit.name || first.name,
      item: items[g.product_id],
      qty: g.placements.length,
      refs: g.placements.map((p) => p.unit_ref),
      seqs: g.placements.map((p) => p.seq),
      fragile: !!unit.fragile,
      padding: first.padding_cm,
      handling: unit.handling_instructions,
      restrictions: unit.restrictions,
      wrap,
      spots,
      earlierRefs: earlierAll.map((q) => q.unit_ref),
    }
  })
}

// Which side of the carton faces the worker (the length side runs left to right).
export function setupShort(carton) {
  return `${fmt(carton[0])} cm side toward you`
}

export function setupLine(carton) {
  const [L, W, H] = carton
  return `Long side (${fmt(L)} cm) toward you · ${fmt(W)} cm deep · ${fmt(H)} cm tall`
}

// Product colour for each unit (from the catalogue illustration tone), so the 3D boxes
// look like the products the worker is holding.
export function colorsFor(plan, order) {
  const tones = Object.fromEntries((order?.items || []).map((i) => [i.product_id, i.art?.tone]))
  const out = {}
  for (const u of plan?.units || []) if (tones[u.product_id]) out[u.ref] = tones[u.product_id]
  return out
}

// How full the box is: items with their protective padding, and bare product volume.
export function fillOf(plan) {
  const vol = plan?.selected?.carton?.volume_cm3
  if (!vol) return null
  const padded = (plan.units || []).reduce((s, u) => s + u.padded_cm[0] * u.padded_cm[1] * u.padded_cm[2], 0)
  // Floor used: what the packing algorithm optimises (its rows on the carton floor).
  const [L, W] = plan.selected.carton.dims_cm
  const footprint = (plan.placements || []).reduce((s, p) => s + p.dx * p.dy, 0)
  return { floor: Math.min(1, footprint / (L * W)), padded: Math.min(1, padded / vol), product: plan.utilization ?? null }
}

// Shelf number of a standard warehouse carton: its position by size (1 = smallest), sent by the
// backend as box_no. Older plans without box_no fall back to the number in the code ("STD-02" -> "2").
export function boxNo(carton) {
  if (carton?.box_no) return String(carton.box_no)
  const m = /^(?:BOX|STD)-0*(\d+)$/i.exec(carton?.code || '')
  return m ? m[1] : null
}

export function cartonTitle(carton) {
  const n = boxNo(carton)
  return n ? `Box ${n} · ${carton.name}` : `${carton?.name} carton`
}
