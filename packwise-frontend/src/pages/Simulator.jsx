// Algorithm simulator: replays the original packer.cpp on real website orders and compares
// it with packing WITHOUT the algorithm. Every number and position comes from /api/sim.
import { useEffect, useMemo, useRef, useState } from 'react'
import Carton3D from '../components/Carton3D'
import { FloorPlan } from '../components/PackViews'
import { Empty, ErrorBox, Loading } from '../components/ui'
import { api } from '../lib/api'
import { money, pct, vol } from '../lib/format'
import useFetch from '../lib/useFetch'

const fmt = (n) => (Math.round(n * 10) / 10).toString()
const dims = (d) => d.map(fmt).join(' × ') + ' cm'

// ------------------------------------------------------------------ input
function Source({ onRun, busy }) {
  const [mode, setMode] = useState('order')
  const orders = useFetch('/api/sim/orders')
  const products = useFetch(mode === 'custom' ? '/api/sim/products' : null)
  const [orderId, setOrderId] = useState('')
  const [mix, setMix] = useState({})
  useEffect(() => { if (!orderId && orders.data?.length) setOrderId(String(orders.data[0].id)) }, [orders.data, orderId])

  const lines = Object.entries(mix).filter(([, q]) => q > 0).map(([id, q]) => ({ product_id: Number(id), quantity: q }))
  return (
    <section className="sim-source">
      <div className="seg seg-small" role="tablist">
        <button role="tab" aria-selected={mode === 'order'} className={mode === 'order' ? 'on' : ''} onClick={() => setMode('order')}>Website order</button>
        <button role="tab" aria-selected={mode === 'custom'} className={mode === 'custom' ? 'on' : ''} onClick={() => setMode('custom')}>Custom mix</button>
      </div>
      {mode === 'order' ? (
        <div className="sim-row">
          {orders.loading && <Loading label="Loading orders" />}
          <ErrorBox error={orders.error} retry={orders.reload} />
          {orders.data?.length === 0 && <Empty title="No orders yet">Place an order on TOTE, then simulate it here.</Empty>}
          {orders.data?.length > 0 && (<>
            <select className="input" value={orderId} onChange={(e) => setOrderId(e.target.value)} aria-label="Order">
              {orders.data.map((o) => (
                <option key={o.id} value={o.id}>{o.code} · {o.units} items · {o.items.map((i) => `${i.quantity}× ${i.name}`).join(', ').slice(0, 80)}</option>
              ))}
            </select>
            <button className="btn btn-peach btn-lg" disabled={busy || !orderId} onClick={() => onRun({ orderId })}>{busy ? 'Running…' : 'Run simulation'}</button>
          </>)}
        </div>
      ) : (
        <div>
          {products.loading && <Loading label="Loading products" />}
          <div className="mix">
            {products.data?.map((p) => (
              <div key={p.id} className={`mix-item ${mix[p.id] ? 'on' : ''}`}>
                <span className="mix-name">{p.name}<small>{p.dims_cm.join(' × ')} cm{p.fragile ? ' · fragile' : ''}</small></span>
                <div className="mstep-ctl">
                  <button type="button" onClick={() => setMix({ ...mix, [p.id]: Math.max(0, (mix[p.id] || 0) - 1) })} aria-label={`Fewer ${p.name}`}>−</button>
                  <b>{mix[p.id] || 0}</b>
                  <button type="button" onClick={() => setMix({ ...mix, [p.id]: Math.min(20, (mix[p.id] || 0) + 1) })} aria-label={`More ${p.name}`}>+</button>
                </div>
              </div>
            ))}
          </div>
          <div className="sim-row">
            <span className="muted">{lines.reduce((s, l) => s + l.quantity, 0)} items selected</span>
            <button className="btn btn-quiet" onClick={() => setMix({})} disabled={!lines.length}>Clear</button>
            <button className="btn btn-peach btn-lg" disabled={busy || !lines.length} onClick={() => onRun({ items: lines })}>{busy ? 'Running…' : 'Run simulation'}</button>
          </div>
        </div>
      )}
    </section>
  )
}

