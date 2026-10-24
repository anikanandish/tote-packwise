// Real-time 3D carton (Three.js). Drag to rotate, scroll or pinch to zoom.
//
// Every box is built from the packing algorithm's placement data (cm, carton frame):
//   x along the carton length (left -> right), y back -> front, z up (always 0: one layer).
// Mapping to Three.js:  X = x - L/2,  Y = up,  Z = y - W/2  (positive Z faces the worker).
// Nothing is invented: no stacking, no repositioning. If WebGL is unavailable the
// existing SVG view is used instead.
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { IsoCarton } from './PackViews'

const PEACH = 0xFFBEA3
const INK = 0x292334
const LAV = 0xA99ACB
const PALETTE = ['#A99ACB', '#C9BDE3', '#8E7FB5', '#D8CFEA', '#B6A8D6']
const CARD = { light: { wall: 0xD9B494, wallIn: 0xC9A27F, floor: 0xE9CDB3, edge: 0x8E6E57, bg: null },
  dark: { wall: 0x4B3F5C, wallIn: 0x3F3550, floor: 0x554868, edge: 0xB9AAD6, bg: null } }

function webglOk() {
  try {
    const c = document.createElement('canvas')
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')))
  } catch { return false }
}

function textTexture(text, { bg = '#FFBEA3', fg = '#292334', w = 128, h = 128, round = true, font = 'bold 64px Archivo, sans-serif' } = {}) {
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const g = c.getContext('2d')
  if (bg) {
    g.fillStyle = bg
    if (round) { g.beginPath(); g.arc(w / 2, h / 2, Math.min(w, h) / 2 - 4, 0, Math.PI * 2); g.fill() } else g.fillRect(0, 0, w, h)
  }
  g.fillStyle = fg; g.font = font; g.textAlign = 'center'; g.textBaseline = 'middle'
  g.fillText(text, w / 2, h / 2 + 2)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 4
  return t
}

function disposeGroup(group) {
  group.traverse((o) => {
    o.geometry?.dispose?.()
    const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : []
    mats.forEach((m) => { m.map?.dispose?.(); m.dispose?.() })
  })
  group.clear()
}

function buildCarton(group, [L, W, H], theme) {
  const c = CARD[theme] || CARD.light
  const t = Math.max(0.15, Math.min(L, W) * 0.012) // wall thickness, cm
  const wallMat = new THREE.MeshStandardMaterial({ color: c.wall, roughness: 0.95, side: THREE.DoubleSide })
  const inMat = new THREE.MeshStandardMaterial({ color: c.wallIn, roughness: 0.95, side: THREE.DoubleSide })
  const glass = new THREE.MeshStandardMaterial({ color: c.wall, roughness: 1, transparent: true, opacity: 0.07, depthWrite: false, side: THREE.DoubleSide })
  const edgeMat = new THREE.LineBasicMaterial({ color: c.edge })

  const floor = new THREE.Mesh(new THREE.BoxGeometry(L + 2 * t, t, W + 2 * t), new THREE.MeshStandardMaterial({ color: c.floor, roughness: 1 }))
  floor.position.y = -t / 2
  floor.receiveShadow = true
  group.add(floor)

  const walls = [
    { size: [L + 2 * t, H, t], pos: [0, H / 2, -W / 2 - t / 2], mat: inMat },        // back
    { size: [t, H, W], pos: [-L / 2 - t / 2, H / 2, 0], mat: wallMat },              // left
    { size: [t, H, W], pos: [L / 2 + t / 2, H / 2, 0], mat: glass },                 // right (see-through)
    { size: [L + 2 * t, H, t], pos: [0, H / 2, W / 2 + t / 2], mat: glass },         // front (see-through)
  ]
  for (const w of walls) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(...w.size), w.mat)
    m.position.set(...w.pos)
    m.receiveShadow = w.mat !== glass
    group.add(m)
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry), edgeMat)
    e.position.copy(m.position)
    group.add(e)
  }
  // open flaps on the back and left (folded outwards so they never hide the contents)
  const flapMat = new THREE.MeshStandardMaterial({ color: c.wall, roughness: 0.95, side: THREE.DoubleSide })
  const fb = new THREE.Mesh(new THREE.PlaneGeometry(L, W / 2), flapMat)
  fb.geometry.translate(0, W / 4, 0)
  fb.position.set(0, H, -W / 2 - t)
  fb.rotation.x = -1.05
  group.add(fb)
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(W, W / 2), flapMat)
  fl.geometry.translate(0, W / 4, 0)
  fl.position.set(-L / 2 - t, H, 0)
  fl.rotation.y = Math.PI / 2
  fl.rotation.x = -1.05
  group.add(fl)

  // floor marking in front of the carton: which side faces the worker
  const label = new THREE.Mesh(new THREE.PlaneGeometry(Math.min(L * 0.9, 24), Math.min(L * 0.9, 24) / 8),
    new THREE.MeshBasicMaterial({ map: textTexture('FRONT · YOUR SIDE', { bg: null, fg: theme === 'dark' ? '#FFBEA3' : '#292334', w: 1024, h: 128, round: false, font: 'bold 72px Archivo, sans-serif' }), transparent: true }))
  label.rotation.x = -Math.PI / 2
  label.position.set(0, 0.02, W / 2 + t + Math.max(1.2, W * 0.1))
  group.add(label)
}

