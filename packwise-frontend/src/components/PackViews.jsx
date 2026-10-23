// Honest views of the C++ engine's output. Both draw ONLY the coordinates the engine
// returned. The engine plans a single layer (z = 0), so nothing is ever drawn stacked.
//
//  - IsoCarton: 3D open carton (isometric). Main view in the packing slides.
//  - FloorPlan: top-down, to scale. Exact positions; also used in admin history.
//
// placement fields (cm, carton frame): x along length (left -> right as the worker
// sees it), y along width (back -> front), dx/dy padded slot footprint, dz padded
// height, padding_cm clearance on every side.
//
// Step highlighting (optional): currentRefs = items being placed now, doneRefs =
// items already in the carton. Anything else is drawn as a dashed outline on the
// floor so the worker can see where it will go. Without these props every item is
// drawn normally (landing page, history, finished carton).

const PALETTE = ['#A99ACB', '#C9BDE3', '#8E7FB5', '#D8CFEA', '#B6A8D6']
const PEACH = '#FFBEA3'

function productBox(p) {
  const pad = p.padding_cm || 0
  return { x: p.x + pad, y: p.y + pad, dx: p.dx - 2 * pad, dy: p.dy - 2 * pad, dz: p.dz - 2 * pad }
}

function stateOf(ref, currentRefs, doneRefs) {
  if (!currentRefs && !doneRefs) return 'all'
  if (currentRefs?.has(ref)) return 'current'
  if (doneRefs?.has(ref)) return 'done'
  return 'todo'
}

// ---------------------------------------------------------------- top-down floor plan
export function FloorPlan({ carton, placements, currentRefs, doneRefs, fragileRefs = new Set(), compact = false, names = false }) {
  const [L, W] = carton
  const pad = compact ? 26 : 34
  const scale = Math.min(560 / L, (compact ? 260 : 360) / W)
  const w = L * scale + pad * 2
  const h = W * scale + pad * 2 + 6
  const s = (v) => v * scale

  return (
    <svg className="floorplan" viewBox={`0 0 ${w} ${h}`} role="img"
      aria-label={`Top view of the ${L} by ${W} centimetre carton floor`}>
      <defs>
        <pattern id="padhatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke={PEACH} strokeWidth="2" />
        </pattern>
      </defs>
      <g transform={`translate(${pad} ${pad})`}>
        <rect width={s(L)} height={s(W)} className="fp-floor" />
        {Array.from({ length: Math.floor(L / 5) }, (_, i) => (
          <line key={`gx${i}`} x1={s((i + 1) * 5)} x2={s((i + 1) * 5)} y1="0" y2={s(W)} className="fp-grid" />))}
        {Array.from({ length: Math.floor(W / 5) }, (_, i) => (
          <line key={`gy${i}`} y1={s((i + 1) * 5)} y2={s((i + 1) * 5)} x1="0" x2={s(L)} className="fp-grid" />))}
        {placements.map((p) => {
          const st = stateOf(p.unit_ref, currentRefs, doneRefs)
          if (st === 'todo') return (
            <g key={p.unit_ref}>
              <rect x={s(p.x)} y={s(p.y)} width={s(p.dx)} height={s(p.dy)} className="fp-ghost" />
              <text x={s(p.x + p.dx / 2)} y={s(p.y + p.dy / 2)} className="fp-seq ghost" dominantBaseline="central" textAnchor="middle">{p.seq}</text>
            </g>)
          const b = productBox(p)
          return (
            <g key={p.unit_ref} className={`fp-item ${st}`}>
              {p.padding_cm > 0 && <rect x={s(p.x)} y={s(p.y)} width={s(p.dx)} height={s(p.dy)} fill="url(#padhatch)" className="fp-pad" />}
              <rect x={s(b.x)} y={s(b.y)} width={Math.max(1, s(b.dx))} height={Math.max(1, s(b.dy))}
                className={`fp-box ${fragileRefs.has(p.unit_ref) && st === 'all' ? 'fragile' : ''}`} />
              <text x={s(p.x + p.dx / 2)} y={s(p.y + p.dy / 2) - (names && s(p.dy) > 34 && s(p.dx) > 60 ? 7 : 0)} className="fp-seq" dominantBaseline="central" textAnchor="middle">{p.seq}</text>
              {names && s(p.dy) > 34 && s(p.dx) > 60 && (
                <text x={s(p.x + p.dx / 2)} y={s(p.y + p.dy / 2) + 9} className="fp-name" dominantBaseline="central" textAnchor="middle">
                  {(p.name || '').replace(/\s+\d+(\.\d+)?\s?(ml|g)\b.*$/i, '').slice(0, Math.max(4, Math.floor(s(p.dx) / 7)))}
                </text>
              )}
            </g>
          )
        })}
        <g className="fp-dim">
          <line x1="0" x2={s(L)} y1={-14} y2={-14} /><line x1="0" x2="0" y1={-18} y2={-10} /><line x1={s(L)} x2={s(L)} y1={-18} y2={-10} />
        </g>
        <text x={s(L / 2)} y={-20} textAnchor="middle" className="fp-axis">Back · {L} cm</text>
        <text x={s(L / 2)} y={s(W) + 18} textAnchor="middle" className="fp-axis fp-front">Front · your side</text>
        <text x={-10} y={s(W / 2)} textAnchor="middle" className="fp-axis" transform={`rotate(-90 -10 ${s(W / 2)})`}>Left · {W} cm</text>
      </g>
    </svg>
  )
}

