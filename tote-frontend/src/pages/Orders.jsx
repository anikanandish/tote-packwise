import { Link, useParams, useSearchParams } from 'react-router-dom'
import ProductArt from '../components/ProductArt'
import { Empty, ErrorState, Icon, Loading } from '../components/ui'
import { date, money, STATUS_FLOW, STATUS_LABEL } from '../lib/format'
import useFetch from '../lib/useFetch'

export function OrderList() {
  const { data, error, loading, reload } = useFetch('/api/orders')
  if (loading) return <Loading label="Loading your orders" />
  if (error) return <div className="page"><ErrorState error={error} retry={reload} /></div>
  return (
    <div className="page narrow">
      <h1>Your orders</h1>
      {!data.length && <Empty title="No orders yet" action={<Link to="/shop" className="btn btn-wine">Browse the shop</Link>}>Orders you place appear here with live tracking.</Empty>}
      <ul className="order-list">
        {data.map((o) => (
          <li key={o.id}>
            <Link to={`/order/${o.code}`} className="order-row">
              <div className="order-thumbs">{o.items.slice(0, 3).map((i) => <ProductArt key={i.product_id} product={i} />)}</div>
              <div>
                <p className="order-code">{o.code}</p>
                <p className="muted">{date(o.created_at)} · {o.items.reduce((s, i) => s + i.quantity, 0)} items · {money(o.total)}</p>
              </div>
              <span className={`status status-${o.status}`}>{STATUS_LABEL[o.status]}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function OrderTrack() {
  const { code } = useParams()
  const [params] = useSearchParams()
  const { data: o, error, loading, reload } = useFetch(`/api/orders/${code}`)
  if (loading) return <Loading label="Finding your order" />
  if (error) return <div className="page"><ErrorState error={error} retry={reload} /></div>

  const reached = Object.fromEntries(o.timeline.map((e) => [e.status, e]))
  const current = STATUS_FLOW.indexOf(o.status)

  return (
    <div className="page narrow track">
      {params.get('placed') && (
        <div className="placed">
          <h1>Thank you — your order is in.</h1>
          <p>We have sent it to our warehouse to be packed. Your order number is <strong>{o.code}</strong>.</p>
          <p className="muted small">Simulated payment reference {o.payment_ref}. No money was charged.</p>
        </div>
      )}
      {!params.get('placed') && <h1>Order {o.code}</h1>}

      <div className="track-head">
        <div><p className="muted">Status</p><p className="track-status">{STATUS_LABEL[o.status]}</p></div>
        <button className="btn btn-line" onClick={reload}>Refresh status</button>
      </div>

      <ol className="timeline">
        {STATUS_FLOW.map((s, i) => {
          const ev = reached[s]
          const state = i < current || (i === current) ? 'done' : 'todo'
          return (
            <li key={s} className={`tl tl-${state} ${i === current ? 'tl-now' : ''}`}>
              <span className="tl-dot">{state === 'done' && <Icon.check />}</span>
              <div><p className="tl-label">{STATUS_LABEL[s]}</p>
                {ev && <p className="muted small">{date(ev.at)}{ev.note ? ` · ${ev.note}` : ''}</p>}</div>
            </li>
          )
        })}
      </ol>

      <div className="track-grid">
        <section>
          <h2>Items</h2>
          <ul className="sum-lines">
            {o.items.map((i) => <li key={i.product_id}><span>{i.name} <span className="muted">× {i.quantity}</span></span><span>{money(i.unit_price * i.quantity)}</span></li>)}
          </ul>
          <dl className="summary-dl">
            <div><dt>Subtotal</dt><dd>{money(o.subtotal)}</dd></div>
            <div><dt>Delivery</dt><dd>{o.shipping ? money(o.shipping) : 'Free'}</dd></div>
            <div className="summary-total"><dt>Total</dt><dd>{money(o.total)}</dd></div>
          </dl>
        </section>
        <section>
          <h2>Delivering to</h2>
          <p>{o.contact.name}<br />{o.address.line1}{o.address.line2 && <><br />{o.address.line2}</>}<br />{o.address.city}, {o.address.state} {o.address.postal_code}</p>
        </section>
      </div>
      <Link to="/orders" className="link-u">All orders</Link>
    </div>
  )
}
