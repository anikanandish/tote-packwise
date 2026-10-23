import { useState } from 'react'
import { Empty, ErrorBox, Loading, Stat, Tag } from '../../components/ui'
import { litres, mm3, money, pct, signedMoney, when } from '../../lib/format'
import useFetch from '../../lib/useFetch'

export function Reports() {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [carton, setCarton] = useState('')
  const [code, setCode] = useState('')
  const cartons = useFetch('/api/admin/cartons')
  const qs = new URLSearchParams()
  if (from) qs.set('date_from', from)
  if (to) qs.set('date_to', to)
  if (carton) qs.set('carton', carton)
  if (code) qs.set('q', code)
  const { data: r, error, loading, reload } = useFetch(`/api/admin/reports?${qs}`)

  const csv = () => {
    const cols = ['order_code', 'completed_at', 'carton', 'actual_cost', 'estimated_cost', 'sample_priced', 'baseline_carton', 'baseline_cost', 'savings', 'utilization', 'void_cm3', 'carton_volume_cm3', 'baseline_volume_cm3', 'volume_reduction_cm3', 'board_m2_est', 'override']
    const lines = [cols.join(','), ...r.rows.map((row) => cols.map((c) => row[c] ?? '').join(','))]
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }))
    a.download = 'packwise-report.csv'
    a.click()
  }
  const s = r?.sustainability

  return (
    <div className="pagepad">
      <div className="page-head">
        <div><h1>Reports & sustainability</h1><p className="muted">Packed orders only. Costs and sizes come from each plan's frozen snapshot, so later catalogue edits never change past rows.</p></div>
        {r?.rows.length > 0 && <button className="btn btn-quiet" onClick={csv}>Download CSV</button>}
      </div>
      <div className="filters">
        <label className="small">From <input className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label className="small">To <input className="input" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <select className="input" value={carton} onChange={(e) => setCarton(e.target.value)} aria-label="Carton">
          <option value="">All cartons</option>{cartons.data?.map((c) => <option key={c.id} value={c.code}>{c.name}</option>)}</select>
        <input className="input" placeholder="Order code" defaultValue={code} onKeyDown={(e) => e.key === 'Enter' && setCode(e.target.value.trim())} onBlur={(e) => setCode(e.target.value.trim())} aria-label="Order code" />
        {(from || to || carton || code) && <button className="linkbtn" onClick={() => { setFrom(''); setTo(''); setCarton(''); setCode('') }}>Clear</button>}
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} retry={reload} />
      {r && (<>
        {r.sample_priced_orders > 0 && <p className="note-line"><Tag kind="sample">sample prices</Tag> {r.sample_priced_orders} of {r.totals.orders} orders used a carton whose price is still a sample value, so their costs and savings are sample figures too.</p>}
        <div className="stats">
          <Stat label="Orders packed" value={r.totals.orders} tone="ink" />
          <Stat label="Actual packaging cost" value={money(r.totals.actual_cost)} note="Carton + materials recorded at packing" />
          <Stat label="Saved vs baseline" value={signedMoney(r.totals.savings)} note={`${r.totals.comparable_orders} comparable orders`} tone="peach" />
          <Stat label="Average utilisation" value={pct(r.totals.avg_utilization)} note="Product volume ÷ carton volume" />
        </div>

        <h2 className="block-title">Packaging volume and material</h2>
        <div className="sus-grid">
          <div className="sus-card"><Tag kind="calc">calculated</Tag><p className="sus-v">{litres(s.calculated.carton_volume_cm3)}</p><p>Carton volume shipped</p></div>
          <div className="sus-card"><Tag kind="calc">calculated</Tag><p className="sus-v">{litres(s.calculated.volume_reduction_cm3)}</p><p>Volume avoided vs baseline carton ({s.calculated.comparable_orders} orders the baseline could also hold)</p></div>
          <div className="sus-card"><Tag kind="est">estimate</Tag><p className="sus-v">{litres(s.estimated.void_cm3)}</p><p>Empty space inside the boxes (bounding-box products)</p></div>
          <div className="sus-card"><Tag kind="est">estimate</Tag><p className="sus-v">{s.estimated.board_m2 == null ? '—' : `${s.estimated.board_m2.toFixed(2)} m²`}</p>
            <p>Cardboard in the cartons used{s.estimated.baseline_board_m2 != null && ` (baseline cartons would use ${s.estimated.baseline_board_m2.toFixed(2)} m²)`}</p></div>
          <div className="sus-card"><Tag kind="calc">recorded</Tag><p className="sus-v">{s.estimated.void_fill_sheets}</p><p>Kraft void-fill sheets recorded as used</p></div>
        </div>

        {r.carton_usage.length > 0 && (<>
          <h2 className="block-title">Carton usage</h2>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Carton</th><th className="num">Orders</th><th className="num">Volume shipped</th><th className="num">Packaging cost</th></tr></thead>
            <tbody>{r.carton_usage.map((u) => <tr key={u.code}><td><b>{u.name}</b> <span className="muted small">{u.code}</span></td><td className="num">{u.orders}</td><td className="num">{litres(u.volume_cm3)}</td><td className="num">{money(u.cost)}</td></tr>)}</tbody>
          </table></div>
        </>)}

        <h2 className="block-title">Orders</h2>
        {r.rows.length === 0 ? <Empty title="No packed orders match">Complete a packing plan, or change the filters.</Empty> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Order</th><th>Packed</th><th>Carton</th><th className="num">Estimated</th><th className="num">Actual</th><th>Baseline</th><th className="num">Saving</th><th className="num">Utilisation</th><th className="num">Volume avoided</th></tr></thead>
            <tbody>{r.rows.map((x) => (
              <tr key={x.plan_id}><td><b>{x.order_code}</b>{x.override && <Tag kind="sample">override</Tag>}</td><td className="small">{when(x.completed_at)}</td>
                <td>{x.carton_name || x.carton}{x.sample_priced && <div><Tag kind="sample">sample price</Tag></div>}</td><td className="num">{money(x.estimated_cost)}</td><td className="num">{money(x.actual_cost)}</td>
                <td className="small">{x.baseline_carton ? `${x.baseline_carton} ${money(x.baseline_cost)}` : 'Unavailable'}</td>
                <td className={`num ${x.savings < 0 ? 'neg' : ''}`}>{signedMoney(x.savings)}</td><td className="num">{pct(x.utilization)}</td><td className="num">{litres(x.volume_reduction_cm3)}</td></tr>))}</tbody>
          </table></div>)}
        {r.materials.length > 0 && (<>
          <h2 className="block-title">Protective material recorded as used</h2>
          <div className="table-wrap"><table className="table"><thead><tr><th>Material</th><th className="num">Quantity</th><th className="num">Cost</th></tr></thead>
            <tbody>{r.materials.map((m) => <tr key={m.name}><td>{m.name}</td><td className="num">{m.quantity} {m.unit}</td><td className="num">{money(m.cost)}</td></tr>)}</tbody></table></div>
        </>)}
        <section className="assumptions">
          <h2 className="block-title">How these numbers are calculated</h2>
          <p className="small"><Tag kind="calc">calculated</Tag> exact arithmetic on stored sizes and records · <Tag kind="est">estimate</Tag> depends on a simplifying rule below</p>
          <ul>{r.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        </section>
      </>)}
    </div>
  )
}

