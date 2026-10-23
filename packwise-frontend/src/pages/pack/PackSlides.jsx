// Slide-by-slide packing: one slide per product (identical items placed one after another
// share a slide), then a single Finish slide. Positions come from the engine's placements.
import { useEffect, useMemo, useState } from 'react'
import Carton3D from '../../components/Carton3D'
import { FloorPlan } from '../../components/PackViews'
import ProductArt from '../../components/ProductArt'
import { colorsFor, setupShort, cartonTitle } from '../../lib/packPlan'
import { readView, saveView } from '../../lib/viewPref'


function Progress({ slides, index, onJump }) {
  return (
    <div className="progress" aria-label={`Step ${index + 1} of ${slides.length + 1}`}>
      <ol>
        {slides.map((s, i) => (
          <li key={i}><button className={i < index ? 'done' : i === index ? 'now' : ''} onClick={() => onJump(i)}
            aria-label={`Step ${i + 1}: ${s.name}`} aria-current={i === index ? 'step' : undefined} /></li>
        ))}
        <li><button className={index === slides.length ? 'now' : ''} onClick={() => onJump(slides.length)} aria-label="Finish" /></li>
      </ol>
      <span>{index < slides.length ? `Item ${index + 1} of ${slides.length}` : 'Finish'}</span>
    </div>
  )
}

function Stepper({ value, onChange, label, unit }) {
  return (
    <div className="mstep">
      <span>{label}</span>
      <div className="mstep-ctl">
        <button type="button" onClick={() => onChange(Math.max(0, value - 1))} aria-label={`Fewer ${label}`}>−</button>
        <b>{value}</b>
        <button type="button" onClick={() => onChange(value + 1)} aria-label={`More ${label}`}>+</button>
        <small>{unit}</small>
      </div>
    </div>
  )
}

function Finish({ plan, order, busy, error, onComplete }) {
  const fragile = plan.units.some((u) => u.fragile)
  const reserved = plan.reservations.filter((r) => r.item_type === 'material' && r.status === 'active')
  const mats = Object.fromEntries(plan.selected.materials.map((m) => [m.code, m]))
  const voidFill = plan.selected.materials.find((m) => m.purpose === 'void_fill')
  const [checks, setChecks] = useState({ count: false, fragile: !fragile, seal: false })
  const [used, setUsed] = useState(Object.fromEntries(reserved.map((r) => [r.code, r.quantity])))
  const [editUsed, setEditUsed] = useState(false)
  const all = checks.count && checks.fragile && checks.seal
  const toggle = (k) => setChecks({ ...checks, [k]: !checks[k] })

  const submit = () => onComplete({
    // placement_followed is set because the worker stepped through every placement slide to get here.
    checklist: { items_match_order: checks.count, fragile_protection_applied: checks.fragile, placement_followed: true,
      void_fill_added: checks.seal, carton_sealed: checks.seal },
    materials_used: Object.entries(used).map(([code, quantity]) => ({ code, quantity })),
  })

  return (
    <div className="finish">
      <div className="finish-main">
        <h2>Fill, check and seal</h2>
        {voidFill && <p className="finish-lede">Fill the gaps with about <b>{voidFill.quantity} {voidFill.unit}s of {voidFill.name.toLowerCase()}</b> so nothing can move.</p>}
        <div className="checks-big">
          <button className={checks.count ? 'on' : ''} aria-pressed={checks.count} onClick={() => toggle('count')}>
            <span className="tick" />All {plan.placements.length} items are in the carton
          </button>
          {fragile && (
            <button className={checks.fragile ? 'on' : ''} aria-pressed={checks.fragile} onClick={() => toggle('fragile')}>
              <span className="tick" />Fragile items are wrapped and have space around them
            </button>
          )}
          <button className={checks.seal ? 'on' : ''} aria-pressed={checks.seal} onClick={() => toggle('seal')}>
            <span className="tick" />Gaps filled, carton taped and labelled
          </button>
        </div>

        <div className="used">
          <p>Materials used: {reserved.map((r) => `${used[r.code]} ${mats[r.code]?.name.toLowerCase() || r.code}`).join(', ') || 'none'}.
            {' '}<button className="linkbtn" onClick={() => setEditUsed(!editUsed)}>{editUsed ? 'Done' : 'Used a different amount?'}</button></p>
          {editUsed && reserved.map((r) => (
            <Stepper key={r.code} label={mats[r.code]?.name || r.code} unit={mats[r.code]?.unit || ''}
              value={used[r.code]} onChange={(v) => setUsed({ ...used, [r.code]: v })} />
          ))}
        </div>

        {error && <div className="errorbox" role="alert"><strong>Not completed</strong><p>{error.message}</p>
          {error.data?.detail?.missing?.length > 0 && <ul>{error.data.detail.missing.map((m, i) => <li key={i}>{m}</li>)}</ul>}</div>}

        <button className="btn btn-peach btn-xl" disabled={!all || busy} onClick={submit}>
          {busy ? 'Completing…' : all ? `Complete packing ${order.code}` : 'Tick the checks to complete'}
        </button>
      </div>
      <div className="finish-viz">
        <Carton3D carton={plan.selected.carton.dims_cm} placements={plan.placements} colors={colorsFor(plan, order)} />
      </div>
    </div>
  )
}

