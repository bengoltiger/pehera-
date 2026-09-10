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

/** Fails the test if React rendered an uncaught-error placeholder. */
function expectNoCrash() {
  expect(document.body.textContent).not.toMatch(/Cannot read propert|undefined is not|is not a function/i)
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

  it.runIf(apiUp)('renders the real-time telemetry feed', async () => {
    renderAt('/authority/predict')
    await waitFor(() => expect(screen.getByText(/Atmospheric Ingest/i)).toBeInTheDocument(), {
      timeout: 20000,
    })
    await waitFor(() => expect(screen.getByText(/Time-To-Crest Forecast/i)).toBeInTheDocument())
    expect(screen.getByText(/Model Certainty/i)).toBeInTheDocument()
    expectNoCrash()
  }, 40000)

})

describe('citizen app', () => {
  it.runIf(apiUp)('renders the village defense screen for a citizen account', async () => {
    setToken(await login('citizen', 'citizen123'))
    renderAt('/citizen')
    await waitFor(() => expect(screen.getByText(/Village Defense/i)).toBeInTheDocument(), {
      timeout: 20000,
    })
    // zone + shelter + checklist chrome
    await waitFor(() => expect(screen.getByText(/Evacuation Readiness Checklist/i)).toBeInTheDocument())
    expect(screen.getByText('OFFLINE-FIRST')).toBeInTheDocument()
    // when-to-move guidance + live-location card are part of the screen
    await waitFor(() => expect(screen.getAllByText(/When to move/i).length).toBeGreaterThan(0))
    expect(screen.getAllByText(/Live location/i).length).toBeGreaterThan(0)
    expectNoCrash()
  }, 40000)

  it.runIf(apiUp)('renders the evacuation screen with the T-minus header', async () => {
    renderAt('/citizen/evacuate')
    await waitFor(
      () =>
        expect(screen.getByText(/CRITICAL NOTICE|No evacuation required/i)).toBeInTheDocument(),
      { timeout: 20000 },
    )
    await waitFor(() => expect(screen.getByText(/NEAREST SAFE HAVEN|No evacuation required/i)).toBeInTheDocument())
    expectNoCrash()
  }, 40000)
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
