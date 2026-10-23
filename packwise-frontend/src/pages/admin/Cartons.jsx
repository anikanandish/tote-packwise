// Carton catalogue: the eight standard sizes plus admin-created cartons. Sizes in millimetres.
import { useMemo, useState } from 'react'
import { Confirm, Empty, ErrorBox, Field, Loading, Modal, Tag } from '../../components/ui'
import { useToast } from '../../context/ToastContext'
import { api } from '../../lib/api'
import { kg, litres, mm3, money, when } from '../../lib/format'
import useFetch from '../../lib/useFetch'

const AXES = [['length', 'Length'], ['width', 'Width'], ['height', 'Height']]

function intOrNull(v) {
  if (v === '' || v == null) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : NaN
}

// Client-side checks mirror the server's (the server validates again).
function validate(f, isNew) {
  const e = {}
  if (isNew && !/^[A-Za-z0-9_-]{2,40}$/.test(f.code || '')) e.code = 'Use 2–40 letters, digits, - or _'
  if (!f.name || f.name.trim().length < 2) e.name = 'Enter a name'
  for (const [a] of AXES) {
    for (const k of [`nominal_${a}_mm`, ...(f.same ? [] : [`${a}_mm`])]) {
      const n = intOrNull(f[k])
      if (n == null || !Number.isInteger(n) || n <= 0 || n > 3000) e[k] = 'Whole mm, 1–3000'
    }
  }
  const w = intOrNull(f.max_weight_g)
  if (w !== null && (!Number.isInteger(w) || w <= 0)) e.max_weight_g = 'Whole grams above 0, or leave empty'
  const c = intOrNull(f.unit_cost)
  if (c !== null && (Number.isNaN(c) || c < 0)) e.unit_cost = 'A price of 0 or more, or leave empty'
  for (const k of ['min_stock', ...(isNew ? ['stock'] : [])]) {
    const n = intOrNull(f[k])
    if (n == null || !Number.isInteger(n) || n < 0) e[k] = 'A whole number, 0 or more'
  }
  return e
}

