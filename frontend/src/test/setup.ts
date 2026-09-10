/**
 * Test setup.
 *
 * These tests run against the REAL FastAPI backend on 127.0.0.1:8000 when it
 * is reachable (that is the point — we want to catch shape mismatches between
 * the API and the UI, which mocks would hide). Tests that need the API skip
 * themselves with a clear message when it is not running.
 */
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeAll } from 'vitest'

export const API_BASE = process.env.PEHRA_API_BASE ?? 'http://127.0.0.1:8000'

let apiUp = false
export const isApiUp = () => apiUp

beforeAll(async () => {
  try {
    const r = await fetch(`${API_BASE}/api/health`)
    apiUp = r.ok
  } catch {
    apiUp = false
  }
  if (!apiUp) {
    console.warn(
      `\n[pehra] Backend not reachable at ${API_BASE} — API-backed tests will be skipped.\n` +
        `        Start it with: cd backend && PYTHONPATH=. .venv/bin/uvicorn app.main:app --port 8000\n`,
    )
  }
})

afterEach(() => cleanup())

/* jsdom gaps that Leaflet and our components rely on ---------------------- */
if (typeof window !== 'undefined') {
  window.matchMedia =
    window.matchMedia ||
    ((query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList)

  if (!('EventSource' in window)) {
    // Our live provider falls back to polling when SSE is unavailable, which is
    // exactly what we want in tests.
    Object.defineProperty(window, 'EventSource', { value: undefined, writable: true })
  }

  // Leaflet uses the canvas renderer (preferCanvas) for the risk field, ward
  // polygons and threat cells. jsdom has no 2D canvas context, so we stub a
  // no-op context: the maps still mount and the DOM around them (badges,
  // legends, HUD overlays) is what the tests assert on.
  const noop2d = {
    canvas: null as unknown,
    drawImage: () => {},
    clearRect: () => {},
    fillRect: () => {},
    strokeRect: () => {},
    beginPath: () => {},
    closePath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    arc: () => {},
    arcTo: () => {},
    bezierCurveTo: () => {},
    quadraticCurveTo: () => {},
    rect: () => {},
    fill: () => {},
    stroke: () => {},
    clip: () => {},
    save: () => {},
    restore: () => {},
    translate: () => {},
    rotate: () => {},
    scale: () => {},
    setTransform: () => {},
    resetTransform: () => {},
    setLineDash: () => {},
    getLineDash: () => [] as number[],
    measureText: () => ({ width: 0 }) as TextMetrics,
    fillText: () => {},
    strokeText: () => {},
    createLinearGradient: () => ({ addColorStop: () => {} }),
    createRadialGradient: () => ({ addColorStop: () => {} }),
    createPattern: () => (null as unknown as CanvasPattern),
    putImageData: () => {},
    getImageData: () => ({ data: new Uint8ClampedArray(4) }),
    createImageData: () => ({ data: new Uint8ClampedArray(4) }),
  }
  const ctxStub = (w: unknown, h: unknown) => {
    noop2d.canvas = { width: w, height: h }
    return noop2d
  }
  ;(window.HTMLCanvasElement.prototype as unknown as { getContext: unknown }).getContext =
    ((type: string) => (type === '2d' ? ctxStub(300, 150) : null)) as never
}
