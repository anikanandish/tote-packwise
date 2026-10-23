// Product catalogue: storefront details plus the packaging data the packing engine needs.
import { useMemo, useState } from 'react'
import ProductArt from '../../components/ProductArt'
import { Confirm, Empty, ErrorBox, Field, Loading, Modal, Tag } from '../../components/ui'
import { useToast } from '../../context/ToastContext'
import { api, fieldErrors } from '../../lib/api'
import { kg, money } from '../../lib/format'
import useFetch from '../../lib/useFetch'

const BLANK = { name: '', brand: 'TOTE', category: '', price: '', stock: 0, description: '', is_active: true, featured: false,
  length_cm: '', width_cm: '', height_cm: '', weight_g: '', fragile: false, padding_cm: 0, orientation: 'any',
  protection_material_code: '', protection_qty_per_unit: 0, handling_instructions: '', restrictions: '' }
const NUM = ['price', 'stock', 'length_cm', 'width_cm', 'height_cm', 'weight_g', 'padding_cm', 'protection_qty_per_unit']

function validate(f) {
  const e = {}
  if (f.name.trim().length < 2) e.name = 'Enter a name'
  if (f.category.trim().length < 2) e.category = 'Enter a category'
  const pos = (k, label) => { const n = Number(f[k]); if (f[k] === '' || !(n > 0)) e[k] = `${label} must be above 0` }
  pos('price', 'Price'); pos('length_cm', 'Length'); pos('width_cm', 'Width'); pos('height_cm', 'Height')
  if (!(Number.isInteger(Number(f.weight_g)) && Number(f.weight_g) > 0)) e.weight_g = 'Whole grams above 0'
  if (!(Number.isInteger(Number(f.stock)) && Number(f.stock) >= 0)) e.stock = 'A whole number, 0 or more'
  if (!(Number(f.padding_cm) >= 0 && Number(f.padding_cm) <= 20)) e.padding_cm = '0 to 20 cm'
  if (!(Number.isInteger(Number(f.protection_qty_per_unit)) && Number(f.protection_qty_per_unit) >= 0)) e.protection_qty_per_unit = 'Whole number'
  if (f.fragile && !f.protection_material_code) e.protection_material_code = 'Fragile items need a protective material'
  return e
}

