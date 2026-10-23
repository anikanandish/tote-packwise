// One order, end to end: what the customer bought, every packing plan, and the packing
// engine's actual result for the plan you pick (inputs, candidate cartons, coordinates, JSON).
import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import Carton3D from '../../components/Carton3D'
import { FloorPlan } from '../../components/PackViews'
import { Empty, ErrorBox, Loading, OrderBadge, PlanBadge, Tag } from '../../components/ui'
import { kg, litres, mm3, money, pct, signedMoney, when } from '../../lib/format'
import { buildSlides, cartonTitle, colorsFor, fillOf } from '../../lib/packPlan'
import useFetch from '../../lib/useFetch'

const CHECKS = [['dimensions', 'Size'], ['weight', 'Weight'], ['placement', 'Engine fit'], ['carton_stock', 'Stock'], ['materials', 'Materials']]

function CheckDot({ ev, name }) {
  const ch = ev.checks.find((c) => c.name === name)
  if (!ch) return <span className="dot dot-na" title="Not reached">·</span>
  if (ch.not_checked) return <span className="dot dot-warn" title={ch.detail}>?</span>
  return <span className={`dot ${ch.ok ? 'dot-ok' : 'dot-bad'}`} title={ch.detail}>{ch.ok ? '✓' : '✕'}</span>
}

function Candidates({ plan }) {
  const chosen = plan.selected?.carton?.id
  const rows = [...plan.evaluations].sort((a, b) => a.carton.volume_cm3 - b.carton.volume_cm3)
  return (
    <div className="table-wrap"><table className="table compact">
      <thead><tr><th>Carton</th><th>Internal mm</th><th className="num">Volume</th>{CHECKS.map(([, l]) => <th key={l} className="center">{l}</th>)}<th>Verdict</th><th className="num">Est. cost</th></tr></thead>
      <tbody>{rows.map((ev) => {
        const sel = ev.carton.id === chosen
        return (
          <tr key={ev.carton.id} className={sel ? 'row-selected' : ev.status === 'inactive' ? 'inactive' : ''}>
            <td><b>{ev.carton.name}</b><div className="small muted">{ev.carton.code}</div></td>
            <td className="mono">{mm3(ev.carton.dims_mm)}{ev.carton.internal_verified === false && <div><Tag kind="warn">nominal</Tag></div>}</td>
            <td className="num">{litres(ev.carton.volume_cm3)}</td>
            {CHECKS.map(([n]) => <td key={n} className="center"><CheckDot ev={ev} name={n} /></td>)}
            <td>{sel ? <Tag kind="base">Selected</Tag> : ev.status === 'feasible' ? <Tag>Fits, larger</Tag> : ev.status === 'inactive' ? <Tag>Switched off</Tag>
              : <span className="small err">{ev.short_reason || ev.reasons[0]}</span>}</td>
            <td className="num">{ev.cost?.total != null ? money(ev.cost.total) : '—'}</td>
          </tr>)
      })}</tbody>
    </table></div>
  )
}

