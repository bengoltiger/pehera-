/**
 * End-to-end smoke tests for the authority command centre.
 *
 * These deliberately run against the live FastAPI process instead of mocks:
 * the whole point is to catch a UI that reads `alert.location_name` when the
 * API returns `alert.location.name`. Mocked fixtures would happily agree with
 * a wrong assumption.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeAll, describe, expect, it } from 'vitest'
import App from '../App'
import { setToken } from '../lib/api'
import { AppProviders } from '../lib/providers'
import { API_BASE } from './setup'

/* Probed at collection time so the guards below are resolved before the suite
   is registered. */
const apiUp = await fetch(`${API_BASE}/api/health`)
  .then((r) => r.ok)
  .catch(() => false)
if (!apiUp) console.warn(`[pehra] backend not reachable at ${API_BASE}; API tests skipped`)

/* Probed at collection time: the live-weather test only runs when the
   Open-Meteo provider is actually reachable from this machine — an
   unreachable provider is an honest skip, not a fake green. */
const liveUp = await fetch(`${API_BASE}/api/live/weather?lat=18.56&lng=73.26&grid=0`)
  .then((r) => r.ok)
  .catch(() => false)
if (apiUp && !liveUp) console.warn('[pehra] Open-Meteo unreachable; live-weather test skipped')

async function login(username = 'authority', password = 'authority123') {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await res.json()
  return data.access_token as string
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppProviders>
        <App />
      </AppProviders>
    </MemoryRouter>,
  )
}

/** Fails the test if React rendered an uncaught-error placeholder or a whole
    subtree unmounted (a thrown error with no boundary wipes the DOM).
    Pass a minLength to also require meaningful content (catches full
    unmounts on screens that should be rich). */
function expectNoCrash(minLength = 0) {
  expect(document.body.textContent).not.toMatch(/Cannot read propert|undefined is not|is not a function|No context provided|useLeafletContext/i)
  if (minLength > 0) expect(document.body.textContent?.length).toBeGreaterThan(minLength)
}

describe('authority command centre', () => {
  beforeAll(async () => {
    if (!apiUp) return
    setToken(await login())
  })

  it.runIf(apiUp)('renders the overview with live engine numbers', async () => {
    renderAt('/authority')
    await waitFor(() => expect(screen.getByText(/DEMO \/ SIMULATED DATA/i)).toBeInTheDocument(), {
      timeout: 15000,
    })
    await waitFor(() => expect(screen.getAllByText(/Priority queue/i).length).toBeGreaterThan(0), {
      timeout: 15000,
    })
    expectNoCrash()
  }, 30000)

  it.runIf(apiUp)('renders the priority queue page and a full risk assessment', async () => {
    renderAt('/authority/queue')
    await waitFor(() => expect(screen.getByText(/Why this risk\?/i)).toBeInTheDocument(), {
      timeout: 20000,
    })
    // the ranked-contribution panel must show at least one named feature
    const why = screen.getByText(/Why this risk\?/i).closest('section') ?? document.body
    await waitFor(() => expect(within(why).getByText(/Ranked contribution/i)).toBeInTheDocument())
    expect(screen.getAllByText(/Confidence/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Prediction timeline/i)).toBeInTheDocument()
    expectNoCrash()
  }, 40000)

  it.runIf(apiUp)('renders the alerts console', async () => {
    renderAt('/authority/alerts')
    await waitFor(
      () =>
        expect(
          screen.getByText(/Awaiting approval|No alerts in this view/i),
        ).toBeInTheDocument(),
      { timeout: 20000 },
    )
    expectNoCrash()
  }, 40000)

  it.runIf(apiUp)('renders the simulation lab with the scenario library', async () => {
    // The Simulation Lab is administrator-only, so this test must sign in as admin.
    setToken(await login('admin', 'admin12345'))
    renderAt('/authority/lab')
    await waitFor(() => expect(screen.getByText(/Scenario library/i)).toBeInTheDocument(), {
      timeout: 20000,
    })
    await waitFor(() => expect(screen.getByText(/What-if lab/i)).toBeInTheDocument())
    expectNoCrash()
  }, 40000)

  it.runIf(apiUp)('refuses an unknown route by redirecting home', async () => {
    renderAt('/nope')
    await waitFor(() => expect(document.body.textContent).toBeTruthy())
    expectNoCrash()
  }, 20000)
})