function Editor({ row, onClose, onSaved }) {
  const toast = useToast()
  const isNew = !row
  const [f, setF] = useState(() => row ? {
    name: row.name, category: row.category, notes: row.notes,
    nominal_length_mm: row.nominal_mm[0], nominal_width_mm: row.nominal_mm[1], nominal_height_mm: row.nominal_mm[2],
    length_mm: row.internal_mm[0], width_mm: row.internal_mm[1], height_mm: row.internal_mm[2],
    same: !row.internal_differs, internal_verified: row.internal_verified,
    max_weight_g: row.max_weight_g ?? '', unit_cost: row.unit_cost ?? '', min_stock: row.min_stock, is_baseline: row.is_baseline,
  } : { code: '', name: '', category: 'Custom', notes: '', same: true, internal_verified: false, stock: 0, min_stock: 0,
    max_weight_g: '', unit_cost: '', is_baseline: false })
  const [errors, setErrors] = useState({})
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  const save = async (e) => {
    e.preventDefault()
    const v = validate(f, isNew)
    setErrors(v)
    if (Object.keys(v).length) return
    const body = { name: f.name.trim(), category: f.category.trim() || 'Custom', notes: f.notes || '',
      internal_verified: !!f.internal_verified, min_stock: Number(f.min_stock), is_baseline: !!f.is_baseline }
    for (const [a] of AXES) {
      body[`nominal_${a}_mm`] = Number(f[`nominal_${a}_mm`])
      body[`${a}_mm`] = Number(f.same ? f[`nominal_${a}_mm`] : f[`${a}_mm`])
    }
    const w = intOrNull(f.max_weight_g), c = intOrNull(f.unit_cost)
    if (isNew) {
      Object.assign(body, { code: f.code.trim(), stock: Number(f.stock), max_weight_g: w, unit_cost: c })
    } else {
      if (w === null) { if (row.max_weight_g != null) body.clear_max_weight = true } else if (w !== row.max_weight_g) body.max_weight_g = w
      if (c === null) { if (row.unit_cost != null) body.clear_unit_cost = true } else if (c !== row.unit_cost) body.unit_cost = c
      // Only send what changed, so untouched sample values stay marked as sample.
      for (const k of Object.keys(body)) {
        if (['clear_max_weight', 'clear_unit_cost', 'max_weight_g', 'unit_cost'].includes(k)) continue
        const old = k.endsWith('_mm') ? (k.startsWith('nominal_') ? row.nominal_mm : row.internal_mm)[['length', 'width', 'height'].indexOf(k.replace('nominal_', '').replace('_mm', ''))] : row[k]
        if (old === body[k]) delete body[k]
      }
      if (body.is_baseline === false) delete body.is_baseline
    }
    setBusy(true); setErr(null)
    try {
      await api(isNew ? '/api/admin/cartons' : `/api/admin/cartons/${row.id}`, { method: isNew ? 'POST' : 'PATCH', body })
      toast(isNew ? 'Carton added' : 'Carton saved'); onSaved()
    } catch (e2) { setErr(e2) } finally { setBusy(false) }
  }

  const sample = (k) => row?.sample_fields?.includes(k) && <Tag kind="sample">sample value</Tag>
  return (
    <Modal title={isNew ? 'Add a custom carton' : `Edit ${row.name}`} onClose={onClose} wide>
      <form onSubmit={save} noValidate>
        {row?.is_predefined && <p className="note-line">Standard carton {row.code}. Its nominal size is the specification; record the measured internal size below once checked.</p>}
        <div className="form-grid three">
          {isNew && <Field label="Code" error={errors.code} hint="Unique, e.g. LIP-SLEEVE"><input className="input" value={f.code} onChange={set('code')} /></Field>}
          <Field label="Name" error={errors.name}><input className="input" value={f.name} onChange={set('name')} /></Field>
          <Field label="Group"><input className="input" value={f.category} onChange={set('category')} disabled={row?.is_predefined} /></Field>
        </div>
        <fieldset className="dims-set">
          <legend>Nominal size (as labelled), mm · L × W × H</legend>
          <div className="dims-row">{AXES.map(([a, l]) => (
            <Field key={a} label={l} error={errors[`nominal_${a}_mm`]}>
              <input className="input num" inputMode="numeric" value={f[`nominal_${a}_mm`] ?? ''} onChange={set(`nominal_${a}_mm`)} /></Field>))}</div>
        </fieldset>
        <fieldset className="dims-set">
          <legend>Internal usable size, mm · used for every fit calculation</legend>
          <label className="checkline"><input type="checkbox" checked={f.same} onChange={set('same')} />Same as nominal (not measured yet)</label>
          {!f.same && <div className="dims-row">{AXES.map(([a, l]) => (
            <Field key={a} label={l} error={errors[`${a}_mm`]}>
              <input className="input num" inputMode="numeric" value={f[`${a}_mm`] ?? ''} onChange={set(`${a}_mm`)} /></Field>))}</div>}
          <label className="checkline"><input type="checkbox" checked={f.internal_verified} onChange={set('internal_verified')} />Internal size verified by measuring a real carton</label>
        </fieldset>
        <div className="form-grid three">
          <Field label={<>Maximum weight (g) {sample('max_weight_g')}</>} error={errors.max_weight_g} hint="Leave empty if no verified figure; weight is then not checked">
            <input className="input num" inputMode="numeric" value={f.max_weight_g} onChange={set('max_weight_g')} placeholder="Not set" /></Field>
          <Field label={<>Unit cost (₹) {sample('unit_cost')}</>} error={errors.unit_cost} hint="Leave empty if unknown">
            <input className="input num" inputMode="decimal" value={f.unit_cost} onChange={set('unit_cost')} placeholder="Unknown" /></Field>
          <Field label={<>Low-stock threshold {sample('min_stock')}</>} error={errors.min_stock}>
            <input className="input num" inputMode="numeric" value={f.min_stock} onChange={set('min_stock')} /></Field>
          {isNew && <Field label="Opening stock" error={errors.stock}><input className="input num" inputMode="numeric" value={f.stock} onChange={set('stock')} /></Field>}
        </div>
        <Field label="Notes"><input className="input" value={f.notes} onChange={set('notes')} /></Field>
        {!row?.is_baseline && <label className="checkline"><input type="checkbox" checked={f.is_baseline} onChange={set('is_baseline')} />Make this the baseline carton for savings comparisons</label>}
        <ErrorBox error={err} />
        <div className="modal-actions"><button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-ink" disabled={busy}>{busy ? 'Saving…' : isNew ? 'Add carton' : 'Save changes'}</button></div>
      </form>
    </Modal>
  )
}

