import { useNavigate, useSearchParams } from 'react-router-dom'
import { Empty, ErrorBox, Loading, PlanBadge, Tag } from '../../components/ui'
import { money, PLAN_STATUS, signedMoney, when } from '../../lib/format'
import useFetch from '../../lib/useFetch'

export default function History() {
  const [params, setParams] = useSearchParams()
  const nav = useNavigate()
  const setOpen = (p) => nav(`/admin/orders/${p.order_id}?plan=${p.id}`)
  const cartons = useFetch('/api/admin/cartons')
  const qs = params.toString()
  const { data, error, loading, reload } = useFetch(`/api/admin/history${qs ? `?${qs}` : ''}`)
  const set = (k, v) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); setParams(n) }

  return (
    <div className="pagepad">
      <div className="page-head"><div><h1>Packing results</h1><p className="muted">Every packing plan the engine produced, including superseded, cancelled and no-fit plans. Open one for its inputs, candidate cartons, coordinates and 3D blueprint.</p></div></div>
      <div className="filters">
        <input className="input" placeholder="Order code" defaultValue={params.get('q') || ''} onKeyDown={(e) => e.key === 'Enter' && set('q', e.target.value)} />
        <select className="input" value={params.get('status') || ''} onChange={(e) => set('status', e.target.value)}>
          <option value="">Any status</option>{Object.entries(PLAN_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input className="input" placeholder="Worker" defaultValue={params.get('worker') || ''} onKeyDown={(e) => e.key === 'Enter' && set('worker', e.target.value)} />
        <select className="input" value={params.get('carton') || ''} onChange={(e) => set('carton', e.target.value)}>
          <option value="">Any carton</option>{cartons.data?.map((c) => <option key={c.id} value={c.code}>{c.name}</option>)}
        </select>
        <select className="input" value={params.get('override') || ''} onChange={(e) => set('override', e.target.value)}>
          <option value="">Overrides and normal</option><option value="true">Overrides only</option><option value="false">No overrides</option>
        </select>
        <input className="input" type="date" value={params.get('date_from') || ''} onChange={(e) => set('date_from', e.target.value)} aria-label="From date" />
        <input className="input" type="date" value={params.get('date_to') || ''} onChange={(e) => set('date_to', e.target.value)} aria-label="To date" />
        {qs && <button className="linkbtn" onClick={() => setParams({})}>Clear</button>}
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} retry={reload} />
      {data?.length === 0 && <Empty title="No plans match">Change the filters, or pack an order first.</Empty>}
      {data?.length > 0 && (
        <div className="table-wrap"><table className="table clickable">
          <thead><tr><th>Plan</th><th>Order</th><th>Status</th><th>Carton</th><th className="num">Est. cost</th><th className="num">Saving</th><th>Worker</th><th>Created</th></tr></thead>
          <tbody>{data.map((p) => (
            <tr key={p.id} onClick={() => setOpen(p)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && setOpen(p)}>
              <td>#{p.id}{p.is_override && <Tag kind="sample">override</Tag>}</td><td><b>{p.order_code}</b></td><td><PlanBadge status={p.status} /></td>
              <td>{p.carton?.name || '—'}</td><td className="num">{money(p.estimated_cost)}</td><td className="num">{signedMoney(p.estimated_savings)}</td>
              <td className="small">{p.accepted_by || p.created_by}</td><td className="small">{when(p.created_at)}</td></tr>))}</tbody>
        </table></div>)}
    </div>
  )
}