export default function PackSlides({ order, plan, slides, index, setIndex, busy, error, onComplete, onChange, onStop }) {
  const [view, setView] = useState(readView)
  const carton = plan.selected.carton
  const onFinish = index >= slides.length
  const slide = slides[Math.min(index, slides.length - 1)]

  const colors = useMemo(() => colorsFor(plan, order), [plan, order])
  const currentRefs = useMemo(() => new Set(onFinish ? [] : slide.refs), [onFinish, slide])
  const doneRefs = useMemo(() => new Set(onFinish ? plan.placements.map((p) => p.unit_ref) : slide.earlierRefs), [onFinish, slide, plan])

  useEffect(() => {
    const on = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || document.querySelector('.modal')) return
      if ((e.key === 'ArrowRight' || e.key === 'Enter') && !onFinish) { e.preventDefault(); setIndex(index + 1) }
      if (e.key === 'ArrowLeft' && index > 0) { e.preventDefault(); setIndex(index - 1) }
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [index, onFinish, setIndex])

  const pickView = (v) => { setView(v); saveView(v) }

  return (
    <div className="slides">
      <div className="slides-bar">
        <div className="carton-chip"><b>{cartonTitle(carton)}</b> <span>{setupShort(carton.dims_cm)}</span></div>
        <Progress slides={slides} index={index} onJump={setIndex} />
        <div className="slides-tools">
          <button className="linkbtn" onClick={onChange}>Change carton</button>
          <button className="linkbtn" onClick={onStop}>Stop packing</button>
        </div>
      </div>

      {onFinish ? <Finish plan={plan} order={order} busy={busy} error={error} onComplete={onComplete} /> : (
        <div className="slide" key={index}>
          <div className="slide-product">
            <div className="slide-top">
              <div className="slide-art">
                <ProductArt product={slide.item || { name: slide.name }} />
                {slide.qty > 1 && <span className="qty-badge">×{slide.qty}</span>}
              </div>
              <div>
                {slide.fragile && <span className="flag flag-frag">Fragile</span>}
                <h2 className="slide-name">{slide.name}</h2>
                {slide.qty > 1 && <p className="muted">{slide.qty} of these, placed one after the other</p>}
              </div>
            </div>
            <ol className="todo">
              {slide.wrap && <li className="todo-wrap">{slide.wrap}</li>}
              {slide.spots.map((sp, k) => (
                <li key={sp.ref} className="todo-place">
                  <span className="seqdot">{sp.seq}</span>
                  <div>
                    <b>{slide.qty > 1 ? `${k === 0 ? 'First' : k === 1 ? 'Second' : `No. ${k + 1}`}: ` : ''}{sp.headline}</b>
                    <span>{sp.upright}. {sp.turn}.</span>
                  </div>
                </li>
              ))}
              {slide.padding > 0 && <li className="todo-gap">Leave a {slide.padding} cm gap on every side</li>}
            </ol>
            {(slide.restrictions || (slide.handling && slide.handling !== 'Standard item.')) && (
              <p className="slide-note">{slide.handling !== 'Standard item.' ? slide.handling : ''} {slide.restrictions}</p>
            )}
            <details className="exact">
              <summary>Exact measurements</summary>
              <ul>{slide.spots.map((sp) => <li key={sp.ref}>No. {sp.seq}: {sp.exact}; footprint {sp.footprint}</li>)}</ul>
            </details>
          </div>

          <div className="slide-viz">
            <div className="seg seg-small" role="tablist" aria-label="View">
              <button role="tab" aria-selected={view === 'top'} className={view === 'top' ? 'on' : ''} onClick={() => pickView('top')}>Top view</button>
              <button role="tab" aria-selected={view === '3d'} className={view === '3d' ? 'on' : ''} onClick={() => pickView('3d')}>3D</button>
            </div>
            {view === '3d'
              ? <Carton3D carton={carton.dims_cm} placements={plan.placements} currentRefs={currentRefs} doneRefs={doneRefs} colors={colors} />
              : <FloorPlan carton={carton.dims_cm} placements={plan.placements} currentRefs={currentRefs} doneRefs={doneRefs} names />}
            <p className="legend"><span className="lg-cur" />Place now <span className="lg-done" />Already in <span className="lg-ghost" />Comes later</p>
          </div>
        </div>
      )}

      <div className="slides-nav">
        <button className="btn btn-quiet btn-lg" disabled={index === 0} onClick={() => setIndex(index - 1)}>Back</button>
        {!onFinish && (
          <button className="btn btn-ink btn-lg nav-next" onClick={() => setIndex(index + 1)}>
            {index === slides.length - 1 ? 'Done, finish up' : 'Done, next item'}
          </button>
        )}
      </div>
    </div>
  )
}