// ---------------------------------------------------------------- isometric 3D carton
const C30 = Math.cos(Math.PI / 6)
const S30 = 0.5

function painterOrder(boxes) {
  // A is drawn before B when A sits fully behind B along x or y (footprints never overlap).
  const n = boxes.length
  const behind = (a, b) => a.x + a.dx <= b.x + 1e-6 || a.y + a.dy <= b.y + 1e-6
  const order = []
  const used = new Array(n).fill(false)
  for (let k = 0; k < n; k++) {
    let pick = -1
    for (let i = 0; i < n && pick < 0; i++) {
      if (used[i]) continue
      let ok = true
      for (let j = 0; j < n; j++) if (!used[j] && j !== i && behind(boxes[j], boxes[i]) && !behind(boxes[i], boxes[j])) { ok = false; break }
      if (ok) pick = i
    }
    if (pick < 0) pick = used.indexOf(false)
    used[pick] = true
    order.push(pick)
  }
  return order
}

export function IsoCarton({ carton, placements, currentRefs, doneRefs, fragileRefs = new Set(), animate = false,
  className = '', theme = 'light', showFront = false }) {
  const [L, W, H] = carton
  // Camera at the front-right corner: x (left -> right) runs down-right on screen,
  // y (back -> front) runs down-left. Far walls (left x = 0, back y = 0) are drawn solid,
  // near walls (right x = L, front y = W) as dashed outlines so the contents stay visible.
  const P = (x, y, z) => [(x - y) * C30, (x + y) * S30 - z]
  const pts = (arr) => arr.map((c) => P(...c).join(',')).join(' ')
  const flapA = H * 0.42
  const frontAt = P(L / 2, W + Math.max(2.5, W * 0.12), 0)
  const probe = [[0, 0, 0], [L, 0, 0], [0, W, 0], [L, W, 0], [0, 0, H + flapA], [L, 0, H + flapA], [0, W, H + flapA]].map((c) => P(...c))
  if (showFront) probe.push([frontAt[0] - 8, frontAt[1] + 4], [frontAt[0] + 8, frontAt[1] + 4])
  const minX = Math.min(...probe.map((c) => c[0])) - 4, maxX = Math.max(...probe.map((c) => c[0])) + 4
  const minY = Math.min(...probe.map((c) => c[1])) - 4, maxY = Math.max(...probe.map((c) => c[1])) + 4

  const boxes = placements.map((p) => ({ ...productBox(p), ref: p.unit_ref, seq: p.seq, st: stateOf(p.unit_ref, currentRefs, doneRefs) }))
  const order = painterOrder(boxes)
  const fs = Math.max(1.6, Math.min(L, W) * 0.07)

  return (
    <svg className={`iso iso-${theme} ${className}`} viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`} role="img"
      aria-label={`Open ${L} by ${W} by ${H} centimetre carton with one layer of items, nothing stacked`}>
      <polygon points={pts([[0, 0, H], [0, W, H], [0, W * 0.92, H + flapA], [0, W * 0.08, H + flapA]])} className="iso-flap" />
      <polygon points={pts([[0, 0, H], [L, 0, H], [L * 0.92, 0, H + flapA], [L * 0.08, 0, H + flapA]])} className="iso-flap iso-flap-2" />
      <polygon points={pts([[0, 0, 0], [0, W, 0], [0, W, H], [0, 0, H]])} className="iso-wall-l" />
      <polygon points={pts([[0, 0, 0], [L, 0, 0], [L, 0, H], [0, 0, H]])} className="iso-wall-r" />
      <polygon points={pts([[0, 0, 0], [L, 0, 0], [L, W, 0], [0, W, 0]])} className="iso-floor" />

      {boxes.filter((b) => b.st === 'todo').map((b) => (
        <polygon key={`g${b.ref}`} className="iso-ghost"
          points={pts([[b.x, b.y, 0], [b.x + b.dx, b.y, 0], [b.x + b.dx, b.y + b.dy, 0], [b.x, b.y + b.dy, 0]])} />
      ))}

      {order.map((idx) => {
        const b = boxes[idx]
        if (b.st === 'todo') return null
        const color = b.st === 'current' ? PEACH : b.st === 'done' ? '#CFC6E2'
          : fragileRefs.has(b.ref) ? PEACH : PALETTE[idx % PALETTE.length]
        const x2 = b.x + b.dx, y2 = b.y + b.dy, z2 = b.dz
        const top = P(b.x + b.dx / 2, b.y + b.dy / 2, z2)
        return (
          <g key={`${b.ref}-${b.st}`} className={`iso-box ${b.st} ${animate ? 'drop' : ''}`}
            style={animate ? { animationDelay: `${0.35 + idx * 0.28}s` } : undefined}>
            <polygon points={pts([[x2, b.y, 0], [x2, y2, 0], [x2, y2, z2], [x2, b.y, z2]])} fill={color} className="f-r" />
            <polygon points={pts([[b.x, y2, 0], [x2, y2, 0], [x2, y2, z2], [b.x, y2, z2]])} fill={color} className="f-l" />
            <polygon points={pts([[b.x, b.y, z2], [x2, b.y, z2], [x2, y2, z2], [b.x, y2, z2]])} fill={color} className="f-t" />
            {b.st === 'current' && <text x={top[0]} y={top[1] - fs * 0.9} className="iso-seq" style={{ fontSize: fs }} textAnchor="middle">{b.seq}</text>}
          </g>
        )
      })}

      <polyline points={pts([[L, 0, H], [L, W, H], [0, W, H]])} className="iso-rim" />
      <polyline points={pts([[L, 0, 0], [L, W, 0], [0, W, 0]])} className="iso-rim" />
      {[[L, W], [L, 0], [0, W]].map(([x, y]) => {
        const a = P(x, y, 0), b = P(x, y, H)
        return <line key={`${x}-${y}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} className="iso-rim" />
      })}
      {showFront && (
        <text x={frontAt[0]} y={frontAt[1]} className="iso-label" style={{ fontSize: fs * 0.85 }} textAnchor="middle"
          transform={`rotate(30 ${frontAt[0]} ${frontAt[1]})`}>front · your side</text>
      )}
    </svg>
  )
}
