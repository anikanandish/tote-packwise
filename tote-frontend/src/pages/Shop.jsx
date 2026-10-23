import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import ProductCard from '../components/ProductCard'
import { Empty, ErrorState, Loading } from '../components/ui'
import useFetch from '../lib/useFetch'

const SORTS = [['featured', 'Featured'], ['price_asc', 'Price: low to high'], ['price_desc', 'Price: high to low'],
  ['rating', 'Top rated'], ['newest', 'Newest']]
const PRICES = [['', 'Any price'], ['0-999', 'Under ₹1,000'], ['1000-2999', '₹1,000 – ₹2,999'], ['3000-', '₹3,000 and above']]

export default function Shop() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const category = params.get('category') || ''
  const sort = params.get('sort') || 'featured'
  const price = params.get('price') || ''
  const [qInput, setQInput] = useState(q)
  const [showFilters, setShowFilters] = useState(false)
  useEffect(() => setQInput(q), [q])

  const [min, max] = price ? price.split('-') : ['', '']
  const qs = new URLSearchParams({ sort, limit: '100' })
  if (q) qs.set('q', q)
  if (category) qs.set('category', category)
  if (min) qs.set('min_price', min)
  if (max) qs.set('max_price', max)
  const { data, error, loading, reload } = useFetch(`/api/products?${qs}`)
  const cats = useFetch('/api/products/categories')

  const set = (k, v) => {
    const next = new URLSearchParams(params)
    v ? next.set(k, v) : next.delete(k)
    setParams(next)
  }

  return (
    <div className="page shop">
      <div className="shop-head">
        <h1>{category || (q ? `Results for “${q}”` : 'Shop all')}</h1>
        {data && <p className="muted">{data.count} {data.count === 1 ? 'piece' : 'pieces'}</p>}
        <button className="btn btn-line filters-toggle" aria-expanded={showFilters} onClick={() => setShowFilters(!showFilters)}>
          {showFilters ? 'Hide filters' : 'Search and filter'}</button>
      </div>
      <div className="shop-layout">
        <aside className={`filters ${showFilters ? 'open' : ''}`} aria-label="Filters">
          <form onSubmit={(e) => { e.preventDefault(); set('q', qInput.trim()) }} className="filter-block">
            <label className="field-label" htmlFor="shop-q">Search</label>
            <input id="shop-q" className="input" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Product name" />
          </form>
          <div className="filter-block">
            <p className="field-label">Category</p>
            <button className={`chip ${!category ? 'on' : ''}`} onClick={() => set('category', '')}>All</button>
            {cats.data?.map((c) => (
              <button key={c.name} className={`chip ${category === c.name ? 'on' : ''}`} onClick={() => set('category', c.name)}>
                {c.name}<span className="chip-n">{c.count}</span>
              </button>
            ))}
          </div>
          <div className="filter-block">
            <p className="field-label">Price</p>
            {PRICES.map(([v, l]) => (
              <button key={v} className={`chip ${price === v ? 'on' : ''}`} onClick={() => set('price', v)}>{l}</button>
            ))}
          </div>
          <div className="filter-block">
            <label className="field-label" htmlFor="shop-sort">Sort by</label>
            <select id="shop-sort" className="input" value={sort} onChange={(e) => set('sort', e.target.value)}>
              {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          {(q || category || price) && <button className="link-u" onClick={() => setParams({})}>Clear filters</button>}
        </aside>
        <section className="grid-wrap">
          {loading && <Loading label="Finding pieces" />}
          {error && <ErrorState error={error} retry={reload} />}
          {data && data.items.length === 0 && (
            <Empty title="Nothing matches yet" action={<button className="btn btn-line" onClick={() => setParams({})}>Show everything</button>}>
              Try another word or remove a filter.
            </Empty>
          )}
          {data && data.items.length > 0 && (
            <div className="pgrid">{data.items.map((p) => <ProductCard key={p.id} product={p} />)}</div>
          )}
        </section>
      </div>
    </div>
  )
}
