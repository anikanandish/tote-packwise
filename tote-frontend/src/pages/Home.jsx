import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { CATEGORIES } from '../components/Layout'
import ProductArt from '../components/ProductArt'
import ProductCard from '../components/ProductCard'
import { ErrorState, Loading } from '../components/ui'
import { useShop } from '../context/ShopContext'
import { money } from '../lib/format'
import useFetch from '../lib/useFetch'

function useParallax(ref, strength = 0.08) {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let raf
    const on = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        ref.current?.querySelectorAll('[data-depth]').forEach((el) => {
          el.style.transform = `translate3d(0, ${-window.scrollY * strength * Number(el.dataset.depth)}px, 0)`
        })
      })
    }
    window.addEventListener('scroll', on, { passive: true })
    return () => { window.removeEventListener('scroll', on); cancelAnimationFrame(raf) }
  }, [ref, strength])
}

function Hero({ products }) {
  const ref = useRef(null)
  useParallax(ref)
  const [a, b, c] = products
  return (
    <section className="hero" ref={ref}>
      <div className="hero-copy">
        <h1 className="hero-title">
          <span>Fewer,</span>
          <span>better</span>
          <span className="hero-title-it">things.</span>
        </h1>
        <p className="hero-lede">A small edit of beauty, objects and tech we would keep for years — from a weighted matte lipstick to a brass pen that ages with you.</p>
        <div className="hero-cta">
          <Link to="/shop" className="btn btn-wine">Shop the edit</Link>
          <Link to="/shop?category=Beauty" className="btn btn-line">Beauty</Link>
        </div>
      </div>
      <div className="hero-stage" aria-hidden>
        {a && <Link to={`/product/${a.slug}`} className="hero-tile hero-tile-a" data-depth="1.6" tabIndex={-1}><ProductArt product={a} /></Link>}
        {b && <Link to={`/product/${b.slug}`} className="hero-tile hero-tile-b" data-depth="0.6" tabIndex={-1}><ProductArt product={b} /></Link>}
        {c && <Link to={`/product/${c.slug}`} className="hero-tile hero-tile-c" data-depth="2.4" tabIndex={-1}><ProductArt product={c} /></Link>}
        {a && <p className="hero-caption" data-depth="1.6">{a.name}<span>{money(a.price)}</span></p>}
      </div>
    </section>
  )
}

function Row({ title, sub, link, items }) {
  if (!items?.length) return null
  return (
    <section className="row">
      <div className="row-head">
        <div><h2>{title}</h2>{sub && <p className="muted">{sub}</p>}</div>
        {link && <Link to={link} className="link-u">View all</Link>}
      </div>
      <div className="row-scroll">{items.map((p) => <ProductCard key={p.id} product={p} />)}</div>
    </section>
  )
}

function BeautyEdit({ items }) {
  if (!items?.length) return null
  return (
    <section className="edit">
      <div className="edit-side">
        <div className="edit-sticky">
          <h2 className="edit-title">The beauty edit</h2>
          <p>Wine-dark lips, a liner with a 0.1 mm point and a rose-and-oud parfum in hand-finished glass. Eight pieces that do their job beautifully.</p>
          <Link to="/shop?category=Beauty" className="btn btn-line">Shop beauty</Link>
        </div>
      </div>
      <div className="edit-grid">{items.map((p) => <ProductCard key={p.id} product={p} size="lg" />)}</div>
    </section>
  )
}

export default function Home() {
  const featured = useFetch('/api/products?featured=true&limit=12')
  const newest = useFetch('/api/products?sort=newest&limit=10')
  const beauty = useFetch('/api/products?category=Beauty&sort=rating&limit=6')
  const { recent } = useShop()

  if (featured.loading) return <Loading label="Opening the shop" />
  if (featured.error) return <div className="page"><ErrorState error={featured.error} retry={featured.reload} /></div>
  const f = featured.data.items
  const heroPicks = ['rose-oud-eau-de-parfum', 'structured-mini-tote', 'velvet-matte-lipstick']
    .map((s) => f.find((p) => p.slug === s)).filter(Boolean)

  return (
    <div className="home">
      <Hero products={heroPicks.length === 3 ? heroPicks : f.slice(0, 3)} />

      <nav className="cats" aria-label="Shop by category">
        {CATEGORIES.map((c) => (
          <Link key={c} to={`/shop?category=${encodeURIComponent(c)}`} className="cat">
            <span className="cat-name">{c}</span>
          </Link>
        ))}
      </nav>

      <Row title="Featured" sub="What we reach for first" link="/shop" items={f.filter((p) => !heroPicks.includes(p))} />
      <BeautyEdit items={beauty.data?.items} />
      <Row title="New in" sub="Recently added to the shop" link="/shop?sort=newest" items={newest.data?.items} />
      {recent.length > 0 && <Row title="Recently viewed" items={recent} />}
    </div>
  )
}
