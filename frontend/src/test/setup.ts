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
}