function PackingResult({ planId, order }) {
  const { data: p, error, loading } = useFetch(`/api/packwise/plans/${planId}`)
  const [view, setView] = useState('3d')
  const colors = useMemo(() => (p ? colorsFor(p, order) : {}), [p, order])
  const fragileRefs = useMemo(() => new Set((p?.units || []).filter((u) => u.fragile).map((u) => u.ref)), [p])
  const slides = useMemo(() => (p?.selected ? buildSlides(p, order) : []), [p, order])
  if (loading) return <Loading label="Loading packing result" />
  if (error) return <ErrorBox error={error} />
  const sel = p.selected
  const carton = sel?.carton
  const fill = sel ? fillOf(p) : null
  const units = Object.fromEntries(p.units.map((u) => [u.ref, u]))
  const enginePlacements = sel?.placement?.placements || []
  const rawResult = (p.engine.response_results || []).find((r) => carton && r.carton_id === `C${carton.id}`)

  return (
    <div className="result">
      <div className="result-head">
        <PlanBadge status={p.status} />
        <span className="muted small">Plan #{p.id} · made by {p.created_by} {when(p.created_at)}{p.accepted_by && ` · accepted by ${p.accepted_by}`}{p.completed_at && ` · completed ${when(p.completed_at)}`}</span>
        {p.is_override && <Tag kind="sample">Worker override</Tag>}
      </div>
      {p.override && <div className="alert"><b>Override:</b> {p.override.actor} replaced {p.override.original_carton} with this carton. Reason: “{p.override.reason}”</div>}
      {p.cancel_reason && <div className="alert"><b>Cancelled:</b> {p.cancel_reason}</div>}

      {sel ? (<>
        <div className="result-grid">
          <div className="carton-card">
            <p className="ch-label">Carton</p>
            <p className="cc-name">{cartonTitle(carton)}</p>
            <p className="mono">{mm3(carton.dims_mm)} internal{carton.nominal_mm && carton.nominal_mm.join() !== carton.dims_mm.join() && <span className="muted"> · nominal {mm3(carton.nominal_mm)}</span>}</p>
            <div className="tags">{carton.internal_verified ? <Tag kind="ok">Internal size verified</Tag> : <Tag kind="warn">Nominal size used</Tag>}
              {carton.max_weight_g == null ? <Tag kind="warn">No weight limit set</Tag> : <Tag>Max {kg(carton.max_weight_g)}</Tag>}</div>
          </div>
          <div className="mini-stats">
            <div><span>Estimated packaging cost</span><b>{money(p.estimated_cost)}</b>{carton.sample_fields?.includes('unit_cost') && <Tag kind="sample">sample carton price</Tag>}</div>
            <div><span>Against baseline</span><b>{signedMoney(p.estimated_savings)}</b>{p.baseline?.carton && <small>{p.baseline.carton.name}</small>}</div>
            <div><span>Box filled (items + padding)</span><b>{fill ? pct(fill.padded) : '—'}</b><small>calculated</small></div>
            <div><span>Floor covered</span><b>{fill ? pct(fill.floor) : '—'}</b><small>one layer</small></div>
          </div>
        </div>
        {p.warnings?.length > 0 && <ul className="warn-list">{p.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
        {sel.why?.length > 0 && <div className="panel why-panel"><h3>Why this carton</h3><ul>{sel.why.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}

        <section className="panel">
          <div className="panel-head"><h3>3D packing blueprint</h3>
            <div className="seg-small" role="tablist"><button role="tab" aria-selected={view === '3d'} className={view === '3d' ? 'on' : ''} onClick={() => setView('3d')}>3D</button>
              <button role="tab" aria-selected={view === 'top'} className={view === 'top' ? 'on' : ''} onClick={() => setView('top')}>Top view</button></div></div>
          <div className="blueprint">{view === '3d'
            ? <Carton3D carton={carton.dims_cm} placements={p.placements} colors={colors} fragileRefs={fragileRefs} />
            : <FloorPlan carton={carton.dims_cm} placements={p.placements} fragileRefs={fragileRefs} names />}</div>
          <p className="small muted">Drawn from the stored engine coordinates: one layer, z = 0, nothing stacked. Translucent shells show protective padding.</p>
        </section>

        <section className="panel">
          <h3>Placement coordinates <span className="muted small">(C++ engine output, carton frame, mm)</span></h3>
          <div className="table-wrap flat"><table className="table compact">
            <thead><tr><th className="num">#</th><th>Item</th><th className="num">x</th><th className="num">y</th><th className="num">z</th><th className="num">Slot L × W × H</th><th>Turned 90°</th><th className="num">Padding</th></tr></thead>
            <tbody>{enginePlacements.map((q) => (
              <tr key={q.id}><td className="num">{q.seq}</td><td>{units[q.id]?.name || q.id}<div className="small muted">{q.id}</div></td>
                <td className="num">{q.x}</td><td className="num">{q.y}</td><td className="num">{q.z}</td><td className="num mono">{q.dx} × {q.dy} × {q.dz}</td>
                <td>{q.rotated ? 'Yes' : 'No'}</td><td className="num">{units[q.id]?.padding_cm ? `${units[q.id].padding_cm * 10} mm` : '—'}</td></tr>))}</tbody>
          </table></div>
          {sel.placement?.search && <p className="small muted">Inside this carton the engine tried {sel.placement.search.widths_tried} row widths (both orientations); {sel.placement.search.widths_that_fit} produced a layout that fits, and the tightest was kept{sel.placement.orientation ? ` (${sel.placement.orientation.replace(/_/g, ' ')})` : ''}.</p>}
        </section>

        {slides.length > 0 && (
          <section className="panel">
            <h3>Packing instructions shown to the worker</h3>
            <ol className="instr">{slides.map((s) => (
              <li key={s.index}><b>{s.qty > 1 ? `${s.qty} × ` : ''}{s.name}</b>
                {s.wrap && <span className="instr-wrap">{s.wrap}</span>}
                {s.spots.map((sp) => <div key={sp.ref} className="small">#{sp.seq}: {sp.headline}. {sp.turn}. {sp.upright}.</div>)}</li>))}
              <li><b>Fill gaps, check and seal</b><div className="small">{(sel.materials || []).filter((m) => m.purpose === 'void_fill').map((m) => `About ${m.quantity} ${m.name.toLowerCase()} (estimate)`).join('; ') || 'No void fill estimated'}</div></li>
            </ol>
          </section>)}
      </>) : (
        <section className="panel nofit">
          <h3>No carton can hold this order</h3>
          <p>PackWise did not pick a carton, so nothing was reserved and no layout is shown.</p>
          {p.blockers?.length > 0 && <ul className="warn-list">{p.blockers.map((b, i) => <li key={i}>{b}</li>)}</ul>}
          {p.alternatives?.length > 0 && (<><h3>What could be done</h3><ul className="alt-list">{p.alternatives.map((a, i) => <li key={i}>{a.text}</li>)}</ul></>)}
          <Link to="/admin/cartons" className="btn btn-quiet">Open cartons</Link>
        </section>
      )}

      <section className="panel">
        <h3>Candidate cartons</h3>
        <p className="small muted">Every carton considered for this plan, smallest first. Hover a mark for the detail.</p>
        <Candidates plan={p} />
      </section>

      <section className="panel">
        <h3>Items sent to the engine</h3>
        <div className="table-wrap flat"><table className="table compact">
          <thead><tr><th>Unit</th><th>Product</th><th className="num">Product cm</th><th className="num">Padding</th><th className="num">Packed size mm</th><th className="num">Weight</th></tr></thead>
          <tbody>{p.units.map((u) => (
            <tr key={u.ref}><td className="mono">{u.ref}</td><td>{u.name} {u.fragile && <Tag kind="warn">Fragile</Tag>}</td>
              <td className="num">{u.dims_cm.join(' × ')}</td><td className="num">{u.padding_cm ? `${u.padding_cm} cm` : '—'}{u.padding_rule === 'fragile_minimum' && <div className="small muted">fragile minimum</div>}</td>
              <td className="num mono">{u.padded_mm.join(' × ')}</td><td className="num">{kg(u.weight_g)}</td></tr>))}</tbody>
        </table></div>
        <p className="small muted">The engine only sees these packed sizes (product + padding, rounded up to whole mm). Weight, padding, stock and cost are business rules applied by the backend, not by the engine.</p>
      </section>

      <details className="panel json-panel"><summary>Engine request and raw JSON response</summary>
        <p className="small muted">Exactly what was sent to and returned by the C++ packing service for this plan.</p>
        <h4>Request</h4><pre>{JSON.stringify(p.engine.request, null, 2)}</pre>
        <h4>Response {rawResult ? `(selected carton ${carton.code})` : ''}</h4>
        <pre>{JSON.stringify(rawResult || p.engine.response_results || p.engine.response_meta, null, 2)}</pre>
        {p.engine.response_meta && <><h4>Engine</h4><pre>{JSON.stringify(p.engine.response_meta, null, 2)}</pre></>}
      </details>
    </div>
  )
}

export default function OrderDetail() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const { data, error, loading, reload } = useFetch(`/api/admin/orders/${id}`)
  const [pick, setPick] = useState(params.get('plan') ? Number(params.get('plan')) : null)
  if (loading) return <Loading label="Loading order" />
  if (error) return <div className="pagepad"><ErrorBox error={error} retry={reload} /></div>
  const o = data.order
  const planId = pick ?? data.current_plan_id
  return (
    <div className="pagepad">
      <Link to="/admin/orders" className="back">Orders</Link>
      <div className="page-head">
        <div>
          <h1>{o.code} <OrderBadge status={o.status} />{o.priority && <Tag kind="base">Priority</Tag>}{o.fragile && <Tag kind="warn">Fragile</Tag>}</h1>
          <p className="muted">{o.customer} · {data.order.customer_email} · placed {when(o.created_at)} · {money(o.total)} · {o.unit_count} units · {kg(o.weight_g)}</p>
        </div>
        <Link to={`/orders/${o.id}`} className="btn btn-quiet">Open in worker view</Link>
      </div>

      <div className="order-top">
        <section className="panel">
          <h3>Items</h3>
          <div className="table-wrap flat"><table className="table compact">
            <thead><tr><th>Product</th><th className="num">Qty</th><th className="num">Size cm</th><th className="num">Weight</th><th>Packing needs</th></tr></thead>
            <tbody>{o.items.map((i) => (
              <tr key={i.product_id}><td>{i.name}<div className="small muted">{money(i.unit_price)} each</div></td><td className="num">{i.quantity}</td>
                <td className="num">{[i.packaging.length_cm, i.packaging.width_cm, i.packaging.height_cm].join(' × ')}</td><td className="num">{kg(i.packaging.weight_g)}</td>
                <td className="small"><div className="tags">{i.packaging.fragile && <Tag kind="warn">Fragile</Tag>}{i.packaging.orientation === 'upright' && <Tag>Upright</Tag>}
                  {i.packaging.protection_material_code && <Tag>{i.packaging.protection_material_code}</Tag>}</div></td></tr>))}</tbody>
          </table></div>
        </section>
        <section className="panel">
          <h3>Timeline</h3>
          <ol className="timeline">{o.timeline.map((t, k) => <li key={k}><b>{t.status.replace(/_/g, ' ')}</b> <span className="muted small">{when(t.at)}</span>{t.note && <div className="small">{t.note}</div>}</li>)}</ol>
          {data.completion && (<>
            <h3>Packed</h3>
            <p className="small">{data.completion.actor} · {when(data.completion.created_at)} · {data.completion.carton_code} · actual cost {money(data.completion.actual_cost)}</p>
            <ul className="list small">{data.completion.materials_used.map((m) => <li key={m.code}>{m.quantity} {m.unit} {m.name}</li>)}</ul>
          </>)}
          {data.overrides.length > 0 && (<>
            <h3>Carton overrides</h3>
            <ul className="list small">{data.overrides.map((x) => <li key={x.id}><b>{x.from} → {x.to}</b> by {x.actor} · “{x.reason}”</li>)}</ul>
          </>)}
        </section>
      </div>

      <h2 className="block-title">Packing results</h2>
      {data.plans.length === 0 ? <Empty title="Not planned yet">A recommendation is made when a worker opens this order in the queue.</Empty> : (<>
        <div className="plan-tabs" role="tablist">{[...data.plans].reverse().map((pl) => (
          <button key={pl.id} role="tab" aria-selected={pl.id === planId} className={pl.id === planId ? 'on' : ''} onClick={() => setPick(pl.id)}>
            #{pl.id} <PlanBadge status={pl.status} />{pl.carton && <span className="small"> {pl.carton.name}</span>}{pl.id === data.current_plan_id && <span className="small muted"> · current</span>}</button>))}</div>
        <PackingResult key={planId} planId={planId} order={o} />
      </>)}
    </div>
  )
}
