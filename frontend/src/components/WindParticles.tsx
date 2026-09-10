/**
 * WindParticles — canvas-2D "god's-eye view" of the live wind field.
 *
 * Deliberately dependency-free (no WebGL, no leaflet-plugin): the Predict
 * screen targets cheap phones on flaky networks, so the animation is a single
 * 2D canvas with a few hundred particles advected through the bilinearly
 * sampled Open-Meteo u/v grid, drawn as short streaks. ~1.5 MB of zero extra
 * network cost — the field itself comes from /api/live/weather (cached 10 min
 * server-side).
 *
 * Mounted inside a Leaflet map via useMap(); the canvas overlays the
 * OSM tiles and follows the view on move/zoom/resize.
 */
import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import type { LiveWindField } from '../lib/types'

interface Particle {
  lat: number
  lng: number
  prevLat: number
  prevLng: number
  age: number
  maxAge: number
}

/** Speed (km/h) → streak colour. Blue = calm, teal = breeze, amber = strong, red = dangerous. */
function speedColor(kmh: number): string {
  if (kmh < 5) return 'rgba(125, 211, 252, 0.6)'
  if (kmh < 12) return 'rgba(94, 234, 212, 0.7)'
  if (kmh < 25) return 'rgba(250, 204, 21, 0.75)'
  return 'rgba(248, 113, 113, 0.85)'
}

/**
 * Exaggeration for visual motion. Physical speed at 30 fps is sub-pixel on a
 * city-scale map; wind visualisations conventionally speed particles up.
 * Tuned so even a 2–3 km/h night breeze reads as visible drift, and 25+ km/h
 * reads as a clear flow.
 */
const VISUAL_BOOST = 42

function sample(field: LiveWindField, lat: number, lng: number): { u: number; v: number } | null {
  const r = (lat - field.origin_lat) / field.step_deg
  const c = (lng - field.origin_lng) / field.step_deg
  const r0 = Math.floor(r)
  const c0 = Math.floor(c)
  if (r0 < 0 || c0 < 0 || r0 >= field.rows - 1 || c0 >= field.cols - 1) return null
  const fr = r - r0
  const fc = c - c0
  const at = (row: number, col: number) => row * field.cols + col
  const u =
    field.u[at(r0, c0)] * (1 - fr) * (1 - fc) +
    field.u[at(r0, c0 + 1)] * (1 - fr) * fc +
    field.u[at(r0 + 1, c0)] * fr * (1 - fc) +
    field.u[at(r0 + 1, c0 + 1)] * fr * fc
  const v =
    field.v[at(r0, c0)] * (1 - fr) * (1 - fc) +
    field.v[at(r0, c0 + 1)] * (1 - fr) * fc +
    field.v[at(r0 + 1, c0)] * fr * (1 - fc) +
    field.v[at(r0 + 1, c0 + 1)] * fr * fc
  if (!Number.isFinite(u) || !Number.isFinite(v)) return null
  return { u, v }
}

export function WindParticles({
  field,
  enabled = true,
}: {
  field: LiveWindField
  enabled?: boolean
}) {
  const map = useMap()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    if (!enabled) return
    const container = map.getContainer()
    const canvas = document.createElement('canvas')
    canvas.style.position = 'absolute'
    canvas.style.inset = '0'
    canvas.style.pointerEvents = 'none'
    canvas.style.zIndex = '450' // above overlay vectors (400), below markers (600)
    canvas.setAttribute('aria-hidden', 'true')
    container.appendChild(canvas)
    canvasRef.current = canvas
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      canvas.remove()
      return
    }

    const particles: Particle[] = []
    let raf = 0
    let frame = 0
    let running = true

    const resize = () => {
      const size = container.clientWidth
      const height = container.clientHeight
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.max(1, Math.floor(size * dpr))
      canvas.height = Math.max(1, Math.floor(height * dpr))
      canvas.style.width = `${size}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const rand = (a: number, b: number) => a + Math.random() * (b - a)

    const spawn = (): Particle => ({
      lat: rand(field.origin_lat, field.origin_lat + (field.rows - 1) * field.step_deg),
      lng: rand(field.origin_lng, field.origin_lng + (field.cols - 1) * field.step_deg),
      prevLat: 0,
      prevLng: 0,
      age: 0,
      maxAge: Math.floor(rand(50, 140)),
    })

    const target = () =>
      Math.max(250, Math.min(1300, Math.round((container.clientWidth * container.clientHeight) / 1600)))

    const seed = () => {
      const n = target()
      particles.length = 0
      for (let i = 0; i < n; i += 1) {
        const p = spawn()
        p.prevLat = p.lat
        p.prevLng = p.lng
        p.age = Math.floor(rand(0, p.maxAge)) // desync trails
        particles.push(p)
      }
    }

    const inBounds = (lat: number, lng: number) =>
      lat >= field.origin_lat &&
      lat <= field.origin_lat + (field.rows - 1) * field.step_deg &&
      lng >= field.origin_lng &&
      lng <= field.origin_lng + (field.cols - 1) * field.step_deg

    const step = () => {
      if (!running) return
      frame += 1
      if (frame % 2 === 1) {
        // ~30 fps on a 60 Hz display; halves the CPU on phones
        raf = requestAnimationFrame(step)
        return
      }
      const w = container.clientWidth
      const h = container.clientHeight
      ctx.clearRect(0, 0, w, h)
      if (w < 10 || h < 10) return

      for (const p of particles) {
        p.age += 1
        const wind = sample(field, p.lat, p.lng)
        if (!wind || p.age > p.maxAge || !inBounds(p.lat, p.lng)) {
          const np = spawn()
          p.lat = np.lat
          p.lng = np.lng
          p.prevLat = np.lat
          p.prevLng = np.lng
          p.age = 0
          p.maxAge = np.maxAge
          continue
        }
        p.prevLat = p.lat
        p.prevLng = p.lng
        const cosLat = Math.cos((p.lat * Math.PI) / 180) || 1
        p.lat += (wind.v / 3600 / 111) * VISUAL_BOOST
        p.lng += (wind.u / 3600 / (111 * cosLat)) * VISUAL_BOOST
        const a = map.latLngToContainerPoint([p.prevLat, p.prevLng])
        const b = map.latLngToContainerPoint([p.lat, p.lng])
        const kmh = Math.hypot(wind.u, wind.v)
        ctx.strokeStyle = speedColor(kmh)
        ctx.lineWidth = 1.2
        ctx.beginPath()
        // draw a short streak (from previous position back a hair) so calm
        // wind still shows a grain of motion
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
      }
      raf = requestAnimationFrame(step)
    }

    resize()
    seed()
    raf = requestAnimationFrame(step)

    const stop = () => {
      running = false
      cancelAnimationFrame(raf)
    }
    const onResize = () => {
      resize()
      seed()
    }
    const onVis = () => {
      if (document.hidden) {
        stop()
      } else if (!running) {
        running = true
        raf = requestAnimationFrame(step)
      }
    }

    map.on('resize', onResize)
    document.addEventListener('visibilitychange', onVis)

    return () => {
      stop()
      map.off('resize', onResize)
      document.removeEventListener('visibilitychange', onVis)
      canvas.remove()
      canvasRef.current = null
    }
  }, [map, field, enabled])

  return null
}
