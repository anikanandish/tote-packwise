// Admin overview. Every number is read from stored orders, plans, completions and stock.
import { Link } from 'react-router-dom'
import { Bars, Empty, ErrorBox, Loading, Stat, Tag } from '../../components/ui'
import { ACTION_LABEL, litres, money, pct, signedMoney, when } from '../../lib/format'
import useFetch from '../../lib/useFetch'

function StockBars({ rows }) {
  if (!rows.length) return <p className="muted">No active cartons.</p>
  const max = Math.max(...rows.map((r) => Math.max(r.stock, r.min_stock)), 1)
  return (
    <ul className="stockbars">{rows.map((r) => (
      <li key={r.id} className={r.low ? 'low' : ''}>
        <span className="sb-name" title={r.name}>{r.name}</span>
        <span className="sb-track" aria-hidden>
          <span className="sb-fill" style={{ width: `${(Math.max(r.available, 0) / max) * 100}%` }} />
          {r.reserved > 0 && <span className="sb-res" style={{ width: `${(r.reserved / max) * 100}%` }} />}
          <span className="sb-min" style={{ left: `${(r.min_stock / max) * 100}%` }} title={`Minimum ${r.min_stock}`} />
        </span>
        <span className="sb-num">{r.available}{r.sample_stock && <Tag kind="sample">sample</Tag>}{r.reserved > 0 && <small> +{r.reserved} reserved</small>}</span>
      </li>))}</ul>
  )
}

export default function Dashboard() {
  const { data: d, error, loading, reload } = useFetch('/api/admin/dashboard')
  if (loading) return <Loading label="Loading overview" />
  if (error) return <div className="pagepad"><ErrorBox error={error} retry={reload} /></div>
  const c = d.completed
  const q = d.data_quality
  const lowCartons = d.carton_stock.filter((x) => x.low)
  return (
    <div className="pagepad">
      <div className="page-head">
        <div><h1>Overview</h1><p className="muted">Calculated from stored orders, packing plans, completions and stock. Nothing here is a projection.</p></div>
        <button className="btn btn-quiet" onClick={reload}>Refresh</button>
      </div>

      <div className="stats">
        <Stat label="Orders" value={d.orders.total} note={`${d.orders.packed} packed · ${d.orders.in_progress} packing now`} tone="ink" />
        <Stat label="Awaiting packing" value={d.orders.awaiting_packing} note={`${d.orders.awaiting_recommendation} not planned yet · ${d.orders.fragile_open} fragile`} tone={d.orders.awaiting_packing ? 'peach' : undefined} />
        <Stat label="Packaging cost, packed orders" value={money(c.actual_cost_total)} note={c.count ? `${money(c.actual_cost_avg)} per order on average` : 'No packed orders yet'} />
        <Stat label="Saved vs baseline carton" value={signedMoney(c.savings_total)} note={c.savings_comparable_orders ? `${c.savings_comparable_orders} comparable orders` : 'Needs a packed, comparable order'} />
        <Stat label="No-fit orders" value={d.no_fit_count} note="No active carton could hold them" tone={d.no_fit_count ? 'peach' : undefined} />
      </div>

      {(q.unverified_internal > 0 || q.no_max_weight > 0 || q.sample_values > 0) && (
        <div className="quality-strip">
          <b>Carton data to confirm:</b>
          {q.unverified_internal > 0 && <span>{q.unverified_internal} of {q.standard_cartons} standard cartons use nominal size (internal size not measured)</span>}
          {q.no_max_weight > 0 && <span>{q.no_max_weight} active cartons have no maximum weight, so weight is not checked for them</span>}
          {q.sample_values > 0 && <span>{q.sample_values} cartons still hold sample stock or prices</span>}
          <Link to="/admin/cartons" className="linkbtn">Review cartons</Link>
        </div>)}

      <div className="dash-grid">
        <section className="panel span-2">
          <div className="panel-head"><h3>Packaging cost by day</h3><span className="small muted">packed orders · ₹</span></div>
          <Bars data={d.series.by_day} x="date" y="cost" format={(v) => `₹${Math.round(v)}`} />
        </section>
        <section className="panel">
          <div className="panel-head"><h3>Packing efficiency</h3><Link to="/admin/reports" className="linkbtn">Reports</Link></div>
          <dl className="kv">
            <div><dt>Average box utilisation</dt><dd>{pct(c.avg_utilization)} <Tag kind="calc">calculated</Tag></dd></div>
            <div><dt>Carton volume avoided vs baseline</dt><dd>{litres(c.volume_reduction_cm3_total)} <Tag kind="calc">calculated</Tag></dd></div>
            <div><dt>Average empty space per box</dt><dd>{litres(c.avg_void_cm3)} <Tag kind="est">estimate</Tag></dd></div>
          </dl>
        </section>
        <section className="panel span-2">
          <div className="panel-head"><h3>Carton stock</h3><span className="small muted">available · reserved · marker = low-stock threshold</span>
            <Link to="/admin/cartons" className="linkbtn">Cartons</Link></div>
          <StockBars rows={d.carton_stock} />
        </section>
        <section className="panel">
          <div className="panel-head"><h3>Low stock</h3></div>
          {d.low_stock.length === 0 ? <p className="muted">Everything is above its minimum.</p> : (
            <ul className="list">{d.low_stock.map((a) => (
              <li key={`${a.type}${a.id}`} className={a.out ? 'bad' : 'warnline'}><b>{a.name}</b> <span className="muted small">{a.type}</span>
                <span className="right">{a.available} available · min {a.min_stock}</span></li>))}</ul>)}
          {lowCartons.length === 0 && d.low_stock.length > 0 && <p className="small muted">All cartons are above their minimum.</p>}
        </section>
        <section className="panel">
          <div className="panel-head"><h3>Cartons used</h3></div>
          <Bars data={d.series.carton_mix} x="carton" y="count" />
        </section>
        <section className="panel">
          <div className="panel-head"><h3>No-fit and failures</h3><Link to="/admin/orders?packing=no_fit" className="linkbtn">No-fit orders</Link></div>
          {d.failures.length === 0 ? <p className="muted">No failures recorded.</p> : (
            <ul className="list">{d.failures.map((f) => (
              <li key={f.id}><b>{ACTION_LABEL[f.action] || f.action}</b> {f.order_code && <span>· {f.order_code}</span>}
                <span className="right muted small">{when(f.created_at)}</span>
                {f.details?.error && <p className="small muted">{f.details.error}</p>}</li>))}</ul>)}
        </section>
        <section className="panel">
          <div className="panel-head"><h3>Carton overrides</h3></div>
          {d.overrides.length === 0 ? <p className="muted">No overrides yet.</p> : (
            <ul className="list">{d.overrides.map((o) => (
              <li key={o.id}><b>{o.order_code}</b> {o.from} → {o.to} <span className="right muted small">{o.actor}</span>
                <p className="small">“{o.reason}”</p></li>))}</ul>)}
        </section>
        <section className="panel span-2">
          <div className="panel-head"><h3>Recent activity</h3><Link to="/admin/orders" className="linkbtn">Orders</Link></div>
          {d.recent_activity.length === 0 ? <Empty title="Quiet so far" /> : (
            <ul className="list">{d.recent_activity.map((e) => (
              <li key={e.id}>{ACTION_LABEL[e.action] || e.action.replace(/_/g, ' ')} {e.order_code && <b>{e.order_code}</b>} <span className="muted small">{e.actor}</span>
                <span className="right muted small">{when(e.created_at)}</span></li>))}</ul>)}
        </section>
      </div>
    </div>
  )
}