export function Settings() {
  const { data: s, error, loading, reload } = useFetch('/api/admin/settings')
  if (loading) return <Loading />
  return (
    <div className="pagepad">
      <div className="page-head"><div><h1>Settings</h1><p className="muted">Read-only view of the rules in force. Change them in <code>backend/.env</code> and restart the API.</p></div>
        <button className="btn btn-quiet" onClick={reload}>Re-check engine</button></div>
      <ErrorBox error={error} />
      {s && (<div className="dash-grid">
        <section className="panel">
          <h3>Packing engine</h3>
          <p className={s.engine.status === 'ok' ? 'okline' : 'err'}>{s.engine.status === 'ok' ? `Connected at ${s.packer_url}` : s.engine.error}</p>
          {s.engine.capabilities && <dl className="kv">{Object.entries(s.engine.capabilities).map(([k, v]) => <div key={k}><dt>{k.replace(/_/g, ' ')}</dt><dd>{String(Array.isArray(v) ? v.join(', ') : v)}</dd></div>)}</dl>}
        </section>
        <section className="panel">
          <h3>Packing rules</h3>
          <dl className="kv">
            <div><dt>Fragile minimum padding</dt><dd>{s.rules.fragile_min_padding_cm} cm each side</dd></div>
            <div><dt>Void-fill material</dt><dd>{s.rules.void_fill_material_code}, 1 unit per {s.rules.void_fill_cm3_per_unit} cm³ empty (estimate)</dd></div>
            <div><dt>Rounding</dt><dd>{s.rules.rounding}</dd></div>
            <div><dt>Selection</dt><dd>{s.rules.selection}</dd></div>
            <div><dt>Units</dt><dd>{s.rules.units}</dd></div>
            <div><dt>Weight</dt><dd>{s.rules.weight}</dd></div>
            <div><dt>Layout inside a carton</dt><dd>{s.rules.layout}</dd></div>
            <div><dt>Worker code</dt><dd>{s.worker_code_configured ? 'Configured' : 'Not set: workers cannot sign in'}</dd></div>
            <div><dt>Admin access code</dt><dd>{s.admin_code_configured ? 'Configured (never shown)' : 'Not set'}</dd></div>
            <div><dt>Session length</dt><dd>{s.session_hours} hours</dd></div>
          </dl>
        </section>
        <section className="panel">
          <h3>Baseline carton</h3>
          {s.baseline_carton ? <p>{s.baseline_carton.name}, internal {mm3(s.baseline_carton.internal_mm)}, at {money(s.baseline_carton.unit_cost)}{s.baseline_carton.sample_fields?.includes('unit_cost') && ' (sample price)'}. Savings everywhere are measured against this carton. Change it from the Cartons page.</p>
            : <p className="err">No baseline carton is set, so savings show as unavailable.</p>}
        </section>
      </div>)}
    </div>
  )
}