function Adjust({ row, onClose, onSaved }) {
  const [delta, setDelta] = useState('')
  const [reason, setReason] = useState('')
  const [err, setErr] = useState(null)
  const n = Number(delta)
  const valid = Number.isInteger(n) && n !== 0 && reason.trim().length >= 3 && row.stock + n >= row.reserved
  const save = async (e) => {
    e.preventDefault(); setErr(null)
    try { await api(`/api/admin/cartons/${row.id}/adjust`, { method: 'POST', body: { delta: n, reason: reason.trim() } }); onSaved() }
    catch (e2) { setErr(e2) }
  }
  return (
    <Modal title={`Adjust stock: ${row.name}`} onClose={onClose}>
      <form onSubmit={save}>
        <p>{row.stock} in stock, {row.reserved} reserved for packing in progress, {row.available} available.
          {row.sample_fields.includes('stock') && <> <Tag kind="sample">sample quantity</Tag> Recording a real count replaces it.</>}</p>
        <Field label="Change (+ to add, − to remove)" hint={delta && Number.isInteger(n) ? `New stock: ${row.stock + n}` : 'Whole cartons'}
          error={delta && Number.isInteger(n) && row.stock + n < row.reserved ? `Stock cannot go below the ${row.reserved} reserved` : null}>
          <input className="input num" value={delta} onChange={(e) => setDelta(e.target.value)} placeholder="e.g. 50 or -3" autoFocus /></Field>
        <Field label="Reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Delivery received, stock count, damaged…" /></Field>
        <ErrorBox error={err} />
        <div className="modal-actions"><button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-ink" disabled={!valid}>Record adjustment</button></div>
      </form>
    </Modal>
  )
}

function Movements({ row, onClose }) {
  const { data, error, loading } = useFetch(`/api/admin/movements?item_type=carton&item_id=${row.id}`)
  return (
    <Modal title={`Stock history: ${row.name}`} onClose={onClose} wide>
      {loading && <Loading />}
      <ErrorBox error={error} />
      {data?.length === 0 && <Empty title="No movements yet" />}
      {data?.length > 0 && (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>When</th><th>Type</th><th className="num">Stock Δ</th><th className="num">Reserved Δ</th><th className="num">Stock after</th><th>Reason</th><th>By</th></tr></thead>
          <tbody>{data.map((m) => (
            <tr key={m.id}><td className="small">{when(m.created_at)}</td><td>{m.kind}</td>
              <td className="num">{m.stock_delta > 0 ? '+' : ''}{m.stock_delta}</td><td className="num">{m.reserved_delta > 0 ? '+' : ''}{m.reserved_delta}</td>
              <td className="num">{m.stock_after}</td><td className="small">{m.reason}{m.order_code && ` (${m.order_code})`}</td><td className="small">{m.actor}</td></tr>))}</tbody>
        </table></div>)}
    </Modal>
  )
}

