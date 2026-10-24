import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Carton3D from '../components/Carton3D'
import { Logo } from '../components/Shell'
import { useAuth } from '../context/AuthContext'
import useFetch from '../lib/useFetch'

function LiveCarton() {
  const previewUrl = ['localhost', '127.0.0.1'].includes(window.location.hostname)
    ? 'http://localhost:8000/api/public/engine-preview'
    : '/api/public/engine-preview'
  const { data, error, loading, reload } = useFetch(previewUrl)
  const [rotating, setRotating] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches)
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
      <div className={`hero-visual-stage${rotating ? '' : ' is-paused'}`}>
        <div className="hero-orbit" aria-hidden="true"><span /></div>
        <Carton3D carton={[L, W, H]} placements={placements} fragileRefs={fragile} theme="dark" autoRotate={rotating} className="c3d-hero" />
      </div>
      <figcaption>
        <span>Live from the C++ engine</span>
        {`${data.carton.name} carton, ${L} × ${W} × ${H} cm.`} {placements.length} items, packed in one layer:{' '}
        {[...new Set(data.placements.map((p) => p.name))].join(' + ')}.{fragile.size > 0 && ` Pale outlines show protective clearance around the products (${[...new Set(data.placements.filter((p) => p.padding_cm > 0).map((p) => `${p.padding_cm} cm padding`))].join(', ')}).`}
        {data.rejected.length > 0 && <> Smaller cartons rejected: {data.rejected.map((r) => r.carton).join(', ')}.</>}
        <button type="button" className="hero-motion-toggle" aria-pressed={rotating}
          onClick={() => setRotating((value) => !value)}>{rotating ? 'Pause rotation' : 'Resume rotation'}</button>
      </figcaption>
    </figure>
  )
}

function CartonComparisonArt() {
  return (
    <div className="land-compare-art">
      <svg viewBox="0 0 820 390" role="img" aria-labelledby="compare-art-title compare-art-desc">
        <title id="compare-art-title">The same items in two carton sizes</title>
        <desc id="compare-art-desc">A few products take up little room in a large carton, then fit with protective space in a smaller carton.</desc>
        <defs>
          <pattern id="unused-space" width="12" height="12" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <rect width="12" height="12" fill="#F2E9E0" />
            <path d="M0 0V12" stroke="#D8B9AA" strokeWidth="2" />
          </pattern>
          <linearGradient id="carton-face" x2="0" y2="1">
            <stop stopColor="#E3C4AA" />
            <stop offset="1" stopColor="#CBA687" />
          </linearGradient>
        </defs>
        <g className="compare-illustration-panel">
          <rect x="10" y="10" width="382" height="370" rx="22" />
          <text x="34" y="48" className="compare-svg-kicker">OVERSIZED CARTON</text>
          <text x="34" y="76" className="compare-svg-title">Room shipped unused</text>
          <path d="M64 146 210 91 342 139 195 199Z" fill="#F1DCCB" stroke="#95795F" strokeWidth="3" />
          <path d="M64 146 195 199 195 321 64 266Z" fill="url(#carton-face)" stroke="#95795F" strokeWidth="3" />
          <path d="M195 199 342 139 342 262 195 321Z" fill="#B99170" stroke="#95795F" strokeWidth="3" />
          <path d="M78 159 194 205 194 296 78 250Z" fill="url(#unused-space)" opacity=".82" />
          <path d="M211 205 328 157 328 251 211 299Z" fill="url(#unused-space)" opacity=".56" />
          <g className="compare-product">
            <path d="M115 210 139 200 158 208 134 219Z" fill="#FFE0D2" stroke="#62556A" strokeWidth="2" />
            <path d="M115 210 134 219 134 266 115 257Z" fill="#E6A98E" stroke="#62556A" strokeWidth="2" />
            <path d="M134 219 158 208 158 255 134 266Z" fill="#C98870" stroke="#62556A" strokeWidth="2" />
            <path d="M160 226 182 217 199 224 177 234Z" fill="#EEE8F3" stroke="#62556A" strokeWidth="2" />
            <path d="M160 226 177 234 177 273 160 265Z" fill="#C8BBD8" stroke="#62556A" strokeWidth="2" />
            <path d="M177 234 199 224 199 263 177 273Z" fill="#A798BB" stroke="#62556A" strokeWidth="2" />
          </g>
          <path d="M255 284h59" stroke="#6C5968" strokeWidth="2" strokeDasharray="5 5" />
          <text x="255" y="307" className="compare-svg-note">Empty space</text>
        </g>
        <g className="compare-illustration-panel">
          <rect x="428" y="10" width="382" height="370" rx="22" />
          <text x="452" y="48" className="compare-svg-kicker">PACKWISE PICK</text>
          <text x="452" y="76" className="compare-svg-title">Sized to the order</text>
          <path d="M482 187 620 135 758 184 620 238Z" fill="#F1DCCB" stroke="#95795F" strokeWidth="3" />
          <path d="M482 187 620 238 620 321 482 270Z" fill="url(#carton-face)" stroke="#95795F" strokeWidth="3" />
          <path d="M620 238 758 184 758 267 620 321Z" fill="#B99170" stroke="#95795F" strokeWidth="3" />
          <path d="M499 190 620 146 741 190 620 235Z" fill="none" stroke="#E79A7B" strokeWidth="2" strokeDasharray="5 5" />
          <g className="compare-product">
            <path d="M548 194 572 184 591 191 567 202Z" fill="#FFE0D2" stroke="#62556A" strokeWidth="2" />
            <path d="M548 194 567 202 567 257 548 249Z" fill="#E6A98E" stroke="#62556A" strokeWidth="2" />
            <path d="M567 202 591 191 591 246 567 257Z" fill="#C98870" stroke="#62556A" strokeWidth="2" />
            <path d="M596 201 618 192 635 199 613 209Z" fill="#EEE8F3" stroke="#62556A" strokeWidth="2" />
            <path d="M596 201 613 209 613 258 596 250Z" fill="#C8BBD8" stroke="#62556A" strokeWidth="2" />
            <path d="M613 209 635 199 635 248 613 258Z" fill="#A798BB" stroke="#62556A" strokeWidth="2" />
            <path d="M640 207 659 199 675 205 656 214Z" fill="#FFE0D2" stroke="#62556A" strokeWidth="2" />
            <path d="M640 207 656 214 656 259 640 252Z" fill="#E6A98E" stroke="#62556A" strokeWidth="2" />
            <path d="M656 214 675 205 675 250 656 259Z" fill="#C98870" stroke="#62556A" strokeWidth="2" />
          </g>
          <text x="511" y="296" className="compare-svg-note">Protective clearance kept</text>
        </g>
      </svg>
      <p>Illustrative view · actual carton and placements come from the packing engine.</p>
    </div>
  )
}

