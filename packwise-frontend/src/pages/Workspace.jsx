// Guided packing for one order:  Ready (auto carton)  ->  Slides  ->  Packed.
// Every carton, cost and placement shown here comes from the backend plan, which comes
// from the C++ engine. All inventory rules stay on the server.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Carton3D from '../components/Carton3D'
import { ErrorBox, Field, Loading, Modal, OrderBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { api } from '../lib/api'
import { ACTION_LABEL, kg, money, signedMoney, when } from '../lib/format'
import { buildSlides, cartonTitle, colorsFor, fillOf } from '../lib/packPlan'
import useFetch from '../lib/useFetch'
import PackSlides from './pack/PackSlides'
import ReadyView, { ChangeCarton } from './pack/ReadyView'

const PENDING = ['placed', 'awaiting_packing']
const PACKED = ['packed', 'ready_for_dispatch', 'dispatched']

const slideKey = (planId) => `packwise.slide.${planId}`
const readSlide = (planId) => { try { return Number(sessionStorage.getItem(slideKey(planId))) || 0 } catch { return 0 } }
const saveSlide = (planId, i) => { try { sessionStorage.setItem(slideKey(planId), String(i)) } catch { /* ignore */ } }

async function nextOrderId(excludeId) {
  const list = await api('/api/packwise/orders?group=pending')
  return list.find((o) => o.id !== excludeId)?.id ?? null
}

// ------------------------------------------------------------------ no carton fits
function NoFit({ plan, busy, onRetry }) {
  const reasons = plan.blockers.length ? plan.blockers
    : plan.evaluations.filter((e) => e.status !== 'inactive').map((e) => `${cartonTitle(e.carton)}: ${e.reasons[0] || 'did not pass'}`)
  return (
    <div className="nofit-panel">
      <h2>No carton can safely hold this order</h2>
      <p>PackWise will not pick a carton that breaks a safety rule. None of the warehouse carton sizes passes every check. Ask a supervisor to restock or split the order, then check again.</p>
      <ul>{reasons.slice(0, 6).map((r, i) => <li key={i}>{r}</li>)}</ul>
      <button className="btn btn-peach btn-lg" disabled={busy} onClick={onRetry}>{busy ? 'Checking…' : 'Check again'}</button>
    </div>
  )
}

// ------------------------------------------------------------------ packed
function Packed({ order, plan, justDone, onNext, nextBusy, reload }) {
  const toast = useToast()
  const history = useFetch(`/api/packwise/orders/${order.id}/history`, [order.status])
  const c = order.completion
  const advance = async (status) => {
    try { await api(`/api/packwise/orders/${order.id}/dispatch`, { method: 'POST', body: { status } }); toast('Order updated'); reload() }
    catch (e) { toast(e.message, 'error') }
  }
  return (
    <div className="packed">
      <div className="packed-main">
        <div className={`packed-hero ${justDone ? 'pop' : ''}`}>
          <span className="big-tick" aria-hidden />
          <div><h2>{order.code} is packed</h2>
            <p>Stock updated and the customer's tracking now shows <b>{order.status === 'packed' ? 'Packed' : order.status.replace(/_/g, ' ')}</b>.</p></div>
        </div>
        {c && (
          <dl className="kv">
            <div><dt>Carton</dt><dd>{plan?.selected ? `${cartonTitle(plan.selected.carton)}, ${plan.selected.carton.dims_cm.join(' × ')} cm` : '—'}</dd></div>
            {fillOf(plan) && <div><dt>Floor used</dt><dd>{Math.round(fillOf(plan).floor * 100)}% (box volume {Math.round(fillOf(plan).padded * 100)}%)</dd></div>}
            <div><dt>Packaging cost</dt><dd>{money(c.actual_cost)}</dd></div>
            <div><dt>Against baseline</dt><dd className={c.actual_savings < 0 ? 'neg' : 'pos'}>{c.actual_savings == null ? 'Unavailable' : `${signedMoney(c.actual_savings)} saved`}</dd></div>
            <div><dt>Packed by</dt><dd>{c.actor.replace(/^worker:/, '')} · {when(c.created_at)}</dd></div>
          </dl>
        )}
        <div className="packed-actions">
          <button className="btn btn-peach btn-xl" disabled={nextBusy} onClick={onNext} autoFocus>{nextBusy ? 'Finding next order…' : 'Pack next order'}</button>
          {order.status === 'packed' && <button className="btn btn-quiet btn-lg" onClick={() => advance('ready_for_dispatch')}>Mark ready for dispatch</button>}
          {order.status === 'ready_for_dispatch' && <button className="btn btn-quiet btn-lg" onClick={() => advance('dispatched')}>Mark dispatched</button>}
        </div>
        <details className="why-box">
          <summary>Order history</summary>
          {history.data && <ol className="audit">{history.data.map((e) => (
            <li key={e.id}><span className="muted small">{when(e.created_at)}</span> <b>{ACTION_LABEL[e.action] || e.action}</b>
              {e.details?.status && ` → ${e.details.status.replace(/_/g, ' ')}`} <span className="muted small">{e.actor}</span></li>))}</ol>}
        </details>
      </div>
      {plan?.selected && <div className="packed-viz"><Carton3D carton={plan.selected.carton.dims_cm} placements={plan.placements} colors={colorsFor(plan, order)} /></div>}
    </div>
  )
}

// ------------------------------------------------------------------ page
function Workspace() {
  const { id } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const { isAdmin } = useAuth()
  const { data: order, error, loading, reload } = useFetch(`/api/packwise/orders/${id}`)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState({}) // per-action errors: { recommend, start, change, finish, stop }
  const [changing, setChanging] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [stopReason, setStopReason] = useState('')
  const [justDone, setJustDone] = useState(false)
  const [nextBusy, setNextBusy] = useState(false)
  const [prio, setPrio] = useState(null)
  const autoTried = useRef(false)

  const plan = order?.current_plan
  const pending = order && PENDING.includes(order.status)
  // Recalculate when there is no current plan, or an open recommendation is older than 10 minutes
  // (stock, catalogue or box-machine settings may have changed since it was made).
  const ageMin = plan ? (Date.now() - new Date(plan.created_at + (plan.created_at.endsWith('Z') ? '' : 'Z')).getTime()) / 60000 : 0
  const stale = pending && (!plan || order.plans[0]?.id !== plan.id
    || (['recommended', 'no_fit'].includes(plan.status) && ageMin > 10))
  const slides = useMemo(() => (plan?.status === 'accepted' ? buildSlides(plan, order) : []), [plan, order])
  const [index, setIndexState] = useState(0)
  useEffect(() => { if (plan?.status === 'accepted') setIndexState(Math.min(readSlide(plan.id), slides.length)) }, [plan?.id, plan?.status, slides.length])
  const setIndex = useCallback((i) => {
    const v = Math.max(0, Math.min(i, slides.length))
    setIndexState(v)
    if (plan) saveSlide(plan.id, v)
  }, [plan, slides.length])

  const run = useCallback(async (key, fn, okMsg) => {
    setBusy(true); setErr({})
    try { const r = await fn(); if (okMsg) toast(okMsg); await reload(); return r ?? true }
    catch (e) { setErr({ [key]: e }); await reload(); return false }
    finally { setBusy(false) }
  }, [reload, toast])

  const recommend = useCallback((key = 'recommend') => run(key, () => api(`/api/packwise/orders/${id}/recommend`, { method: 'POST' })), [id, run])

  // Open an order -> the carton is chosen automatically.
  useEffect(() => {
    if (stale && !autoTried.current) { autoTried.current = true; recommend() }
  }, [stale, recommend])

  const start = () => run('start', () => api(`/api/packwise/plans/${plan.id}/accept`, { method: 'POST' })).then((ok) => { if (ok) { saveSlide(plan.id, 0); setIndexState(0) } })
  const override = async (cartonId, reason) => {
    const ok = await run('change', () => api(`/api/packwise/plans/${plan.id}/override`, { method: 'POST', body: { carton_id: cartonId, reason } }), 'Carton changed. Press Start packing.')
    if (ok) setChanging(false)
  }
  const recalc = async (key = 'change') => { const ok = await recommend(key); if (ok) setChanging(false) }
  const stop = async () => {
    const ok = await run('stop', () => api(`/api/packwise/plans/${plan.id}/cancel`, { method: 'POST', body: { reason: stopReason.trim() } }), 'Packing stopped. Reserved stock released.')
    if (ok) { setStopping(false); setStopReason(''); autoTried.current = false }
  }
  const complete = async (body) => {
    const r = await run('finish', () => api(`/api/packwise/plans/${plan.id}/complete`, { method: 'POST', body }))
    if (r) setJustDone(true)
  }
  const next = async () => {
    setNextBusy(true)
    try {
      const nid = await nextOrderId(order.id)
      if (nid) nav(`/orders/${nid}`)
      else { toast('No more orders waiting. Nice work.'); nav('/queue') }
    } catch (e) { toast(e.message, 'error') } finally { setNextBusy(false) }
  }
  const savePriority = async () => {
    try {
      await api(`/api/admin/orders/${order.id}/priority`, { method: 'POST', body: { priority: !order.priority, reason: prio.trim() } })
      toast(order.priority ? 'Priority removed' : 'Marked as priority'); setPrio(null); reload()
    } catch (e) { toast(e.message, 'error') }
  }

  if (loading && !order) return <Loading label="Opening order" />
  if (error) return <div className="pagepad"><ErrorBox error={error} retry={reload} /></div>

  let body
  if (PACKED.includes(order.status)) {
    body = <Packed order={order} plan={plan} justDone={justDone} onNext={next} nextBusy={nextBusy} reload={reload} />
  } else if (plan?.status === 'accepted') {
    body = slides.length ? (
      <PackSlides order={order} plan={plan} slides={slides} index={index} setIndex={setIndex} busy={busy}
        error={err.finish} onComplete={complete} onChange={() => setChanging(true)} onStop={() => setStopping(true)} />
    ) : <ErrorBox error={{ message: 'This plan has no placement data, so packing slides cannot be shown. Stop packing and request a new recommendation.' }} />
  } else if (err.recommend && (stale || !plan)) {
    body = <ErrorBox error={err.recommend} retry={() => recommend()} />
  } else if (stale || (busy && !plan)) {
    body = <div className="finding"><span className="spinner" aria-hidden /><p>Finding the best box…</p><small>The packing algorithm is designing a box around these items and checking sizes, padding, weight and stock.</small></div>
  } else if (plan?.status === 'no_fit') {
    body = <NoFit plan={plan} busy={busy} onRetry={() => recommend()} />
  } else if (plan?.status === 'recommended') {
    body = <ReadyView order={order} plan={plan} busy={busy} error={err.start || err.recommend} onStart={start}
      onChange={() => setChanging(true)} onRecalculate={() => recalc('start')} />
  } else {
    body = <ErrorBox error={{ message: `This order is '${order.status}' and has no active packing plan.` }} retry={reload} />
  }

  return (
    <div className="pagepad ws2">
      <header className="ws-head">
        <Link to="/queue" className="back">Queue</Link>
        <h1>{order.code}</h1>
        <span className="ws-meta">{order.unit_count} {order.unit_count === 1 ? 'item' : 'items'} · {kg(order.weight_g)}</span>
        {order.fragile && <span className="flag flag-frag">Fragile</span>}
        {order.priority && <span className="flag flag-prio" title={order.priority_reason}>Priority</span>}
        <span className="ws-spacer" />
        {plan?.status === 'accepted' && plan.accepted_by && <span className="muted small">Started by {plan.accepted_by.replace(/^worker:/, '')}</span>}
        <OrderBadge status={order.status} />
        {isAdmin && !PACKED.includes(order.status) && <button className="linkbtn small" onClick={() => setPrio('')}>{order.priority ? 'Remove priority' : 'Mark priority'}</button>}
      </header>

      {body}

      {changing && plan && (
        <ChangeCarton plan={plan} busy={busy} error={err.change} onClose={() => setChanging(false)} onOverride={override} onRecalculate={() => recalc('change')} />
      )}

      {stopping && (
        <Modal title="Stop packing this order?" onClose={() => setStopping(false)}>
          <p>The reserved carton and materials go back into stock and the order returns to the queue with a fresh recommendation.</p>
          <div className="chips">
            {['Item missing from the shelf', 'Item damaged', 'Shift ended'].map((r) => <button key={r} className={`chip ${stopReason === r ? 'on' : ''}`} onClick={() => setStopReason(r)}>{r}</button>)}
          </div>
          <Field label="Reason"><input className="input" value={stopReason} onChange={(e) => setStopReason(e.target.value)} /></Field>
          <ErrorBox error={err.stop} />
          <div className="modal-actions">
            <button className="btn btn-quiet" onClick={() => setStopping(false)}>Keep packing</button>
            <button className="btn btn-ink" disabled={stopReason.trim().length < 3 || busy} onClick={stop}>Stop and release stock</button>
          </div>
        </Modal>
      )}
      {prio !== null && (
        <Modal title={order.priority ? 'Remove priority' : 'Mark as priority'} onClose={() => setPrio(null)}>
          <Field label="Reason (kept in the audit log)"><input className="input" value={prio} onChange={(e) => setPrio(e.target.value)} autoFocus /></Field>
          <div className="modal-actions"><button className="btn btn-quiet" onClick={() => setPrio(null)}>Cancel</button>
            <button className="btn btn-ink" disabled={prio.trim().length < 3} onClick={savePriority}>Save</button></div>
        </Modal>
      )}
    </div>
  )
}

// Remount per order so state never leaks between orders (e.g. after "Pack next order").
export default function WorkspaceRoute() {
  const { id } = useParams()
  return <Workspace key={id} />
}