// ------------------------------------------------------------------ 1. width search
function SweepChart({ sweep }) {
  const trials = sweep.trials
  const fit = trials.filter((t) => t.fits)
  const [shown, setShown] = useState(trials.length)
  const raf = useRef(0)
  const play = () => {
    cancelAnimationFrame(raf.current)
    const t0 = performance.now()
    const tick = (t) => {
      const n = Math.min(trials.length, Math.ceil(((t - t0) / 2600) * trials.length))
      setShown(n)
      if (n < trials.length) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
  }
  useEffect(() => { play(); return () => cancelAnimationFrame(raf.current) }, [sweep]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!fit.length) return <p className="muted">No width worked for these items.</p>
  const W = 640, H = 220, pl = 64, pb = 34, pt = 14, pr = 14
  const xs = trials.map((t) => t.width_cm), vs = fit.map((t) => t.volume_cm3)
  const x0 = Math.min(...xs), x1 = Math.max(...xs) || x0 + 1
  const v0 = Math.min(...vs) * 0.9, v1 = Math.max(...vs) * 1.05
  const X = (x) => pl + ((x - x0) / Math.max(1e-9, x1 - x0)) * (W - pl - pr)
  const Y = (v) => pt + (1 - (v - v0) / Math.max(1e-9, v1 - v0)) * (H - pt - pb)
  const visible = trials.slice(0, shown)
  const cur = visible[visible.length - 1]
  const best = trials[sweep.best]
  const bestShown = shown > sweep.best
  // best-so-far line (the algorithm keeps the lowest score seen so far)
  let run = Infinity
  const path = visible.filter((t) => t.fits).map((t) => { run = Math.min(run, t.volume_cm3); return `${X(t.width_cm)},${Y(run)}` }).join(' ')

  return (
    <div className="sweep">
      <svg viewBox={`0 0 ${W} ${H}`} className="sweep-svg" role="img" aria-label={`${trials.length} row widths tried; best at ${best.width_cm} cm`}>
        {[0, 0.5, 1].map((f) => {
          const v = v0 + (v1 - v0) * f
          return <g key={f}><line x1={pl} x2={W - pr} y1={Y(v)} y2={Y(v)} className="sw-grid" />
            <text x={pl - 6} y={Y(v)} className="sw-ax" textAnchor="end" dominantBaseline="middle">{vol(v)}</text></g>
        })}
        <text x={pl} y={H - 8} className="sw-ax">{fmt(x0)} cm</text>
        <text x={W - pr} y={H - 8} className="sw-ax" textAnchor="end">{fmt(x1)} cm</text>
        <text x={(pl + W - pr) / 2} y={H - 8} className="sw-ax" textAnchor="middle">row width tried →</text>
        <polyline points={path} className="sw-best-line" />
        {visible.map((t) => t.fits
          ? <circle key={t.k} cx={X(t.width_cm)} cy={Y(t.volume_cm3)} r={t.k === sweep.best && bestShown ? 6 : 2.6} className={`sw-pt ${t.k === sweep.best && bestShown ? 'best' : ''}`} />
          : <line key={t.k} x1={X(t.width_cm)} x2={X(t.width_cm)} y1={H - pb} y2={H - pb - 6} className="sw-no" />)}
      </svg>
      <div className="sweep-side">
        <p className="sw-k">Trial {cur ? cur.k + 1 : 0} of {trials.length}</p>
        {cur && (cur.fits
          ? <p>Width {fmt(cur.width_cm)} cm → box {dims(cur.box_cm)} = <b>{vol(cur.volume_cm3)}</b></p>
          : <p>Width {fmt(cur.width_cm)} cm → an item does not fit</p>)}
        {shown >= trials.length && (
          <p className="sw-kept">Kept trial {best.k + 1}: <b>{dims(best.box_cm)}</b>, the lowest score (volume plus a small penalty for long sides).</p>
        )}
        <button className="btn btn-quiet" onClick={play}>Replay search</button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ 2. placement replay
function Replay({ algo, colors }) {
  const n = algo.placements.length
  const [step, setStep] = useState(0) // number of items placed
  const [playing, setPlaying] = useState(false)
  const [view, setView] = useState('top')
  useEffect(() => { setStep(0); setPlaying(true) }, [algo])
  useEffect(() => {
    if (!playing) return
    if (step >= n) { setPlaying(false); return }
    const t = setTimeout(() => setStep((s) => s + 1), 900)
    return () => clearTimeout(t)
  }, [playing, step, n])

  const refs = algo.placements.map((p) => p.unit_ref)
  const currentRefs = useMemo(() => new Set(step > 0 ? [refs[step - 1]] : []), [step, algo]) // eslint-disable-line react-hooks/exhaustive-deps
  const doneRefs = useMemo(() => new Set(refs.slice(0, Math.max(0, step - 1))), [step, algo]) // eslint-disable-line react-hooks/exhaustive-deps
  const cur = step > 0 ? algo.steps[step - 1] : null

  return (
    <div className="replay">
      <div className="replay-viz">
        <div className="replay-bar">
          <div className="seg seg-small" role="tablist">
            <button role="tab" aria-selected={view === 'top'} className={view === 'top' ? 'on' : ''} onClick={() => setView('top')}>Top view</button>
            <button role="tab" aria-selected={view === '3d'} className={view === '3d' ? 'on' : ''} onClick={() => setView('3d')}>3D</button>
          </div>
          <span className="muted small">Box {dims(algo.box_cm)}</span>
        </div>
        {view === 'top'
          ? <FloorPlan carton={algo.box_cm} placements={algo.placements} currentRefs={currentRefs} doneRefs={doneRefs} names />
          : <Carton3D carton={algo.box_cm} placements={algo.placements} currentRefs={currentRefs} doneRefs={doneRefs} colors={colors} />}
        <div className="replay-ctl">
          <button className="btn btn-quiet" onClick={() => { setPlaying(false); setStep(0) }}>Restart</button>
          <button className="btn btn-quiet" disabled={step === 0} onClick={() => { setPlaying(false); setStep(step - 1) }}>Back</button>
          <button className="btn btn-ink" onClick={() => (step >= n ? (setStep(0), setPlaying(true)) : setPlaying(!playing))}>
            {playing ? 'Pause' : step >= n ? 'Play again' : 'Play'}</button>
          <button className="btn btn-quiet" disabled={step >= n} onClick={() => { setPlaying(false); setStep(step + 1) }}>Next</button>
          <span className="replay-count">{step} / {n} placed</span>
        </div>
      </div>
      <ol className="steplog">
        {algo.steps.map((s, i) => (
          <li key={s.ref} className={i === step - 1 ? 'now' : i < step - 1 ? 'done' : ''}>
            <span className="seqdot">{s.seq}</span>
            <div><b>{s.name}</b><span>{s.text}</span></div>
          </li>
        ))}
      </ol>
      {cur && <p className="sr-only" aria-live="polite">{cur.name}: {cur.text}</p>}
    </div>
  )
}

// ------------------------------------------------------------------ 3. with vs without
function SameScale({ options }) {
  // Top views of all options drawn to ONE scale, so their sizes compare honestly.
  const avail = options.filter((o) => o.available !== false)
  const maxL = Math.max(...avail.map((o) => o.box_cm[0])), maxW = Math.max(...avail.map((o) => o.box_cm[1]))
  const s = Math.min(150 / maxW, 260 / maxL)
  return (
    <div className="samescale" aria-label="All boxes drawn to the same scale">
      {avail.map((o) => (
        <figure key={o.key} className={o.key === 'algorithm' ? 'algo' : ''}>
          <svg width={o.box_cm[0] * s + 4} height={o.box_cm[1] * s + 4}>
            <rect x="2" y="2" width={o.box_cm[0] * s} height={o.box_cm[1] * s} className="ss-box" />
            {o.placements.map((p) => <rect key={p.unit_ref} x={2 + (p.x + p.padding_cm) * s} y={2 + (p.y + p.padding_cm) * s}
              width={Math.max(1, (p.dx - 2 * p.padding_cm) * s)} height={Math.max(1, (p.dy - 2 * p.padding_cm) * s)} className="ss-item" />)}
          </svg>
          <figcaption>{o.label.replace('Without: ', '')}<br /><b>{dims(o.box_cm)}</b></figcaption>
        </figure>
      ))}
    </div>
  )
}

const ROWS = [
  ['Box size', (o) => dims(o.box_cm)],
  ['Box volume', (o) => vol(o.volume_cm3)],
  ['Filled by items', (o) => pct(o.fill)],
  ['Empty space', (o) => vol(o.empty_cm3)],
  ['Cardboard', (o) => `${o.board_m2.toFixed(3)} m²`],
  ['Box cost', (o) => money(o.box_cost)],
  ['Void-fill paper', (o) => `${o.void_fill_sheets} sheets`],
]

function Compare({ data }) {
  const options = [...data.without, data.algorithm]
  const byKey = Object.fromEntries(data.comparisons.map((c) => [c.against, c]))
  return (
    <div>
      <SameScale options={options} />
      <div className="table-wrap">
        <table className="table cmp">
          <thead><tr><th></th>{options.map((o) => <th key={o.key} className={o.key === 'algorithm' ? 'algo' : ''}>{o.label}{o.carton ? ` (${o.carton})` : ''}</th>)}</tr></thead>
          <tbody>
            {ROWS.map(([label, f]) => (
              <tr key={label}><td>{label}</td>{options.map((o) => <td key={o.key} className={o.key === 'algorithm' ? 'algo' : ''}>{o.available === false ? '—' : f(o)}</td>)}</tr>
            ))}
            <tr><td>How it was packed</td>{options.map((o) => <td key={o.key} className={`small ${o.key === 'algorithm' ? 'algo' : ''}`}>{o.available === false ? o.reason : o.note}</td>)}</tr>
          </tbody>
        </table>
      </div>
      <div className="savings">
        {data.without.map((o) => {
          const c = byKey[o.key]
          if (!c) return null
          const more = (v, unit, lessWord, moreWord) => (v >= 0 ? `${unit(v)} ${lessWord}` : `${unit(-v)} ${moreWord}`)
          return (
            <div key={o.key} className="saving-card">
              <p className="muted">Compared with {o.key === 'stock' ? `the ${o.carton} stock carton` : 'one straight row'}</p>
              <p className="big">{pct(Math.abs(c.volume_saved_pct))} <span>{c.volume_saved_pct >= 0 ? 'less' : 'more'} box volume</span></p>
              <p>{more(c.volume_saved_cm3, vol, 'less space', 'more space')} ·
                {' '}{more(c.board_saved_m2, (v) => `${v.toFixed(3)} m²`, 'less cardboard', 'more cardboard')} ·
                {' '}{more(c.cost_saved, money, 'cheaper box', 'dearer box')} ·
                {' '}{more(c.void_fill_saved, (v) => `${v}`, 'fewer paper sheets', 'more paper sheets')}</p>
            </div>
          )
        })}
      </div>
      <details className="why-box"><summary>Assumptions</summary><ul>{data.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul></details>
    </div>
  )
}

function Totals() {
  const { data, error, loading, reload } = useFetch('/api/sim/summary')
  if (loading) return <Loading label="Simulating recent orders" />
  if (error) return <ErrorBox error={error} retry={reload} />
  const t = data.totals
  if (!t.orders) return <Empty title="No orders to compare yet" />
  const cut = (a, b) => (b ? 1 - a / b : null)
  return (
    <div>
      <div className="stats">
        <div className="stat stat-ink"><p className="stat-label">Orders simulated</p><p className="stat-value">{t.orders}</p></div>
        <div className="stat stat-peach"><p className="stat-label">Box volume vs one row</p><p className="stat-value">−{pct(cut(t.algorithm_cm3, t.single_row_cm3))}</p>
          <p className="stat-note">{vol(t.algorithm_cm3)} instead of {vol(t.single_row_cm3)}</p></div>
        <div className="stat stat-peach"><p className="stat-label">Box volume vs stock cartons</p><p className="stat-value">{t.stock_orders ? `−${pct(cut(t.algo_cm3_on_stock_orders, t.stock_cm3))}` : '—'}</p>
          <p className="stat-note">{t.stock_orders} orders that fit a stock carton</p></div>
        <div className="stat"><p className="stat-label">Box cost vs stock cartons</p><p className="stat-value">{t.stock_orders ? money(t.stock_cost - t.algo_cost_on_stock_orders) : '—'}</p>
          <p className="stat-note">{money(t.algo_cost_on_stock_orders)} instead of {money(t.stock_cost)}</p></div>
      </div>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Order</th><th className="num">Items</th><th>Algorithm box</th><th className="num">Volume</th><th className="num">One row</th><th className="num">Stock carton</th><th className="num">Filled (algo / stock)</th></tr></thead>
        <tbody>{data.orders.map((o) => (
          <tr key={o.id}><td><b>{o.code}</b></td><td className="num">{o.units}</td><td>{dims(o.algorithm_box_cm)}</td><td className="num">{vol(o.algorithm_cm3)}</td>
            <td className="num">{vol(o.single_row_cm3)}</td><td className="num">{o.stock_cm3 ? `${vol(o.stock_cm3)} (${o.stock_carton})` : 'none fits'}</td>
            <td className="num">{pct(o.algorithm_fill)} / {o.stock_fill != null ? pct(o.stock_fill) : '—'}</td></tr>))}</tbody>
      </table></div>
    </div>
  )
}

// ------------------------------------------------------------------ page
export default function Simulator() {
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = async ({ orderId, items }) => {
    setBusy(true); setError(null)
    try { setRes(orderId ? await api(`/api/sim/orders/${orderId}`) : await api('/api/sim/custom', { method: 'POST', body: { items } })) }
    catch (e) { setError(e) } finally { setBusy(false) }
  }
  const colors = useMemo(() => {
    if (!res) return {}
    const tones = Object.fromEntries((res.order.items || []).map((i) => [i.product_id, i.art?.tone]))
    return Object.fromEntries(res.units.map((u) => [u.ref, tones[u.product_id]]).filter(([, t]) => t))
  }, [res])

  return (
    <div className="pagepad sim">
      <div className="page-head"><div>
        <h1>Algorithm simulator</h1>
        <p className="muted">Runs your packing algorithm (the original packer.cpp, unchanged) on real TOTE orders, step by step, and compares it with packing without it.</p>
      </div></div>

      <Source onRun={run} busy={busy} />
      <ErrorBox error={error} />
      {busy && !res && <Loading label="Running the algorithm" />}

      {res && (<>
        <h2 className="sim-h">{res.order.code}: {res.units.length} items <span className="muted small">{res.order.items.map((i) => `${i.quantity}× ${i.name}`).join(', ')}</span></h2>

        <section className="panel sim-panel">
          <h3>1. Width search</h3>
          <p className="muted small">The algorithm sorts items longest side first, then tries {res.algorithm.sweep.trials.length} row widths between {fmt(res.algorithm.sweep.lo_cm)} and {fmt(res.algorithm.sweep.hi_cm)} cm.
            For each width it fills rows left to right and measures the box. The peach line is the best box found so far.</p>
          <SweepChart sweep={res.algorithm.sweep} />
        </section>

        <section className="panel sim-panel">
          <h3>2. Placement, step by step</h3>
          <p className="muted small">Items go into the kept width in the algorithm's order. Each step shows exactly where it put the item and why.</p>
          <Replay algo={res.algorithm} colors={colors} />
        </section>

        <section className="panel sim-panel">
          <h3>3. With vs without the algorithm</h3>
          <Compare data={res} />
        </section>
      </>)}

      <section className="panel sim-panel">
        <h3>Across recent website orders</h3>
        <p className="muted small">Every recent TOTE order run through the algorithm and through both ways of packing without it.</p>
        <Totals key={res ? res.order.code : 'none'} />
      </section>
    </div>
  )
}
