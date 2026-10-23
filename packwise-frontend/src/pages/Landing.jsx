import { Link } from 'react-router-dom'
import Carton3D from '../components/Carton3D'
import { Logo } from '../components/Shell'
import { useAuth } from '../context/AuthContext'
import useFetch from '../lib/useFetch'

function LiveCarton() {
  const { data, error, loading, reload } = useFetch('/api/public/engine-preview')
  if (loading) return <div className="hero-viz-msg">Asking the packing engine…</div>
  if (error || !data?.fits) {
    return (
      <div className="hero-viz-msg">
        <p><strong>The packing engine is not answering.</strong></p>
        <p>{error?.message || data?.message}</p>
        <p>Start the C++ service, then <button className="linkbtn" onClick={reload}>ask again</button>. Nothing is drawn until real coordinates arrive.</p>
      </div>
    )
  }
  const placements = data.placements.map((p) => ({ ...p, unit_ref: p.id, x: p.x / 10, y: p.y / 10, z: 0, dx: p.dx / 10, dy: p.dy / 10, dz: p.dz / 10 }))
  const fragile = new Set(data.placements.filter((p) => p.fragile).map((p) => p.id))
  const [L, W, H] = data.carton.dims_cm
  return (
    <figure className="hero-viz">
      <Carton3D carton={[L, W, H]} placements={placements} fragileRefs={fragile} theme="dark" autoRotate className="c3d-hero" />
      <figcaption>
        <span>Live from the C++ engine</span>
        {`${data.carton.name} carton, ${L} × ${W} × ${H} cm.`} {placements.length} items placed in one layer:{' '}
        {[...new Set(data.placements.map((p) => p.name))].join(', ')}.{fragile.size > 0 && ' Peach marks fragile, padded items.'}
        {data.rejected.length > 0 && <> Smaller cartons rejected: {data.rejected.map((r) => r.carton).join(', ')}.</>}
      </figcaption>
    </figure>
  )
}

export default function Landing() {
  const { session } = useAuth()
  const start = session ? '/queue' : '/login'
  return (
    <div className="landing">
      <header className="land-top">
        <Logo light />
        <Link to={start} className="btn btn-peach">{session ? 'Open the queue' : 'Sign in'}</Link>
      </header>

      <section className="land-hero">
        <div className="land-copy">
          <h1>The smallest standard carton that keeps it safe.</h1>
          <p>PackWise reads every TOTE order, lets the packing algorithm design a box around the items, checks it against real sizes, padding, weight and stock,
            and hands the packer an exact placement plan — so nothing ships in a box twice its size.</p>
          <div className="land-cta">
            <Link to={start} className="btn btn-peach btn-lg">{session ? 'Open the queue' : 'Start packing'}</Link>
            <a href="#how" className="btn btn-ghost-light btn-lg">How it decides</a>
          </div>
        </div>
        <LiveCarton />
      </section>

      <section className="land-how" id="how">
        <h2>How a carton is chosen</h2>
        <ol className="how-steps">
          <li><h3>Expand and pad</h3><p>Every unit in the order becomes a box from its catalogue size. Fragile items get at least 1 cm of padding on every side.</p></li>
          <li><h3>Rule out the impossible</h3><p>Cartons that are inactive, out of stock, too short, too narrow or over their weight limit are rejected with the exact reason.</p></li>
          <li><h3>Ask the engine to place</h3><p>For each remaining carton the C++ service runs the original width search: 200 row widths in both floor orientations, keeping the tightest layout that fits. It returns real coordinates.</p></li>
          <li><h3>Pick the smallest</h3><p>Of the active cartons (the eight standard sizes plus any the admin adds), the smallest one that passes every check wins, so the least air is shipped. Cost is shown against the baseline carton.</p></li>
        </ol>
      </section>

      <section className="land-honest">
        <div>
          <h2>What the engine does, and what it does not</h2>
          <p>We would rather show a smaller claim that is true.</p>
        </div>
        <dl>
          <div><dt>Does</dt><dd>Places items side by side in rows on the carton floor, turning them 90° when that helps.</dd></div>
          <div><dt>Does</dt><dd>Tries both floor orientations of every carton and explains each failure.</dd></div>
          <div><dt>Does not</dt><dd>Stack items. Every plan is a single layer, and the visualisation shows exactly that.</dd></div>
          <div><dt>Does not</dt><dd>Tip items over. Tall items need a tall enough carton.</dd></div>
          <div><dt>Does not</dt><dd>Estimate emissions. Reports show cost, volume and void space only.</dd></div>
        </dl>
      </section>

      <footer className="land-foot"><Logo light /><span>Warehouse companion to the TOTE store · hackathon build</span></footer>
    </div>
  )
}
