import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useShop } from '../context/ShopContext'
import { money } from '../lib/format'
import ProductArt from './ProductArt'
import { Icon } from './ui'

export default function ProductCard({ product, size = 'md' }) {
  const { add, inWishlist, toggleWish } = useShop()
  const { user } = useAuth()
  const nav = useNavigate()
  const wished = inWishlist(product.id)

  const onWish = async (e) => {
    e.preventDefault()
    if (!user) return nav(`/login?next=/product/${product.slug}`)
    toggleWish(product)
  }

  return (
    <article className={`pcard pcard-${size}`}>
      <Link to={`/product/${product.slug}`} className="pcard-media" aria-label={product.name}>
        <ProductArt product={product} />
        {!product.in_stock && <span className="pcard-flag">Sold out</span>}
        {product.in_stock && product.stock <= 10 && <span className="pcard-flag">Only {product.stock} left</span>}
      </Link>
      <button className={`pcard-wish ${wished ? 'on' : ''}`} onClick={onWish} aria-pressed={wished}
        aria-label={wished ? `Remove ${product.name} from wishlist` : `Save ${product.name} to wishlist`}>
        <Icon.heart filled={wished} />
      </button>
      <div className="pcard-body">
        <p className="pcard-brand">{product.brand}</p>
        <Link to={`/product/${product.slug}`} className="pcard-name">{product.name}</Link>
        <div className="pcard-foot">
          <span className="pcard-price">{money(product.price)}</span>
          <button className="pcard-add" disabled={!product.in_stock} onClick={() => add(product, 1)}>
            {product.in_stock ? 'Add to bag' : 'Sold out'}
          </button>
        </div>
      </div>
    </article>
  )
}
