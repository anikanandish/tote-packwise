import { useNavigate, useSearchParams } from 'react-router-dom'
import { Empty, ErrorBox, Loading, OrderBadge, PlanBadge, Tag } from '../../components/ui'
import { cartonTitle } from '../../lib/packPlan'
import { money, ORDER_STATUS, pct, when } from '../../lib/format'
import useFetch from '../../lib/useFetch'

export default function Orders() {
  const [params, setParams] = useSearchParams()
  const nav = useNavigate()
  const cartons = useFetch('/api/admin/cartons')
  const qs = params.toString()
  const { data, error, loading, reload } = useFetch(`/api/admin/orders${qs ? `?${qs}` : ''}`)
  const set = (k, v) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); setParams(n) }
  const open = (id) => nav(`/admin/orders/${id}`)

  return (
    <div className="pagepad">
      <div className="page-head">
        <div><h1>Orders</h1><p className="muted">Every TOTE order, with the carton and packing result PackWise recorded for it.</p></div>
        <button className="btn btn-quiet" onClick={reload}>Refresh</button>
      </div>
      <div className="filters">
        <input className="input" placeholder="Order code, customer name or email" defaultValue={params.get('q') || ''}
          onKeyDown={(e) => e.key === 'Enter' && set('q', e.target.value.trim())} onBlur={(e) => set('q', e.target.value.trim())} aria-label="Search orders" />
        <select className="input" value={params.get('status') || ''} onChange={(e) => set('status', e.target.value)} aria-label="Order status">
          <option value="">Any order status</option>{Object.entries(ORDER_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select className="input" value={params.get('packing') || ''} onChange={(e) => set('packing', e.target.value)} aria-label="Packing result">
          <option value="">Any packing result</option><option value="no_plan">Not planned yet</option><option value="no_fit">No carton fits</option><option value="override">Carton overridden</option></select>
        <select className="input" value={params.get('carton') || ''} onChange={(e) => set('carton', e.target.value)} aria-label="Carton">
          <option value="">Any carton</option>{cartons.data?.map((c) => <option key={c.id} value={c.code}>{c.name}</option>)}</select>
        <input className="input" type="date" value={params.get('date_from') || ''} onChange={(e) => set('date_from', e.target.value)} aria-label="From date" />
        <input className="input" type="date" value={params.get('date_to') || ''} onChange={(e) => set('date_to', e.target.value)} aria-label="To date" />
        {qs && <button className="linkbtn" onClick={() => setParams({})}>Clear filters</button>}
      </div>
      {loading && <Loading label="Loading orders" />}
      <ErrorBox error={error} retry={reload} />
      {data?.length === 0 && <Empty title={qs ? 'No orders match these filters' : 'No orders yet'}>{qs ? 'Change or clear the filters.' : 'Orders placed in the TOTE shop appear here straight away.'}</Empty>}
      {data?.length > 0 && (<>
        <p className="small muted">{data.length} {data.length === 1 ? 'order' : 'orders'}</p>
        <div className="table-wrap"><table className="table clickable">
          <thead><tr><th>Order</th><th>Placed</th><th>Customer</th><th className="num">Items</th><th>Status</th><th>Packing result</th><th className="num">Packaging est.</th><th className="num">Box filled</th></tr></thead>
          <tbody>{data.map((o) => (
            <tr key={o.id} tabIndex={0} onClick={() => open(o.id)} onKeyDown={(e) => e.key === 'Enter' && open(o.id)}>
              <td><b>{o.code}</b><div className="tags">{o.fragile && <Tag kind="warn">Fragile</Tag>}{o.priority && <Tag kind="base">Priority</Tag>}</div></td>
              <td className="small">{when(o.created_at)}</td>
              <td>{o.customer}<div className="small muted">{money(o.total)}</div></td>
              <td className="num">{o.units}</td>
              <td><OrderBadge status={o.status} /></td>
              <td>{o.plan ? <><PlanBadge status={o.plan.status} />{o.plan.carton_code && <div className="small">{cartonTitle({ code: o.plan.carton_code, name: o.plan.carton_name })}</div>}
                {o.has_override && <div><Tag kind="sample">override</Tag></div>}</> : <span className="muted small">Not planned yet</span>}</td>
              <td className="num">{o.plan ? money(o.plan.estimated_cost) : '—'}</td>
              <td className="num">{o.plan ? pct(o.plan.utilization) : '—'}</td>
            </tr>))}</tbody>
        </table></div>
      </>)}
    </div>
  )
}
