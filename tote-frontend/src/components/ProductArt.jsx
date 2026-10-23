// Illustrated still-life for each product, drawn in SVG from the product's `art` spec
// ({ shape, tone }). Every product in the catalogue shares one art direction, works offline,
// and never shows a broken image. If an admin sets image_url, that photo is used instead.
import { useState } from 'react'

function mix(hex, target, t) {
  const h = (hex || '#D9B88F').replace('#', '')
  const a = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16))
  const b = [0, 2, 4].map((i) => parseInt(target.slice(i, i + 2), 16))
  return '#' + a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, '0')).join('')
}
const light = (c, t) => mix(c, 'FFF9F0', t)
const dark = (c, t) => mix(c, '1A1416', t)

const GOLD = '#C9A46A'

const SHAPES = {
  lipstick: (c) => (<g>
    <rect x="96" y="168" width="48" height="82" rx="4" fill={dark(c, 0.55)} />
    <rect x="96" y="168" width="14" height="82" fill={light(dark(c, 0.55), 0.18)} />
    <rect x="100" y="146" width="40" height="24" rx="2" fill={GOLD} />
    <path d="M104 146 V98 Q104 86 116 80 L136 70 V146 Z" fill={c} />
    <path d="M104 146 V98 Q104 86 116 80 L120 78 V146 Z" fill={light(c, 0.25)} />
  </g>),
  flatbottle: (c) => (<g>
    <rect x="94" y="96" width="52" height="22" rx="3" fill={dark(c, 0.5)} />
    <rect x="76" y="116" width="88" height="134" rx="14" fill={light(c, 0.35)} opacity="0.95" />
    <rect x="80" y="150" width="80" height="96" rx="10" fill={c} />
    <rect x="92" y="176" width="56" height="34" rx="2" fill="#FFF9F0" />
    <rect x="100" y="186" width="40" height="3" fill={dark(c, 0.5)} /><rect x="106" y="194" width="28" height="2" fill={dark(c, 0.3)} />
  </g>),
  pen: (c) => (<g transform="rotate(-18 120 170)">
    <rect x="110" y="70" width="20" height="180" rx="6" fill={c} />
    <rect x="110" y="70" width="6" height="180" rx="3" fill={light(c, 0.25)} />
    <rect x="108" y="150" width="24" height="8" fill={GOLD} />
    <path d="M114 70 L120 52 L126 70 Z" fill={dark(c, 0.3)} />
  </g>),
  perfume: (c) => (<g>
    <rect x="102" y="70" width="36" height="36" rx="4" fill={GOLD} />
    <rect x="108" y="104" width="24" height="16" fill={dark(GOLD, 0.25)} />
    <path d="M72 128 Q72 118 82 118 H158 Q168 118 168 128 V238 Q168 250 156 250 H84 Q72 250 72 238 Z" fill={light(c, 0.45)} />
    <path d="M82 134 H158 V236 H82 Z" fill={c} opacity="0.85" />
    <path d="M82 134 L110 134 L92 236 H82 Z" fill="#FFF9F0" opacity="0.35" />
    <rect x="98" y="182" width="44" height="18" fill="#FFF9F0" /><rect x="106" y="189" width="28" height="3" fill={dark(c, 0.5)} />
  </g>),
  dropper: (c) => (<g>
    <path d="M110 62 Q120 50 130 62 V100 H110 Z" fill={dark(c, 0.55)} />
    <rect x="104" y="98" width="32" height="20" rx="3" fill={GOLD} />
    <rect x="90" y="118" width="60" height="132" rx="10" fill={c} />
    <rect x="94" y="122" width="12" height="122" rx="6" fill="#FFF9F0" opacity="0.4" />
    <rect x="100" y="170" width="40" height="40" fill="#FFF9F0" opacity="0.85" />
  </g>),
  jar: (c) => (<g>
    <rect x="70" y="168" width="100" height="30" rx="6" fill={GOLD} />
    <rect x="66" y="196" width="108" height="54" rx="12" fill={light(c, 0.2)} />
    <rect x="72" y="200" width="14" height="44" rx="7" fill="#FFF9F0" opacity="0.5" />
    <rect x="100" y="212" width="40" height="18" fill={dark(c, 0.2)} opacity="0.35" />
  </g>),
  compact: (c) => (<g>
    <ellipse cx="120" cy="226" rx="62" ry="22" fill={dark(c, 0.35)} />
    <ellipse cx="120" cy="220" rx="62" ry="22" fill={GOLD} />
    <ellipse cx="120" cy="219" rx="48" ry="15" fill={c} />
    <ellipse cx="108" cy="215" rx="16" ry="5" fill="#FFF9F0" opacity="0.6" />
    <path d="M58 214 Q58 120 120 112 Q182 120 182 214" fill="none" stroke={GOLD} strokeWidth="10" />
    <path d="M70 208 Q72 132 120 124 Q168 132 170 208 Z" fill={light(c, 0.55)} opacity="0.9" />
  </g>),
  headphones: (c) => (<g>
    <path d="M70 180 Q70 80 120 80 Q170 80 170 180" fill="none" stroke={c} strokeWidth="14" strokeLinecap="round" />
    <path d="M76 170 Q76 96 120 96 Q164 96 164 170" fill="none" stroke={light(c, 0.3)} strokeWidth="4" />
    <rect x="54" y="160" width="40" height="72" rx="18" fill={c} /><rect x="146" y="160" width="40" height="72" rx="18" fill={c} />
    <rect x="62" y="170" width="10" height="52" rx="5" fill={light(c, 0.35)} />
  </g>),
  earbuds: (c) => (<g>
    <rect x="72" y="176" width="96" height="74" rx="34" fill={c} />
    <path d="M72 206 H168" stroke={dark(c, 0.2)} strokeWidth="2" />
    <circle cx="96" cy="150" r="16" fill={light(c, 0.1)} stroke={dark(c, 0.15)} /><rect x="91" y="150" width="10" height="34" rx="5" fill={light(c, 0.1)} />
    <circle cx="148" cy="146" r="16" fill={light(c, 0.1)} stroke={dark(c, 0.15)} /><rect x="143" y="146" width="10" height="34" rx="5" fill={light(c, 0.1)} />
  </g>),
  cable: (c) => (<g fill="none" stroke={c} strokeWidth="9" strokeLinecap="round">
    <ellipse cx="120" cy="214" rx="56" ry="26" /><ellipse cx="120" cy="206" rx="46" ry="20" stroke={light(c, 0.2)} />
    <path d="M166 210 Q190 180 170 150" /><rect x="160" y="128" width="18" height="26" rx="3" fill={dark(c, 0.45)} stroke="none" />
  </g>),
  phonecase: (c) => (<g>
    <rect x="80" y="64" width="80" height="186" rx="20" fill={c} />
    <rect x="80" y="64" width="16" height="186" rx="8" fill={light(c, 0.15)} />
    <rect x="94" y="80" width="32" height="38" rx="9" fill={dark(c, 0.45)} />
    <circle cx="104" cy="92" r="5" fill="#2a2a2a" /><circle cx="116" cy="106" r="5" fill="#2a2a2a" />
  </g>),
  watch: (c) => (<g>
    <rect x="100" y="60" width="40" height="190" rx="10" fill={light(c, 0.15)} />
    <rect x="84" y="118" width="72" height="80" rx="18" fill={GOLD} />
    <rect x="90" y="124" width="60" height="68" rx="14" fill={dark(c, 0.3)} />
    <path d="M120 140 V158 L132 166" stroke={light(c, 0.8)} strokeWidth="3" fill="none" strokeLinecap="round" />
  </g>),
  speaker: (c) => (<g>
    <rect x="78" y="112" width="84" height="138" rx="38" fill={c} />
    {Array.from({ length: 30 }, (_, i) => <circle key={i} cx={92 + (i % 6) * 11} cy={150 + Math.floor(i / 6) * 14} r="2.2" fill={dark(c, 0.45)} />)}
    <rect x="104" y="122" width="32" height="6" rx="3" fill={light(c, 0.3)} />
  </g>),
  scarf: (c) => (<g>
    <path d="M60 180 Q120 160 180 180 L180 238 Q120 222 60 238 Z" fill={c} />
    <path d="M60 196 Q120 176 180 196" stroke={light(c, 0.35)} strokeWidth="3" fill="none" />
    <path d="M60 214 Q120 194 180 214" stroke={dark(c, 0.2)} strokeWidth="2" fill="none" />
    <path d="M70 140 Q120 120 170 140 L180 180 Q120 160 60 180 Z" fill={light(c, 0.2)} />
    {Array.from({ length: 12 }, (_, i) => <path key={i} d={`M${64 + i * 10} 236 v14`} stroke={dark(c, 0.15)} strokeWidth="2" />)}
  </g>),
  bag: (c) => (<g>
    <path d="M96 124 Q96 76 120 76 Q144 76 144 124" fill="none" stroke={dark(c, 0.25)} strokeWidth="8" />
    <path d="M70 124 H170 L178 250 H62 Z" fill={c} />
    <path d="M70 124 H88 L82 250 H62 Z" fill={light(c, 0.15)} />
    <rect x="108" y="146" width="24" height="12" rx="2" fill={GOLD} />
  </g>),
  sunglasses: (c) => (<g>
    <rect x="70" y="218" width="100" height="30" rx="14" fill={dark(c, 0.4)} />
    <path d="M60 150 H180" stroke={c} strokeWidth="6" />
    <ellipse cx="90" cy="168" rx="30" ry="24" fill={c} /><ellipse cx="150" cy="168" rx="30" ry="24" fill={c} />
    <ellipse cx="90" cy="168" rx="23" ry="17" fill={dark(c, 0.6)} /><ellipse cx="150" cy="168" rx="23" ry="17" fill={dark(c, 0.6)} />
    <path d="M78 160 l10 -6" stroke="#FFF9F0" strokeWidth="3" opacity="0.6" /><path d="M138 160 l10 -6" stroke="#FFF9F0" strokeWidth="3" opacity="0.6" />
  </g>),
  scrunchie: (c) => (<g>
    {[[96, 226, '#FFF9F0'], [144, 226, '#722F37'], [120, 186, c]].map(([x, y, col], i) => (
      <g key={i}><ellipse cx={x} cy={y} rx="34" ry="22" fill={col} stroke={dark(c, 0.2)} strokeWidth="1" />
        <ellipse cx={x} cy={y} rx="12" ry="7" fill={light(c, 0.7)} /></g>))}
  </g>),
  cardholder: (c) => (<g>
    <rect x="66" y="150" width="108" height="96" rx="8" fill={c} />
    <rect x="66" y="134" width="108" height="24" rx="4" fill={light(c, 0.65)} transform="rotate(-6 120 146)" />
    <path d="M66 182 H174 M66 210 H174" stroke={light(c, 0.2)} strokeWidth="2" />
    <text x="120" y="236" textAnchor="middle" fontFamily="Bodoni Moda, serif" fontSize="14" fill={GOLD}>T</text>
  </g>),
  earrings: (c) => (<g>
    <rect x="70" y="200" width="100" height="50" rx="4" fill={light('#D9B88F', 0.3)} />
    {[100, 140].map((x) => (<g key={x}><path d={`M${x} 110 q-8 10 0 22 v30`} stroke={GOLD} strokeWidth="3" fill="none" />
      <circle cx={x} cy={178} r="16" fill={c} stroke={dark(c, 0.12)} /><circle cx={x - 5} cy={172} r="5" fill="#fff" opacity="0.8" /></g>))}
  </g>),
  candle: (c) => (<g>
    <path d="M120 96 Q128 108 120 120 Q112 108 120 96 Z" fill="#F4B860" />
    <rect x="118" y="118" width="4" height="22" fill="#2a2a2a" />
    <rect x="78" y="136" width="84" height="114" rx="8" fill={c} opacity="0.92" />
    <rect x="82" y="140" width="76" height="16" fill={light(c, 0.6)} />
    <rect x="84" y="140" width="10" height="106" fill="#FFF9F0" opacity="0.25" />
    <rect x="96" y="182" width="48" height="36" fill="#FFF9F0" /><rect x="104" y="196" width="32" height="3" fill={dark(c, 0.5)} />
  </g>),
  mug: (c) => (<g>
    <path d="M158 160 Q192 160 192 190 Q192 220 158 220" fill="none" stroke={c} strokeWidth="12" />
    <path d="M70 140 H162 V232 Q162 250 144 250 H88 Q70 250 70 232 Z" fill={c} />
    <path d="M70 140 H162 V160 Q116 172 70 160 Z" fill={dark(c, 0.15)} />
    <rect x="80" y="150" width="10" height="88" rx="5" fill="#FFF9F0" opacity="0.4" />
  </g>),
  linen: (c) => (<g>
    {[0, 1, 2, 3].map((i) => <rect key={i} x={70 - i * 2} y={222 - i * 22} width={100 + i * 4} height="24" rx="4" fill={i % 2 ? light(c, 0.25) : c} stroke={dark(c, 0.15)} />)}
    <rect x="70" y="150" width="104" height="8" fill={GOLD} opacity="0.8" />
  </g>),
  vase: (c) => (<g>
    <path d="M118 140 Q112 90 126 56" stroke="#6B7A4F" strokeWidth="3" fill="none" />
    <ellipse cx="128" cy="54" rx="10" ry="7" fill="#C98B7A" />
    <path d="M110 132 H130 Q132 160 150 190 Q164 216 150 240 Q144 250 120 250 Q96 250 90 240 Q76 216 90 190 Q108 160 110 132 Z" fill={c} stroke={dark(c, 0.12)} />
    <path d="M96 200 Q92 220 98 238" stroke="#FFF9F0" strokeWidth="5" opacity="0.6" fill="none" />
  </g>),
  diffuser: (c) => (<g>
    {[-14, -4, 6, 16].map((d, i) => <path key={i} d={`M120 130 L${120 + d * 3} ${50 + i * 6}`} stroke="#8C6A4F" strokeWidth="3" />)}
    <rect x="108" y="122" width="24" height="18" fill={GOLD} />
    <rect x="86" y="138" width="68" height="112" rx="10" fill={c} opacity="0.95" />
    <rect x="90" y="142" width="10" height="104" fill="#FFF9F0" opacity="0.25" />
    <rect x="100" y="182" width="40" height="32" fill="#FFF9F0" />
  </g>),
  book: (c) => (<g>
    <rect x="80" y="76" width="86" height="174" rx="3" fill={c} />
    <rect x="80" y="76" width="16" height="174" fill={dark(c, 0.3)} />
    <rect x="166" y="80" width="6" height="168" fill="#F4ECDF" />
    <rect x="108" y="110" width="44" height="2" fill={GOLD} /><rect x="112" y="118" width="36" height="2" fill={GOLD} />
    <text x="130" y="186" textAnchor="middle" fontFamily="Bodoni Moda, serif" fontStyle="italic" fontSize="16" fill={light(c, 0.8)}>Quiet</text>
  </g>),
  notebook: (c) => (<g>
    <rect x="76" y="84" width="96" height="166" rx="6" fill={c} />
    <rect x="80" y="88" width="88" height="160" rx="4" fill="none" stroke={dark(c, 0.15)} />
    <rect x="148" y="84" width="6" height="166" fill={dark(c, 0.55)} />
    {Array.from({ length: 6 }, (_, i) => <circle key={i} cx={96 + (i % 3) * 14} cy={120 + Math.floor(i / 3) * 14} r="1.6" fill={dark(c, 0.4)} />)}
  </g>),
  fountainpen: (c) => (<g transform="rotate(-32 120 170)">
    <rect x="112" y="60" width="16" height="130" rx="8" fill={c} />
    <rect x="112" y="60" width="5" height="130" rx="3" fill={light(c, 0.35)} />
    <rect x="110" y="140" width="20" height="6" fill={dark(c, 0.3)} />
    <path d="M114 190 L120 236 L126 190 Z" fill={light(GOLD, 0.2)} /><path d="M120 196 V226" stroke={dark(c, 0.5)} />
  </g>),
  bookmark: (c) => (<g>
    {[0, 1, 2].map((i) => (<g key={i} transform={`rotate(${(i - 1) * 10} 120 250)`}>
      <rect x="104" y="80" width="32" height="170" rx="2" fill="#FFF9F0" stroke={dark('#D9B88F', 0.2)} />
      <circle cx="120" cy={130 + i * 20} r="8" fill={i === 1 ? c : light(c, 0.3)} /><path d={`M120 ${138 + i * 20} v30`} stroke="#6B7A4F" strokeWidth="2" /></g>))}
  </g>),
  planner: (c) => (<g>
    <path d="M140 230 v30 l6 -6 l6 6 v-30" fill="#722F37" />
    <rect x="72" y="92" width="100" height="148" rx="4" fill={c} />
    <rect x="72" y="92" width="100" height="148" rx="4" fill="none" stroke={light(c, 0.2)} strokeDasharray="2 3" />
    <text x="122" y="170" textAnchor="middle" fontFamily="Bodoni Moda, serif" fontSize="26" fill={GOLD}>2027</text>
  </g>),
  box: (c) => (<g>
    <path d="M70 140 L120 116 L170 140 V226 L120 250 L70 226 Z" fill={c} />
    <path d="M70 140 L120 164 L170 140 M120 164 V250" stroke={dark(c, 0.2)} fill="none" />
  </g>),
}

export default function ProductArt({ product, className = '' }) {
  const [broken, setBroken] = useState(false)
  if (product?.image_url && !broken) {
    return <img className={`art ${className}`} src={product.image_url} alt={product.name} loading="lazy" onError={() => setBroken(true)} />
  }
  const tone = product?.art?.tone || '#D9B88F'
  const shape = SHAPES[product?.art?.shape] || SHAPES.box
  const backdrop = light(tone, 0.82)
  return (
    <svg className={`art ${className}`} viewBox="0 0 240 300" role="img" aria-label={product?.name || 'Product'} preserveAspectRatio="xMidYMid slice">
      <rect width="240" height="300" fill={backdrop} />
      <rect y="250" width="240" height="50" fill={mix(backdrop, 'D9B88F', 0.35)} />
      <ellipse cx="120" cy="252" rx="78" ry="9" fill={dark(backdrop, 0.25)} opacity="0.35" />
      {shape(tone)}
    </svg>
  )
}
