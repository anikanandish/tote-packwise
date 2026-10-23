import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import ProductArt from '../components/ProductArt'
import ProductCard from '../components/ProductCard'
import { ErrorState, Icon, Loading, Qty, Stars } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useShop } from '../context/ShopContext'
import { money } from '../lib/format'
import useFetch from '../lib/useFetch'

export default function Product() {
  const { slug } = useParams()
  const { data: p, error, loading, reload } = useFetch(`/api/products/${slug}`)
  const { add, inWishlist, toggleWish, viewed, cart } = useShop()
  const { user } = useAuth()
  const nav = useNavigate()
  const [qty, setQty] = useState(1)
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (p) { viewed(p); setQty(1) } }, [p?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <Loading />
  if (error) return <div className="page"><ErrorState error={error} retry={error.status === 404 ? null : reload} />
    {error.status === 404 && <p className="center"><Link to="/shop" className="link-u">Back to the shop</Link></p>}</div>

  const inBag = cart.items.find((i) => i.product.id === p.id)?.quantity || 0
  const canAdd = p.stock - inBag
  const wished = inWishlist(p.id)
  const pk = p.packaging

  return (
    <div className="page pdp">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/shop">Shop</Link><span>/</span><Link to={`/shop?category=${encodeURIComponent(p.category)}`}>{p.category}</Link>
      </nav>
      <div className="pdp-grid">
        <div className="pdp-media"><ProductArt product={p} /></div>
        <div className="pdp-info">
          <p className="pcard-brand">{p.brand}</p>
          <h1 className="pdp-title">{p.name}</h1>
          <Stars value={p.rating} count={p.rating_count} />
          <p className="pdp-price">{money(p.price)}</p>
          <p className="pdp-desc">{p.description}</p>

          <p className={`stock ${p.stock === 0 ? 'out' : p.stock <= 10 ? 'low' : ''}`}>
            {p.stock === 0 ? 'Sold out' : p.stock <= 10 ? `Only ${p.stock} left` : 'In stock'}
            {inBag > 0 && <span className="muted"> · {inBag} in your bag</span>}
          </p>

          <div className="pdp-buy">
            <Qty value={qty} onChange={setQty} max={Math.max(1, canAdd)} disabled={canAdd <= 0} />
            <button className="btn btn-wine btn-grow" disabled={canAdd <= 0 || busy}
              onClick={async () => { setBusy(true); await add(p, qty); setBusy(false) }}>
              {p.stock === 0 ? 'Sold out' : canAdd <= 0 ? 'All stock is in your bag' : busy ? 'Adding…' : 'Add to bag'}
            </button>
            <button className={`btn btn-icon ${wished ? 'on' : ''}`} aria-pressed={wished}
              aria-label={wished ? 'Remove from wishlist' : 'Save to wishlist'}
              onClick={() => (user ? toggleWish(p) : nav(`/login?next=/product/${p.slug}`))}>
              <Icon.heart filled={wished} />
            </button>
          </div>

          <dl className="pdp-specs">
            <div><dt>Size</dt><dd>{pk.length_cm} × {pk.width_cm} × {pk.height_cm} cm</dd></div>
            <div><dt>Weight</dt><dd>{pk.weight_g >= 1000 ? `${(pk.weight_g / 1000).toFixed(2)} kg` : `${pk.weight_g} g`}</dd></div>
            {p.fragile && <div><dt>Packed with</dt><dd>Extra protection for fragile pieces</dd></div>}
          </dl>
        </div>
      </div>

      <section className="reviews">
        <div className="row-head"><h2>Reviews</h2><span className="tag">Demo reviews for this hackathon store</span></div>
        <div className="review-list">
          {p.reviews.map((r, i) => (
            <article key={i} className="review">
              <Stars value={r.rating} />
              <h3>{r.title}</h3>
              <p>{r.body}</p>
              <p className="muted">{r.author}</p>
            </article>
          ))}
        </div>
      </section>

      {p.related.length > 0 && (
        <section className="row">
          <div className="row-head"><h2>You may also like</h2></div>
          <div className="row-scroll">{p.related.map((r) => <ProductCard key={r.id} product={r} />)}</div>
        </section>
      )}
    </div>
  )
}