function buildItems(group, carton, placements, { currentRefs, doneRefs, colors, fragileRefs, dropFrom }) {
  const [L, W] = carton
  const drops = []
  placements.forEach((p, i) => {
    const pad = p.padding_cm || 0
    const fx = Math.max(0.05, p.dx - 2 * pad), fy = Math.max(0.05, p.dy - 2 * pad), fz = Math.max(0.05, p.dz - 2 * pad)
    const cx = p.x + p.dx / 2 - L / 2
    const cz = p.y + p.dy / 2 - W / 2
    const st = !currentRefs && !doneRefs ? 'all' : currentRefs?.has(p.unit_ref) ? 'current' : doneRefs?.has(p.unit_ref) ? 'done' : 'todo'

    if (st === 'todo') {
      // where it will go: outline of the full item, on the floor
      const g = new THREE.BoxGeometry(fx, fz, fy)
      const ghost = new THREE.LineSegments(new THREE.EdgesGeometry(g), new THREE.LineDashedMaterial({ color: LAV, dashSize: 0.5, gapSize: 0.35 }))
      ghost.computeLineDistances()
      ghost.position.set(cx, fz / 2, cz)
      group.add(ghost)
      const foot = new THREE.Mesh(new THREE.PlaneGeometry(fx, fy), new THREE.MeshBasicMaterial({ color: LAV, transparent: true, opacity: 0.22, depthWrite: false }))
      foot.rotation.x = -Math.PI / 2
      foot.position.set(cx, 0.03, cz)
      group.add(foot)
      g.dispose()
      return
    }

    // Item being placed now is peach (matches the "Place now" legend); others keep their product colour.
    const base = st === 'current' ? '#FFBEA3'
      : colors?.[p.unit_ref] || (fragileRefs?.has(p.unit_ref) ? '#FFBEA3' : PALETTE[i % PALETTE.length])
    const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(base), roughness: 0.55, metalness: 0.05 })
    if (st === 'current') { mat.emissive = new THREE.Color(PEACH); mat.emissiveIntensity = 0.25 }
    const box = new THREE.Mesh(new THREE.BoxGeometry(fx, fz, fy), mat)
    box.castShadow = true
    box.receiveShadow = true
    box.position.set(cx, fz / 2, cz)
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry),
      new THREE.LineBasicMaterial({ color: INK, transparent: st !== 'current', opacity: st === 'current' ? 1 : 0.45 }))
    box.add(edges)
    group.add(box)

    if (pad > 0) {
      // The padding is filled by the protective wrap: draw it as a translucent shell
      // the size of the slot the algorithm reserved (it is real, occupied space).
      const shell = new THREE.Mesh(new THREE.BoxGeometry(p.dx, p.dz, p.dy),
        new THREE.MeshStandardMaterial({ color: st === 'current' ? PEACH : 0xF4F1F8, transparent: true,
          opacity: st === 'current' ? 0.4 : 0.58, roughness: 0.3, depthWrite: false }))
      shell.position.set(cx, p.dz / 2, cz)
      const shellEdge = new THREE.LineSegments(new THREE.EdgesGeometry(shell.geometry),
        new THREE.LineBasicMaterial({ color: PEACH, transparent: true, opacity: 0.95 }))
      shell.add(shellEdge)
      group.add(shell)
    }
    if (st === 'current') {
      const s = Math.max(1.2, Math.min(L, W) * 0.14)
      const tag = new THREE.Sprite(new THREE.SpriteMaterial({ map: textTexture(String(p.seq)), depthTest: false }))
      tag.scale.set(s, s, 1)
      tag.position.set(0, fz / 2 + s * 0.75, 0)
      box.add(tag)
      if (dropFrom) drops.push({ obj: box, to: fz / 2, from: fz / 2 + dropFrom })
    }
  })
  return drops
}