function Editor({ row, materials, categories, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState(row ? { ...BLANK, ...row, ...row.packaging, protection_material_code: row.packaging.protection_material_code || '' } : BLANK)
  const [errors, setErrors] = useState({})
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const save = async (e) => {
    e.preventDefault()
    const v = validate(f); setErrors(v)
    if (Object.keys(v).length) return
    const body = {}
    for (const k of Object.keys(BLANK)) body[k] = NUM.includes(k) ? Number(f[k]) : f[k]
    body.protection_material_code = f.protection_material_code || (row ? '' : null)
    setBusy(true); setErr(null)
    try {
      await api(row ? `/api/admin/products/${row.id}` : '/api/admin/products', { method: row ? 'PATCH' : 'POST', body })
      toast(row ? 'Product saved' : 'Product added'); onSaved()
    } catch (e2) { setErr(e2); setErrors(fieldErrors(e2)) } finally { setBusy(false) }
  }
  const padded = ['length_cm', 'width_cm', 'height_cm'].map((k) => Number(f[k]) + 2 * Math.max(Number(f.padding_cm) || 0, f.fragile ? 1 : 0))
  return (
    <Modal title={row ? `Edit ${row.name}` : 'Add a product'} onClose={onClose} wide>
      <form onSubmit={save} noValidate>
        <h3 className="form-section">Storefront</h3>
        <div className="form-grid three">
          <Field label="Name" error={errors.name}><input className="input" value={f.name} onChange={set('name')} /></Field>
          <Field label="Brand"><input className="input" value={f.brand} onChange={set('brand')} /></Field>
          <Field label="Category" error={errors.category}><input className="input" list="cats" value={f.category} onChange={set('category')} />
            <datalist id="cats">{categories.map((c) => <option key={c} value={c} />)}</datalist></Field>
          <Field label="Price (₹)" error={errors.price}><input className="input num" inputMode="decimal" value={f.price} onChange={set('price')} /></Field>
          <Field label="Stock (units for sale)" error={errors.stock}><input className="input num" inputMode="numeric" value={f.stock} onChange={set('stock')} /></Field>
          <div className="checks"><label className="checkline"><input type="checkbox" checked={f.is_active} onChange={set('is_active')} />On sale</label>
            <label className="checkline"><input type="checkbox" checked={f.featured} onChange={set('featured')} />Featured</label></div>
        </div>
        <Field label="Description"><textarea className="input" rows="2" value={f.description} onChange={set('description')} /></Field>
        <h3 className="form-section">Packaging data used by PackWise</h3>
        <div className="form-grid four">
          <Field label="Length (cm)" error={errors.length_cm}><input className="input num" inputMode="decimal" value={f.length_cm} onChange={set('length_cm')} /></Field>
          <Field label="Width (cm)" error={errors.width_cm}><input className="input num" inputMode="decimal" value={f.width_cm} onChange={set('width_cm')} /></Field>
          <Field label="Height (cm)" error={errors.height_cm}><input className="input num" inputMode="decimal" value={f.height_cm} onChange={set('height_cm')} /></Field>
          <Field label="Weight (g)" error={errors.weight_g}><input className="input num" inputMode="numeric" value={f.weight_g} onChange={set('weight_g')} /></Field>
          <Field label="Padding each side (cm)" error={errors.padding_cm} hint="Fragile items get at least 1 cm"><input className="input num" inputMode="decimal" value={f.padding_cm} onChange={set('padding_cm')} /></Field>
          <Field label="Orientation"><select className="input" value={f.orientation} onChange={set('orientation')}>
            <option value="any">Any (still never tipped by the engine)</option><option value="upright">Must stay upright</option></select></Field>
          <Field label="Protective material" error={errors.protection_material_code}><select className="input" value={f.protection_material_code} onChange={set('protection_material_code')}>
            <option value="">None</option>{materials.map((m) => <option key={m.code} value={m.code}>{m.name}</option>)}</select></Field>
          <Field label="Material per unit" error={errors.protection_qty_per_unit}><input className="input num" inputMode="numeric" value={f.protection_qty_per_unit} onChange={set('protection_qty_per_unit')} /></Field>
        </div>
        <label className="checkline"><input type="checkbox" checked={f.fragile} onChange={set('fragile')} />Fragile (needs protection and at least 1 cm padding)</label>
        <div className="form-grid">
          <Field label="Handling instructions (shown to packers)"><input className="input" value={f.handling_instructions} onChange={set('handling_instructions')} /></Field>
          <Field label="Restrictions"><input className="input" value={f.restrictions} onChange={set('restrictions')} /></Field>
        </div>
        {padded.every((n) => n > 0) && <p className="note-line">Packed size sent to the packing engine: {padded.map((n) => Math.ceil(n * 10)).join(' × ')} mm (rounded up).</p>}
        <ErrorBox error={err} />
        <div className="modal-actions"><button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-ink" disabled={busy}>{busy ? 'Saving…' : row ? 'Save changes' : 'Add product'}</button></div>
      </form>
    </Modal>
  )
}

export default function Products() {
  const toast = useToast()
  const { data, error, loading, reload } = useFetch('/api/admin/products')
  const mats = useFetch('/api/admin/materials')
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('')
  const [flt, setFlt] = useState('')
  const [modal, setModal] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actErr, setActErr] = useState(null)
  const categories = useMemo(() => [...new Set((data || []).map((p) => p.category))].sort(), [data])
  const rows = (data || []).filter((p) => (!q || `${p.name} ${p.brand}`.toLowerCase().includes(q.toLowerCase())) &&
    (!cat || p.category === cat) && (!flt || (flt === 'fragile' ? p.fragile : flt === 'inactive' ? !p.is_active : p.stock <= 10)))
  const close = () => { setModal(null); setActErr(null) }
  const toggle = async () => {
    setBusy(true); setActErr(null)
    try { await api(`/api/admin/products/${modal.row.id}`, { method: 'PATCH', body: { is_active: !modal.row.is_active } }); toast('Saved'); close(); reload() }
    catch (e) { setActErr(e) } finally { setBusy(false) }
  }
  return (
    <div className="pagepad">
      <div className="page-head">
        <div><h1>Products</h1><p className="muted">Storefront details and packaging data. Product sizes are bounding boxes in cm; PackWise adds padding and converts to mm.</p></div>
        <button className="btn btn-peach" onClick={() => setModal({ kind: 'edit' })}>Add product</button>
      </div>
      <div className="filters">
        <input className="input" placeholder="Search products" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search products" />
        <select className="input" value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Category"><option value="">All categories</option>{categories.map((c) => <option key={c}>{c}</option>)}</select>
        <select className="input" value={flt} onChange={(e) => setFlt(e.target.value)} aria-label="Filter"><option value="">All products</option><option value="fragile">Fragile</option><option value="low">10 or fewer in stock</option><option value="inactive">Not on sale</option></select>
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} retry={reload} />
      {data && rows.length === 0 && <Empty title="No products match" />}
      {rows.length > 0 && (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Product</th><th>Size L × W × H (cm)</th><th className="num">Weight</th><th>Packing</th><th className="num">Price</th><th className="num">Stock</th><th>Status</th><th></th></tr></thead>
          <tbody>{rows.map((p) => (
            <tr key={p.id} className={!p.is_active ? 'inactive' : ''}>
              <td><div className="prod-cell"><span className="prod-thumb"><ProductArt product={p} /></span>
                <div><b>{p.name}</b><div className="small muted">{p.brand} · {p.category}</div></div></div></td>
              <td className="mono">{[p.packaging.length_cm, p.packaging.width_cm, p.packaging.height_cm].join(' × ')}</td>
              <td className="num">{kg(p.packaging.weight_g)}</td>
              <td className="small"><div className="tags">{p.fragile && <Tag kind="warn">Fragile</Tag>}{p.packaging.orientation === 'upright' && <Tag>Upright</Tag>}
                {p.packaging.padding_cm > 0 && <Tag>{p.packaging.padding_cm} cm padding</Tag>}{p.packaging.protection_material_code && <Tag>{p.packaging.protection_material_code} × {p.packaging.protection_qty_per_unit}</Tag>}</div></td>
              <td className="num">{money(p.price)}</td>
              <td className={`num ${p.stock <= 10 ? 'lowcell' : ''}`}>{p.stock}</td>
              <td>{p.is_active ? 'On sale' : 'Hidden'}</td>
              <td className="row-actions col"><button className="linkbtn" onClick={() => setModal({ kind: 'edit', row: p })}>Edit</button>
                <button className="linkbtn" onClick={() => setModal({ kind: 'toggle', row: p })}>{p.is_active ? 'Hide from shop' : 'Put on sale'}</button></td>
            </tr>))}</tbody>
        </table></div>)}
      {modal?.kind === 'edit' && <Editor row={modal.row} materials={mats.data || []} categories={categories} onClose={close} onSaved={() => { close(); reload() }} />}
      {modal?.kind === 'toggle' && (
        <Confirm title={modal.row.is_active ? `Hide ${modal.row.name}?` : `Put ${modal.row.name} on sale?`} busy={busy} error={actErr}
          confirmLabel={modal.row.is_active ? 'Hide from shop' : 'Put on sale'} danger={modal.row.is_active} onClose={close} onConfirm={toggle}>
          <p>{modal.row.is_active ? 'Customers will no longer see or buy it. Existing orders and their packing records are not affected.' : 'It will appear in the TOTE shop again.'}</p>
        </Confirm>)}
    </div>
  )
}