const SORTS = {
  volume: (a, b) => a.volume_cm3 - b.volume_cm3,
  name: (a, b) => a.name.localeCompare(b.name),
  available: (a, b) => a.available - b.available,
  used: (a, b) => b.times_used - a.times_used,
}

export default function Cartons() {
  const toast = useToast()
  const [showRetired, setShowRetired] = useState(false)
  const { data, error, loading, reload } = useFetch(`/api/admin/cartons${showRetired ? '?include_retired=true' : ''}`)
  const [q, setQ] = useState('')
  const [group, setGroup] = useState('')
  const [kind, setKind] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('volume')
  const [modal, setModal] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actErr, setActErr] = useState(null)
  const close = () => { setModal(null); setActErr(null) }
  const saved = () => { close(); reload() }

  const groups = useMemo(() => [...new Set((data || []).map((c) => c.category))], [data])
  const rows = useMemo(() => (data || []).filter((c) =>
    (!q || `${c.name} ${c.code}`.toLowerCase().includes(q.toLowerCase())) &&
    (!group || c.category === group) &&
    (!kind || (kind === 'standard') === c.is_predefined) &&
    (!status || (status === 'active' ? c.is_active : status === 'inactive' ? !c.is_active : c.is_active && c.low_stock))
  ).sort(SORTS[sort]), [data, q, group, kind, status, sort])

  const act = async (fn, msg) => {
    setBusy(true); setActErr(null)
    try { await fn(); toast(msg); saved() } catch (e) { setActErr(e) } finally { setBusy(false) }
  }
  const std = (data || []).filter((c) => c.is_predefined)

  return (
    <div className="pagepad">
      <div className="page-head">
        <div><h1>Cartons</h1>
          <p className="muted">Sizes in millimetres, shown L × W × H. Fitting always uses the <b>internal</b> size; volume is calculated from it.</p></div>
        <button className="btn btn-peach" onClick={() => setModal({ kind: 'edit' })}>Add custom carton</button>
      </div>
      {std.length > 0 && (
        <div className="quality-strip">
          <span><b>{std.filter((c) => !c.internal_verified).length}</b> of {std.length} standard cartons use the nominal size as internal size (not measured)</span>
          <span><b>{(data || []).filter((c) => c.is_active && c.max_weight_g == null).length}</b> active cartons have no maximum weight set</span>
          <span><b>{(data || []).filter((c) => c.sample_fields.length).length}</b> cartons still hold sample stock or prices</span>
        </div>)}
      <div className="filters">
        <input className="input" placeholder="Search name or code" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search cartons" />
        <select className="input" value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Group">
          <option value="">All groups</option>{groups.map((g) => <option key={g}>{g}</option>)}</select>
        <select className="input" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Type">
          <option value="">Standard and custom</option><option value="standard">Standard (predefined)</option><option value="custom">Admin-created</option></select>
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">Any status</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="low">Low stock</option></select>
        <select className="input" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
          <option value="volume">Sort: volume</option><option value="name">Sort: name</option><option value="available">Sort: available stock</option><option value="used">Sort: most used</option></select>
        <label className="checkline small"><input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} />Show retired cartons</label>
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} retry={reload} />
      {data && rows.length === 0 && <Empty title="No cartons match">Clear the filters or add a carton.</Empty>}
      {rows.length > 0 && (
        <div className="table-wrap"><table className="table cartons-table">
          <thead><tr><th>Carton</th><th>Nominal L × W × H</th><th>Internal (used for fit)</th><th className="num">Volume</th>
            <th className="num">Max load</th><th className="num">Unit cost</th><th className="num">Available</th><th className="num">Used</th><th>Status</th><th></th></tr></thead>
          <tbody>{rows.map((c) => (
            <tr key={c.id} className={!c.is_active ? 'inactive' : ''}>
              <td><b>{c.name}</b><div className="small muted">{c.code} · {c.category}</div>
                <div className="tags">{c.is_predefined ? <Tag kind="std">Standard</Tag> : <Tag kind="custom">Admin-created</Tag>}
                  {c.is_baseline && <Tag kind="base">Baseline</Tag>}</div></td>
              <td className="mono">{mm3(c.nominal_mm)}</td>
              <td className="mono">{c.internal_differs ? mm3(c.internal_mm) : 'Same'}
                <div>{c.internal_verified ? <Tag kind="ok">Verified</Tag> : <Tag kind="warn" title="The nominal size is used until a real carton is measured">Not verified</Tag>}</div></td>
              <td className="num">{litres(c.volume_cm3)}</td>
              <td className="num">{c.max_weight_g == null ? <Tag kind="warn">Not set</Tag> : kg(c.max_weight_g)}</td>
              <td className="num">{money(c.unit_cost)}{c.sample_fields.includes('unit_cost') && <div><Tag kind="sample">sample</Tag></div>}</td>
              <td className={`num ${c.low_stock && c.is_active ? 'lowcell' : ''}`}>{c.available}<span className="muted small"> / {c.stock}</span>
                {c.reserved > 0 && <div className="small muted">{c.reserved} reserved</div>}
                {c.low_stock && c.is_active && <div className="small">low · min {c.min_stock}</div>}
                {c.sample_fields.includes('stock') && <div><Tag kind="sample">sample</Tag></div>}</td>
              <td className="num">{c.times_used}</td>
              <td>{c.is_active ? (c.available > 0 ? 'Active' : 'Active · out of stock') : 'Inactive'}</td>
              <td className="row-actions col">
                <button className="linkbtn" onClick={() => setModal({ kind: 'edit', row: c })}>Edit</button>
                <button className="linkbtn" onClick={() => setModal({ kind: 'adjust', row: c })}>Stock</button>
                <button className="linkbtn" onClick={() => setModal({ kind: 'moves', row: c })}>History</button>
                <button className="linkbtn" onClick={() => setModal({ kind: 'toggle', row: c })}>{c.is_active ? 'Deactivate' : 'Activate'}</button>
                {!c.is_predefined && <button className="linkbtn danger" onClick={() => setModal({ kind: 'delete', row: c })}>Delete</button>}
              </td>
            </tr>))}</tbody>
        </table></div>)}
      {modal?.kind === 'edit' && <Editor row={modal.row} onClose={close} onSaved={saved} />}
      {modal?.kind === 'adjust' && <Adjust row={modal.row} onClose={close} onSaved={saved} />}
      {modal?.kind === 'moves' && <Movements row={modal.row} onClose={close} />}
      {modal?.kind === 'toggle' && (
        <Confirm title={`${modal.row.is_active ? 'Deactivate' : 'Activate'} ${modal.row.name}?`} busy={busy} error={actErr}
          confirmLabel={modal.row.is_active ? 'Deactivate' : 'Activate'} danger={modal.row.is_active} onClose={close}
          onConfirm={() => act(() => api(`/api/admin/cartons/${modal.row.id}`, { method: 'PATCH', body: { is_active: !modal.row.is_active } }),
            modal.row.is_active ? 'Carton deactivated' : 'Carton activated')}>
          {modal.row.is_active
            ? <p>PackWise will stop recommending this carton. Past orders keep their packing records. It cannot be deactivated while cartons are reserved for packing in progress, or while it is the baseline.</p>
            : <p>PackWise will consider this carton again for new recommendations.</p>}
        </Confirm>)}
      {modal?.kind === 'delete' && (
        <Confirm title={`Delete ${modal.row.name}?`} danger busy={busy} error={actErr} confirmLabel="Delete carton" onClose={close}
          onConfirm={() => act(() => api(`/api/admin/cartons/${modal.row.id}`, { method: 'DELETE' }), 'Carton deleted')}>
          <p>Only cartons that have never appeared in a packing plan can be deleted. If this one has, deactivate it instead so order history stays linked to it.</p>
        </Confirm>)}
    </div>
  )
}
