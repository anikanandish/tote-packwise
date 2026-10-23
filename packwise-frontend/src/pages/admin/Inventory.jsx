// Protective materials (cartons have their own page: Cartons.jsx).
import { useState } from 'react'
import { Empty, ErrorBox, Field, Loading, Modal } from '../../components/ui'
import { useToast } from '../../context/ToastContext'
import { api } from '../../lib/api'
import { dims, kg, money, vol, when } from '../../lib/format'
import useFetch from '../../lib/useFetch'

const CONFIG = {
  material: {
    title: 'Protective materials', path: '/api/admin/materials', noun: 'material',
    blurb: 'Products name a material code in their packaging metadata. A material that runs out blocks packing for products that need it.',
    fields: [['code', 'Code', 'text', true], ['name', 'Name', 'text'], ['unit', 'Unit (sheet, bag…)', 'text'], ['unit_cost', 'Cost per unit (₹)', 'num'],
      ['stock', 'Opening stock', 'int', true], ['min_stock', 'Low-stock threshold', 'int'], ['is_active', 'Active', 'bool'], ['notes', 'Handling notes', 'text']],
  },
}

function Editor({ cfg, row, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState(row ? { ...row, unit_cost: row.unit_cost ?? '' } : { is_active: true, is_baseline: false, stock: 0, min_stock: 0 })
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    const body = {}
    for (const [k, , type, createOnly] of cfg.fields) {
      if (row && createOnly) continue
      let v = f[k]
      if (type === 'num' || type === 'int') v = v === '' || v == null ? null : Number(v)
      if (type === 'bool') v = !!v
      if (v === null && k !== 'unit_cost') continue
      body[k] = v
    }
    if (row && body.unit_cost === null) { delete body.unit_cost; body.clear_unit_cost = true }
    try {
      await api(row ? `${cfg.path}/${row.id}` : cfg.path, { method: row ? 'PATCH' : 'POST', body })
      toast(row ? 'Saved' : `New ${cfg.noun} added`); onSaved()
    } catch (e2) { setErr(e2) } finally { setBusy(false) }
  }
  return (
    <Modal title={row ? `Edit ${row.name}` : `Add ${cfg.noun}`} onClose={onClose}>
      <form onSubmit={save}>
        <div className="form-grid">
          {cfg.fields.filter(([, , , createOnly]) => !(row && createOnly)).map(([k, label, type]) => type === 'bool' ? (
            <label key={k} className="checkline"><input type="checkbox" checked={!!f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />{label}</label>
          ) : (
            <Field key={k} label={label} error={err?.data?.errors?.find((x) => x.field === k)?.message}
              hint={k === 'unit_cost' ? 'Leave empty if unknown; costs then show as unavailable' : null}>
              <input className="input" value={f[k] ?? ''} inputMode={type === 'text' ? 'text' : 'decimal'} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
            </Field>
          ))}
        </div>
        {err && <p className="err">{err.message}</p>}
        <div className="modal-actions"><button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-ink" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>
      </form>
    </Modal>
  )
}

function Adjust({ cfg, row, onClose, onSaved }) {
  const [delta, setDelta] = useState('')
  const [reason, setReason] = useState('')
  const [err, setErr] = useState(null)
  const save = async (e) => {
    e.preventDefault(); setErr(null)
    try { await api(`${cfg.path}/${row.id}/adjust`, { method: 'POST', body: { delta: Number(delta), reason } }); onSaved() }
    catch (e2) { setErr(e2) }
  }
  return (
    <Modal title={`Adjust stock: ${row.name}`} onClose={onClose}>
      <form onSubmit={save}>
        <p>{row.stock} in stock, {row.reserved} reserved, {row.available} available.</p>
        <Field label="Change (+ to add, − to remove)"><input className="input num" value={delta} onChange={(e) => setDelta(e.target.value)} placeholder="e.g. 50 or -3" autoFocus /></Field>
        <Field label="Reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Delivery received, damaged, stock count…" /></Field>
        {err && <p className="err">{err.message}</p>}
        <div className="modal-actions"><button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-ink" disabled={!delta || Number(delta) === 0 || reason.trim().length < 3}>Record adjustment</button></div>
      </form>
    </Modal>
  )
}

function Movements({ type, row, onClose }) {
  const { data, error, loading } = useFetch(`/api/admin/movements?item_type=${type}&item_id=${row.id}`)
  return (
    <Modal title={`Stock history: ${row.name}`} onClose={onClose} wide>
      {loading && <Loading />}
      <ErrorBox error={error} />
      {data && data.length === 0 && <Empty title="No movements yet" />}
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

export default function Inventory({ type }) {
  const cfg = CONFIG[type]
  const { data, error, loading, reload } = useFetch(cfg.path)
  const [modal, setModal] = useState(null)
  const close = () => setModal(null)
  const saved = () => { close(); reload() }

  return (
    <div className="pagepad">
      <div className="page-head">
        <div><h1>{cfg.title}</h1><p className="muted">{cfg.blurb}</p></div>
        <button className="btn btn-peach" onClick={() => setModal({ kind: 'edit' })}>Add {cfg.noun}</button>
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} retry={reload} />
      {data && (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>{type === 'carton' ? 'Carton' : 'Material'}</th>
            {type === 'carton' ? <><th>Internal size</th><th className="num">Volume</th><th className="num">Max load</th></> : <th>Unit</th>}
            <th className="num">Unit cost</th><th className="num">Stock</th><th className="num">Reserved</th><th className="num">Available</th><th>Status</th><th></th></tr></thead>
          <tbody>{data.map((r) => (
            <tr key={r.id} className={!r.is_active ? 'inactive' : ''}>
              <td><b>{r.name}</b> <span className="muted small">{r.code}</span>{r.is_baseline && <span className="flag">Baseline</span>}</td>
              {type === 'carton' ? <><td>{dims([r.length_cm, r.width_cm, r.height_cm])}</td><td className="num">{vol(r.volume_cm3)}</td><td className="num">{kg(r.max_weight_g)}</td></> : <td>{r.unit}</td>}
              <td className="num">{money(r.unit_cost)}</td><td className="num">{r.stock}</td><td className="num">{r.reserved}</td>
              <td className={`num ${r.low_stock ? 'lowcell' : ''}`}>{r.available}{r.low_stock && <span className="small"> low (min {r.min_stock})</span>}</td>
              <td>{r.is_active ? (r.available > 0 ? 'Available for packing' : 'Out of stock') : 'Inactive'}</td>
              <td className="row-actions">
                <button className="linkbtn" onClick={() => setModal({ kind: 'adjust', row: r })}>Adjust stock</button>
                <button className="linkbtn" onClick={() => setModal({ kind: 'edit', row: r })}>Edit</button>
                <button className="linkbtn" onClick={() => setModal({ kind: 'moves', row: r })}>History</button>
              </td>
            </tr>))}</tbody>
        </table></div>)}
      {modal?.kind === 'edit' && <Editor cfg={cfg} row={modal.row} onClose={close} onSaved={saved} />}
      {modal?.kind === 'adjust' && <Adjust cfg={cfg} row={modal.row} onClose={close} onSaved={saved} />}
      {modal?.kind === 'moves' && <Movements type={type} row={modal.row} onClose={close} />}
    </div>
  )
}
