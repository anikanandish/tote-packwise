import { cartonTitle } from '../lib/packPlan'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Empty, ErrorBox, Loading, OrderBadge, PlanBadge, Stat } from '../components/ui'
import { kg, money, when } from '../lib/format'
import useFetch from '../lib/useFetch'
import { api } from '../lib/api'

const TABS = [['pending', 'To pack'], ['in_progress', 'Packing now'], ['completed', 'Packed'], ['all', 'All']]

export default function Queue() {
  const [tab, setTab] = useState('pending')
  const nav = useNavigate()
  const [nextErr, setNextErr] = useState('')
  const summary = useFetch('/api/packwise/summary')
  const orders = useFetch(`/api/packwise/orders?group=${tab}`)
  const s = summary.data

  const refresh = () => { summary.reload(); orders.reload() }

  return (
    <div className="pagepad worker-dashboard">
      <div className="page-head">
        <div><h1>Order queue</h1><p className="muted">Priority first, then fragile, then oldest. Open any order and the carton is chosen for you.</p></div>
        <div className="head-badges">
          <button className="btn btn-quiet" onClick={refresh}>Refresh</button>
          <button className="btn btn-peach btn-lg" disabled={!s?.pending} onClick={async () => {
            try {
              const list = await api('/api/packwise/orders?group=pending')
              if (list[0]) nav(`/orders/${list[0].id}`); else setNextErr('Nothing waiting to be packed.')
            } catch (e) { setNextErr(e.message) }
          }}>{s?.pending ? 'Pack next order' : 'Queue is clear'}</button>
        </div>
      </div>
      {nextErr && <p className="err">{nextErr}</p>}

      {summary.error && <ErrorBox error={summary.error} retry={summary.reload} />}
      {s && (
        <div className="stats">
          <Stat label="Waiting to pack" value={s.pending} note={`${s.awaiting_recommendation} need a recommendation`} />
          <Stat label="Recommended" value={s.recommended} note="Ready to accept" />
          <Stat label="Packing now" value={s.in_progress} note="Stock reserved" />
          <Stat label="Packed" value={s.completed} />
          <Stat label="Fragile open" value={s.fragile_open} tone={s.fragile_open ? 'peach' : undefined} />
          <Stat label="Priority open" value={s.priority_open} tone={s.priority_open ? 'ink' : undefined} />
        </div>
      )}
      {s?.low_stock?.length > 0 && (
        <div className="alert">
          <strong>Low stock:</strong> {s.low_stock.map((a) => `${a.name} (${a.available} left)`).join(', ')}
        </div>
      )}

      <div className="tabs" role="tablist">
        {TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}
      </div>

      {orders.loading && <Loading label="Loading orders" />}
      {orders.error && <ErrorBox error={orders.error} retry={orders.reload} />}
      {orders.data && orders.data.length === 0 && (
        <Empty title={tab === 'pending' ? 'Nothing waiting to be packed' : 'No orders here'}>
          {tab === 'pending' ? 'New TOTE orders appear here the moment a customer checks out.' : 'Try another tab.'}
        </Empty>
      )}
      {orders.data?.length > 0 && (
        <ul className="queue">
          {orders.data.map((o, index) => (
            <li key={`${tab}:${o.id}`} style={{ '--queue-delay': `${Math.min(index, 10) * 45}ms` }}>
              <Link to={`/orders/${o.id}`} className={`qrow ${o.priority ? 'prio' : ''} ${o.fragile ? 'frag' : ''}`}>
                <div className="qrow-main">
                  <p className="qrow-code">{o.code}</p>
                  <p className="muted small">{when(o.created_at)} · {o.customer}</p>
                </div>
                <div className="qrow-flags">
                  {o.priority && <span className="flag flag-prio" title={o.priority_reason}>Priority</span>}
                  {o.fragile && <span className="flag flag-frag">Fragile</span>}
                </div>
                <div className="qrow-meta"><b>{o.unit_count}</b> units<br /><span className="muted">{kg(o.weight_g)}</span></div>
                <div className="qrow-items small">{o.items.map((i) => `${i.quantity}× ${i.name}`).join(', ')}</div>
                <div className="qrow-status">
                  <OrderBadge status={o.status} />
                  {o.plan && <span className="small"><PlanBadge status={o.plan.status} />{o.plan.carton && ` ${cartonTitle(o.plan.carton)} · ${money(o.plan.estimated_cost)}`}</span>}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
