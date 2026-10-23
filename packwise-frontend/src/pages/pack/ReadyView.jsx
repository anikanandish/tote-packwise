// First screen of an order: the recommended carton, what to grab, warnings, Start packing.
import { useMemo, useState } from 'react'
import Carton3D from '../../components/Carton3D'
import CartonShelf from '../../components/CartonShelf'
import { FloorPlan } from '../../components/PackViews'
import { readView, saveView } from '../../lib/viewPref'
import { ErrorBox, Field, Modal } from '../../components/ui'
import { dims, money, signedMoney } from '../../lib/format'
import { boxNo, cartonTitle, colorsFor, fillOf, setupLine, shortName } from '../../lib/packPlan'

const QUICK_REASONS = [
  'Recommended carton is damaged',
  'Recommended size is not at my bench',
  'Items need more room than planned',
]

export function ChangeCarton({ plan, busy, error, onOverride, onRecalculate, onClose }) {
  const [pick, setPick] = useState(null)
  const [reason, setReason] = useState('')
  const current = plan.selected?.carton
  const options = plan.evaluations
    .filter((e) => e.status === 'feasible' && e.carton.id !== current?.id)
    .sort((a, b) => a.carton.volume_cm3 - b.carton.volume_cm3)
  const curCost = plan.selected?.cost?.total
  const curVol = current?.volume_cm3

  return (
    <Modal title="Change carton" onClose={onClose}>
      <p className="muted">Only cartons that pass every safety check for this order are listed, smallest first. A bigger box ships more air, so your reason is saved with the order.</p>
      {options.length === 0 ? (
        <div className="empty small-empty">
          <p><b>No other carton passes the checks for this order.</b></p>
          {plan.is_override && <p>This plan came from an override, so only that carton was re-checked. Run the recommendation again to see every option.</p>}
        </div>
      ) : (
        <div className="choice-list" role="radiogroup" aria-label="Valid cartons">
          {options.map((e) => {
            const diff = curCost != null && e.cost?.total != null ? e.cost.total - curCost : null
            return (
              <button key={e.carton.id} role="radio" aria-checked={pick === e.carton.id}
                className={`choice ${pick === e.carton.id ? 'on' : ''}`} onClick={() => setPick(e.carton.id)}>
                <span className="choice-name">{cartonTitle(e.carton)}</span>
                <span className="muted">{dims(e.carton.dims_cm)}{curVol ? ` · ${(e.carton.volume_cm3 / curVol).toFixed(1)}× the space` : ''}</span>
                <span className="choice-cost">{money(e.cost?.total)}{diff != null && <small> {diff >= 0 ? '+' : '−'}{money(Math.abs(diff))}</small>}</span>
              </button>
            )
          })}
        </div>
      )}
      {options.length > 0 && (<>
        <p className="field-label-strong">Why?</p>
        <div className="chips">
          {QUICK_REASONS.map((r) => <button key={r} className={`chip ${reason === r ? 'on' : ''}`} onClick={() => setReason(r)}>{r}</button>)}
        </div>
        <Field label="Or type a reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </>)}
      <ErrorBox error={error} />
      <div className="modal-actions spread">
        <button className="btn btn-quiet" disabled={busy || plan.status !== 'recommended'} onClick={onRecalculate}
          title={plan.status !== 'recommended' ? 'Stop packing first to recalculate' : undefined}>Recalculate</button>
        <button className="btn btn-ink" disabled={!pick || reason.trim().length < 10 || busy}
          onClick={() => onOverride(pick, reason.trim())}>{busy ? 'Checking…' : 'Use this carton'}</button>
      </div>
    </Modal>
  )
}

function WhyCarton({ plan }) {
  const rejected = plan.evaluations.filter((e) => e.status !== 'feasible' && e.carton.volume_cm3 < plan.selected.carton.volume_cm3)
  return (
    <details className="why-box">
      <summary>Why this carton?</summary>
      <ul>
        {(plan.selected.why || []).map((w, i) => <li key={i}>{w}</li>)}
        {(plan.warnings || []).map((w, i) => <li key={`w${i}`} className="warnline">{w}</li>)}
        {rejected.filter((e) => e.status !== 'inactive').map((e) => <li key={e.carton.id}><b>{cartonTitle(e.carton)}</b>: {e.reasons[0] || 'did not pass the checks'}</li>)}
        <li>Estimated packaging cost {money(plan.estimated_cost)}
          {plan.baseline?.available ? `, ${signedMoney(plan.estimated_savings)} against the ${plan.baseline.carton.name} baseline` : ''}.</li>
      </ul>
    </details>
  )
}

export default function ReadyView({ order, plan, busy, error, onStart, onChange, onRecalculate }) {
  const carton = plan.selected.carton
  const fragileRefs = useMemo(() => new Set(plan.units.filter((u) => u.fragile).map((u) => u.ref)), [plan])
  const colors = useMemo(() => colorsFor(plan, order), [plan, order])
  const fill = fillOf(plan)
  const [view, setView] = useState(readView)
  const pick = (v) => { setView(v); saveView(v) }
  const special = order.items.filter((i) => i.packaging.fragile || i.packaging.restrictions || i.packaging.orientation === 'upright')
  const mats = plan.selected.materials

  return (
    <div className="ready-wrap">
    <CartonShelf plan={plan} />
    <div className="ready">
      <section className="ready-main">
        <div className="carton-hero">
          <div className="ch-top">
            {boxNo(carton) && <span className="ch-no" aria-label={`Box number ${boxNo(carton)}`}>{boxNo(carton)}</span>}
            <div>
              <p className="ch-label">Take box</p>
              <p className="ch-name">{carton.name}</p>
            </div>
          </div>
          <p className="ch-dims">{dims(carton.dims_cm)}</p>
          <p className="ch-setup">{setupLine(carton.dims_cm)}</p>
          {fill && (
            <div className="fill" aria-label={`Floor used ${Math.round(fill.floor * 100)} percent`}>
              <div className="fill-bar"><span style={{ width: `${Math.round(fill.floor * 100)}%` }} /></div>
              <p><b>{Math.round(fill.floor * 100)}% of the floor used</b> by items and their padding</p>
              <p className="fill-sub">Box volume used {Math.round(fill.padded * 100)}% · one layer, so the tallest item sets the height</p>
            </div>
          )}
        </div>

        <div className="grab">
          <p className="grab-title">Grab</p>
          <ul>
            <li><b>1</b> {cartonTitle(carton)}</li>
            {mats.map((m) => <li key={m.code}><b>{m.estimate ? '~' : ''}{m.quantity}</b> {m.name.toLowerCase()}</li>)}
          </ul>
        </div>

        {special.length > 0 && (
          <ul className="heads-up" aria-label="Handling warnings">
            {special.map((i) => (
              <li key={i.product_id} className={i.packaging.fragile ? 'frag' : ''}>
                <b>{i.packaging.fragile ? 'Fragile' : 'Careful'}: {shortName(i.name)}{i.quantity > 1 ? ` ×${i.quantity}` : ''}</b>
                <span>{i.packaging.handling_instructions}{i.packaging.restrictions ? ` ${i.packaging.restrictions}` : ''}</span>
              </li>
            ))}
          </ul>
        )}

        {error && (
          <div className="errorbox" role="alert">
            <strong>Could not start packing</strong>
            <p>{error.message}</p>
            <button className="btn btn-quiet" disabled={busy} onClick={onRecalculate}>Get a fresh recommendation</button>
          </div>
        )}

        <button className="btn btn-peach btn-xl" disabled={busy} onClick={onStart} autoFocus>
          {busy ? 'Reserving carton…' : 'Start packing'}
        </button>
        <div className="ready-links">
          <button className="linkbtn" onClick={onChange}>Change carton</button>
          <WhyCarton plan={plan} />
        </div>
      </section>

      <section className="ready-viz" aria-label="Packed arrangement preview">
        <div className="seg seg-small" role="tablist" aria-label="View">
          <button role="tab" aria-selected={view === 'top'} className={view === 'top' ? 'on' : ''} onClick={() => pick('top')}>Top view</button>
          <button role="tab" aria-selected={view === '3d'} className={view === '3d' ? 'on' : ''} onClick={() => pick('3d')}>3D</button>
        </div>
        {view === '3d'
          ? <Carton3D carton={carton.dims_cm} placements={plan.placements} fragileRefs={fragileRefs} colors={colors} />
          : <FloorPlan carton={carton.dims_cm} placements={plan.placements} fragileRefs={fragileRefs} names />}
        <p className="muted small center">
          {plan.placements.length} {plan.placements.length === 1 ? 'item' : 'items'} in one layer, as planned by the packing engine. Nothing is stacked.
          {plan.is_override && ' Carton chosen by override.'}
        </p>
      </section>
    </div>
    </div>
  )
}