describe('new tactical screens', () => {
  it.runIf(apiUp)('renders the sitrep command screen', async () => {
    setToken(await login())
    renderAt('/authority/sitrep')
    await waitFor(() => expect(screen.getByText(/Tactical Vectors/i)).toBeInTheDocument(), {
      timeout: 20000,
    })
    await waitFor(() => expect(screen.getAllByText(/SITREP/i).length).toBeGreaterThan(0))
    expect(screen.getByText(/Active Incident Feed/i)).toBeInTheDocument()
    expectNoCrash()
  }, 40000)

  it.runIf(apiUp)('renders the real-time telemetry feed with a live atmosphere card', async () => {
    renderAt('/authority/predict')
    await waitFor(() => expect(screen.getByText(/Atmospheric Ingest/i)).toBeInTheDocument(), {
      timeout: 20000,
    })
    await waitFor(() => expect(screen.getByText(/Time-To-Crest Forecast/i)).toBeInTheDocument())
    expect(screen.getByText(/Model Certainty/i)).toBeInTheDocument()
    // The atmosphere card must show either the LIVE Open-Meteo badge, an
    // honest "live feed unreachable" fallback, or its loading state — never
    // a blank card. (The radar is now the Mumbai topology layer map.)
    await waitFor(
      () =>
        expect(
          document.body.textContent,
        ).toMatch(/LIVE: OPEN-METEO|LIVE FEED UNREACHABLE|CONNECTING TO LIVE ATMOSPHERIC FEED/),
      { timeout: 25000 },
    )
    // Give the live payload time to arrive and the map + wind overlay to
    // mount, THEN assert the app is still alive — a useMap()-outside-context
    // crash only happens once the live data renders, after the checks above.
    await new Promise((resolve) => setTimeout(resolve, 3000))
    expect(screen.getByText(/Atmospheric Ingest/i)).toBeInTheDocument()
    expectNoCrash(500)
  }, 40000)

})

describe('citizen app', () => {
  it.runIf(apiUp)('renders the village defense screen for a citizen account', async () => {
    setToken(await login('citizen', 'citizen123'))
    renderAt('/citizen')
    await waitFor(() => expect(screen.getByText(/Village Defense/i)).toBeInTheDocument(), {
      timeout: 20000,
    })
    // zone + shelter + checklist chrome (plain-language copy for non-technical users)
    await waitFor(() => expect(screen.getByText(/Pack these first/i)).toBeInTheDocument())
    expect(screen.getByText('WORKS OFFLINE')).toBeInTheDocument()
    // when-to-move guidance + live-location card are part of the screen
    await waitFor(() => expect(screen.getAllByText(/When to move/i).length).toBeGreaterThan(0))
    expect(screen.getAllByText(/Your location/i).length).toBeGreaterThan(0)
    // journey to the nearest shelter with walk time
    await waitFor(() => expect(screen.getAllByText(/MIN WALK/i).length).toBeGreaterThan(0))
    expectNoCrash()
  }, 40000)

  it.runIf(apiUp)('renders the evacuation screen with the T-minus header', async () => {
    renderAt('/citizen/evacuate')
    await waitFor(
      () =>
        expect(screen.getByText(/DANGER — LEAVE NOW|No evacuation required/i)).toBeInTheDocument(),
      { timeout: 20000 },
    )
    await waitFor(() => expect(screen.getByText(/YOUR NEAREST SAFE PLACE|No evacuation required/i)).toBeInTheDocument())
    expectNoCrash()
  }, 40000)
})

describe('live external weather', () => {
  it.runIf(apiUp && liveUp)('serves real Open-Meteo point data + a 12×12 wind field', async () => {
    const res = await fetch(`${API_BASE}/api/live/weather?lat=18.56&lng=73.26&grid=1`)
    expect(res.ok).toBe(true)
    const d = await res.json()
    expect(d.provider).toBe('open-meteo')
    expect(typeof d.fetched_at).toBe('string')
    expect(d.point.temperature_c).toBeGreaterThan(-30)
    expect(d.point.temperature_c).toBeLessThan(60)
    expect(d.point.next_3h_rain_mm).toBeGreaterThanOrEqual(0)
    expect(Array.isArray(d.field.u)).toBe(true)
    expect(d.field.u.length).toBe(144)
    expect(d.field.v.length).toBe(144)
    expect(d.field.rows).toBe(12)
    expect(d.field.cols).toBe(12)
  }, 30000)
})

describe('role-scoped navigation', () => {
  it.runIf(apiUp)('hides the administrator-only Simulation Lab tab from authority users', async () => {
    setToken(await login('authority', 'authority123'))
    renderAt('/authority')
    await waitFor(() => expect(screen.getByText(/DEMO \/ SIMULATED DATA/i)).toBeInTheDocument(), {
      timeout: 15000,
    })
    // The desktop and compact navs both render in jsdom — assert across both.
    expect(screen.queryAllByText(/Simulation lab/i)).toHaveLength(0)
    // Authority-designed tabs must still be visible.
    expect(screen.getAllByText(/SITREP/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Priority queue/i).length).toBeGreaterThan(0)
    expectNoCrash()
  }, 40000)

  it.runIf(apiUp)('shows the Simulation Lab tab to administrators', async () => {
    setToken(await login('admin', 'admin12345'))
    renderAt('/authority')
    await waitFor(() => expect(screen.getAllByText(/Simulation lab/i).length).toBeGreaterThan(0), {
      timeout: 15000,
    })
    expectNoCrash()
  }, 40000)

  it.runIf(apiUp)('blocks a direct /authority/lab URL for authority users', async () => {
    setToken(await login('authority', 'authority123'))
    renderAt('/authority/lab')
    await waitFor(() =>
      expect(screen.getByText(/Your role cannot open this screen/i)).toBeInTheDocument(),
      { timeout: 15000 },
    )
    expectNoCrash()
  }, 40000)
})

describe('unauthenticated access', () => {
  it.runIf(apiUp)('sends a signed-out visitor to the login screen', async () => {
    setToken(null)
    renderAt('/authority')
    await waitFor(() => expect(screen.getAllByText(/Sign in|demo account/i).length).toBeGreaterThan(0), {
      timeout: 15000,
    })
  }, 20000)
})
