// The warehouse carton shelf: every carton size drawn to the same scale, with the
// packing algorithm's verdict on each one for this order. All data comes from the
// plan's evaluations (one per carton, computed by the backend + C++ engine).
import { boxNo } from '../lib/packPlan'

const fmt = (n) => (Math.round(n * 10) / 10).toString()

const VERDICT = {
  chosen: { label: 'Use this', cls: 'chosen' },
  fits: { label: 'Fits, but bigger', cls: 'fits' },
}

function verdictOf(ev, chosenId) {
  if (ev.carton.id === chosenId) return VERDICT.chosen
  if (ev.status === 'feasible') return VERDICT.fits
  const r = ev.short_reason || 'not suitable'
  return { label: r.charAt(0).toUpperCase() + r.slice(1), cls: 'no' }
}

// One carton in oblique projection: front face = length × height, depth drawn up-right.
function Box({ L, W, H, s, cls }) {
  const k = 0.42                       // depth foreshortening
  const dx = W * s * k * 0.87, dy = W * s * k * 0.5
  const w = L * s, h = H * s
  const vw = w + dx + 4, vh = h + dy + 4
  const x0 = 2, y0 = dy + 2
  return (
    <svg className={`shelf-box ${cls}`} width={vw} height={vh} viewBox={`0 0 ${vw} ${vh}`} aria-hidden>
      <polygon className="top" points={`${x0},${y0} ${x0 + dx},${y0 - dy} ${x0 + dx + w},${y0 - dy} ${x0 + w},${y0}`} />
      <polygon className="side" points={`${x0 + w},${y0} ${x0 + w + dx},${y0 - dy} ${x0 + w + dx},${y0 - dy + h} ${x0 + w},${y0 + h}`} />
      <rect className="front" x={x0} y={y0} width={w} height={h} />
      {cls === 'chosen' && <line className="tape" x1={x0 + w / 2} y1={y0} x2={x0 + w / 2} y2={y0 + h * 0.35} />}
    </svg>
  )
}

export default function CartonShelf({ plan }) {
  const chosenId = plan.selected?.carton?.id
  const shelf = (plan.evaluations || [])
    .filter((e) => e.status !== 'inactive' || boxNo(e.carton))
    .sort((a, b) => a.carton.volume_cm3 - b.carton.volume_cm3)
  if (!shelf.length) return null
  const maxL = Math.max(...shelf.map((e) => e.carton.dims_cm[0]))
  const maxH = Math.max(...shelf.map((e) => e.carton.dims_cm[2]))
  // ~120 px for the longest carton; never taller than ~100 px
  const s = Math.min(120 / maxL, 100 / maxH)
  const fits = shelf.filter((e) => e.status === 'feasible').length

  return (
    <section className="shelf" aria-label="Warehouse carton sizes">
      <div className="shelf-head">
        <p className="shelf-title">The packing algorithm tried all {shelf.length} carton sizes</p>
        <p className="shelf-sub">{fits} {fits === 1 ? 'fits' : 'fit'} this order safely · the smallest one wins, so the least air is shipped</p>
      </div>
      <ol className="shelf-row">
        {shelf.map((e) => {
          const v = verdictOf(e, chosenId)
          const [L, W, H] = e.carton.dims_cm
          const n = boxNo(e.carton)
          return (
            <li key={e.carton.id} className={`shelf-item ${v.cls}`} aria-current={v.cls === 'chosen' ? 'true' : undefined}>
              <div className="shelf-art"><Box L={L} W={W} H={H} s={s} cls={v.cls} /></div>
              <p className="shelf-name">{n && <span className="shelf-no">{n}</span>}{e.carton.name}</p>
              <p className="shelf-dims">{fmt(L)} × {fmt(W)} × {fmt(H)}</p>
              <p className="shelf-verdict">{v.label}</p>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