export default function Landing() {
  const { session } = useAuth()
  const landingRef = useRef(null)
  const [headlineWord, setHeadlineWord] = useState(0)
  const start = session ? '/queue' : '/login'
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined
    const timer = window.setInterval(() => setHeadlineWord((word) => (word + 1) % 3), 2600)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    const root = landingRef.current
    if (!root) return
    const elements = root.querySelectorAll('.land-reveal')
    if (!('IntersectionObserver' in window)) {
      elements.forEach((element) => element.classList.add('is-visible'))
      return
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        }
      })
    }, { threshold: 0.12, rootMargin: '0px 0px -4% 0px' })
    elements.forEach((element) => observer.observe(element))
    return () => observer.disconnect()
  }, [])
  return (
    <div className="landing" ref={landingRef}>
      <header className="land-top">
        <Logo light />
        <Link to={start} className="btn btn-peach">{session ? 'Open the queue' : 'Sign in'}</Link>
      </header>

      <section className="land-hero">
        <div className="land-copy">
          <p className="land-eyebrow"><span /> PACKING, WITH LESS WASTE</p>
          <h1>The right-size carton ships <span className="headline-orbit-word" key={headlineWord}>{['less air.', 'with care.', 'more efficiently.'][headlineWord]}</span></h1>
          <p>PackWise reads every TOTE order, lets the packing algorithm design a box around the items, checks it against real sizes, padding, weight and stock,
            and hands the packer an exact placement plan — so nothing ships in a box twice its size.</p>
          <div className="land-cta">
            <Link to={start} className="btn btn-peach btn-lg">{session ? 'Open the queue' : 'Start packing'}</Link>
            <a href="#comparison" className="btn btn-ghost-light btn-lg">See the difference</a>
          </div>
          <div className="land-facts" aria-label="PackWise at a glance">
            <div><b>16</b><span>standard carton sizes</span></div>
            <div><b>1</b><span>clear placement plan</span></div>
            <div><b>0</b><span>guesswork for the packer</span></div>
          </div>
        </div>
        <LiveCarton />
      </section>

      <section className="land-comparison" id="comparison">
        <div className="land-comparison-copy land-reveal">
          <p className="land-eyebrow land-eyebrow-dark"><span /> SAME ORDER · DIFFERENT CARTON</p>
          <h2>Stop shipping empty space.</h2>
          <p>The packing engine checks each stocked size, protects the products, then picks the smallest carton that passes.</p>
          <a href="#how" className="land-text-link">See how the choice is made <span aria-hidden="true">→</span></a>
        </div>
        <div className="land-reveal"><CartonComparisonArt /></div>
      </section>

      <section className="land-how" id="how">
        <h2 className="land-reveal">How a carton is chosen</h2>
        <ol className="how-steps">
          <li className="land-reveal" style={{ '--reveal-delay': '0ms' }}><h3>Expand and pad</h3><p>Every unit in the order becomes a box from its catalogue size. Fragile items get at least 1 cm of padding on every side.</p></li>
          <li className="land-reveal" style={{ '--reveal-delay': '70ms' }}><h3>Rule out the impossible</h3><p>Cartons that are inactive, out of stock, too short, too narrow or over their weight limit are rejected with the exact reason.</p></li>
          <li className="land-reveal" style={{ '--reveal-delay': '140ms' }}><h3>Ask the engine to place</h3><p>For each remaining carton the C++ service runs the original width search: 200 row widths in both floor orientations, keeping the tightest layout that fits. It returns real coordinates.</p></li>
          <li className="land-reveal" style={{ '--reveal-delay': '210ms' }}><h3>Pick the smallest</h3><p>Of the active cartons (the eight standard sizes plus any the admin adds), the smallest one that passes every check wins, so the least air is shipped. Cost is shown against the baseline carton.</p></li>
        </ol>
      </section>

      <section className="land-honest">
        <div className="land-reveal">
          <h2>What the engine does, and what it does not</h2>
          <p>We would rather show a smaller claim that is true.</p>
        </div>
        <dl className="land-reveal">
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