export default function Carton3D({ carton, placements, currentRefs, doneRefs, colors, fragileRefs = new Set(),
  theme = 'light', autoRotate = false, className = '', height, frameDims }) {
  const hostRef = useRef(null)
  const ctx = useRef(null)
  const [ok] = useState(webglOk)
  const key = carton.join('x')
  const frameKey = (frameDims || carton).join('x')

  // one renderer per carton size; camera survives slide changes
  useEffect(() => {
    if (!ok || !hostRef.current) return
    const host = hostRef.current
    const [L, W, H] = carton
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.outputColorSpace = THREE.SRGBColorSpace
    host.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 2000)
    // frame the box plus its open flaps
    const [frameL, frameW, frameH] = frameDims || carton
    const r = Math.sqrt(frameL * frameL + frameW * frameW + (frameH + frameW * 0.5) ** 2) / 2
    const dist = (r / Math.sin((35 * Math.PI) / 360)) * 1.25
    const dir = new THREE.Vector3(0.45, 0.85, 1).normalize()
    const home = dir.multiplyScalar(dist)
    camera.position.copy(home)
    const target = new THREE.Vector3(0, frameH * 0.42, 0)

    scene.add(new THREE.HemisphereLight(0xffffff, theme === 'dark' ? 0x292334 : 0xe9d8c8, 1.1))
    const sun = new THREE.DirectionalLight(0xffffff, 1.6)
    sun.position.set(L * 0.4, H * 3 + r, W * 1.2)
    sun.castShadow = true
    sun.shadow.mapSize.set(1024, 1024)
    const sc = sun.shadow.camera
    sc.left = -r * 1.4; sc.right = r * 1.4; sc.top = r * 1.4; sc.bottom = -r * 1.4; sc.near = 0.1; sc.far = r * 10
    scene.add(sun)

    const cartonGroup = new THREE.Group()
    const itemGroup = new THREE.Group()
    scene.add(cartonGroup, itemGroup)
    buildCarton(cartonGroup, carton, theme)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.copy(target)
    controls.enableDamping = true
    controls.enablePan = false
    controls.minDistance = r * 1.2
    controls.maxDistance = r * 6
    controls.maxPolarAngle = Math.PI * 0.48
    controls.autoRotate = autoRotate
    controls.autoRotateSpeed = 0.8
    controls.update()

    const resize = () => {
      const w = host.clientWidth || 300
      const h = host.clientHeight || 260
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(host)
    resize()

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf
    const state = { drops: [], t0: 0 }
    const loop = (t) => {
      raf = requestAnimationFrame(loop)
      if (state.drops.length) {
        const k = Math.min(1, (t - state.t0) / 320)
        const e = 1 - Math.pow(1 - k, 3)
        state.drops.forEach((d) => { d.obj.position.y = d.from + (d.to - d.from) * e })
        if (k >= 1) state.drops = []
      }
      controls.update()
      renderer.render(scene, camera)
    }
    raf = requestAnimationFrame(loop)

    ctx.current = { itemGroup, state, reduce, controls, camera, home, target, H }
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      disposeGroup(cartonGroup); disposeGroup(itemGroup)
      renderer.dispose()
      host.removeChild(renderer.domElement)
      ctx.current = null
    }
  }, [ok, key, frameKey, theme]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (ctx.current) ctx.current.controls.autoRotate = autoRotate
  }, [autoRotate])

  // rebuild the items whenever the step changes
  useEffect(() => {
    const c = ctx.current
    if (!c) return
    disposeGroup(c.itemGroup)
    c.state.drops = buildItems(c.itemGroup, carton, placements, {
      currentRefs, doneRefs, colors, fragileRefs, dropFrom: c.reduce ? 0 : Math.max(2, c.H * 0.45),
    })
    c.state.t0 = performance.now()
  }, [placements, currentRefs, doneRefs, colors, fragileRefs, key]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!ok) {
    return <IsoCarton carton={carton} placements={placements} currentRefs={currentRefs} doneRefs={doneRefs}
      fragileRefs={fragileRefs} theme={theme} showFront />
  }

  const resetView = () => {
    const c = ctx.current
    if (!c) return
    c.camera.position.copy(c.home)
    c.controls.target.copy(c.target)
    c.controls.update()
  }

  return (
    <div className={`c3d c3d-${theme} ${className}`} style={height ? { height } : undefined}>
      <div ref={hostRef} className="c3d-canvas" role="img"
        aria-label={`3D view of a ${carton.join(' by ')} centimetre carton with ${placements.length} items in one layer`} />
      <button type="button" className="c3d-reset" onClick={resetView}>Reset view</button>
      <span className="c3d-hint">Drag to turn · scroll to zoom</span>
    </div>
  )
}
