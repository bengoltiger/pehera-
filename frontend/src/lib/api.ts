/**
 * Typed API client.
 *
 * Three rules the whole UI depends on:
 *  1. Only relative URLs. The browser talks to its own origin; Vite proxies
 *     /api to FastAPI in dev, FastAPI serves the SPA itself in production.
 *  2. Errors are never swallowed. Every failure becomes a PehraError carrying
 *     the backend's structured reason, which the UI is expected to SHOW.
 *  3. No client-side risk logic. This file moves JSON; it never computes a
 *     score, a level or a threshold.
 */
import type {
  Alert,
  AlertLevel,
  ApiError,
  CitizenEntry,
  CitizensResponse,
  ClockControlResponse,
  Connectivity,
  DataHealth,
  EarlySignal,
  EngineConfig,
  EvacuationPlan,
  ForecastEntry,
  Health,
  HeartbeatBody,
  HeartbeatResponse,
  Hospital,
  HospitalList,
  Lang,
  LiveWeather,
  LocationSummary,
  MapLayers,
  ModelInfo,
  ObservationMeta,
  Overview,
  PersonasResponse,
  PriorityEntry,
  ProviderInfo,
  RainfallForecast,
  RainfallState,
  ReRouteResult,
  RiskCell,
  RiskField,
  RiskResponse,
  RoutePlan,
  RoutingProvidersResponse,
  SafeRoute,
  SafeRoutePlan,
  Scenario,
  Shelter,
  ShelterList,
  SimClock,
  StormState,
  StormTrack,
  TerrainGrid,
  ThreatCell,
  TokenResponse,
  TopologyResponse,
  TrafficState,
  User,
} from './types'

const TOKEN_KEY = 'pehra.token'
const BASE_OVERRIDE_KEY = 'pehra.api_base'

/**
 * Where the API lives. Priority:
 *   1. a runtime override (the APK's Settings screen saves it to localStorage
 *      under `pehra.api_base`, so the same build can point at any live server);
 *   2. `VITE_API_BASE` (build-time; normal web deployments keep this empty and
 *      let FastAPI serve the SPA on the same origin, or Vite proxy in dev).
 */
const ENV_API_BASE: string = (import.meta.env?.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? ''

export function getApiBase(): string {
  try {
    const override = localStorage.getItem(BASE_OVERRIDE_KEY)
    if (override) return override.replace(/\/$/, '')
  } catch {
    /* storage disabled */
  }
  return ENV_API_BASE
}

export function setApiBase(url: string) {
  try {
    if (url && url.trim()) localStorage.setItem(BASE_OVERRIDE_KEY, url.trim().replace(/\/$/, ''))
    else localStorage.removeItem(BASE_OVERRIDE_KEY)
  } catch {
    /* ignore */
  }
  // force a reload so every cached URL uses the new base
  if (typeof window !== 'undefined') window.location.reload()
}

export const API_BASE_URL: string = getApiBase()

export const apiUrl = (path: string) => `${getApiBase()}${path}`

export class PehraError extends Error {
  status: number
  payload: ApiError

  constructor(status: number, payload: ApiError) {
    super(payload?.message || `Request failed (${status})`)
    this.name = 'PehraError'
    this.status = status
    this.payload = payload
  }

  /** True when the user simply is not allowed — worth showing calmly. */
  get isAuth() {
    return this.status === 401 || this.status === 403
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage disabled — session-only auth still works */
  }
}

type Method = 'GET' | 'POST' | 'PATCH' | 'DELETE'

async function request<T>(
  path: string,
  { method = 'GET', body, signal }: { method?: Method; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') throw err
    throw new PehraError(0, {
      error: 'network_unreachable',
      message:
        'Cannot reach the PEHRA server. You may be offline — the last values shown are cached and are no longer live.',
    })
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  let payload: unknown = null
  // A successful response that is not JSON means the request never reached the
  // PEHRA API (e.g. a host serves index.html for /api/*). That is an ERROR, not
  // data — returning it would make every `.map(...)` downstream crash.
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      throw new PehraError(response.status, {
        error: 'bad_response',
        message:
          'The server answered, but not with JSON. Check the API URL in Settings — ' +
          'the request may be hitting a page instead of the PEHRA backend.',
      })
    }
  }

  if (!response.ok) {
    const err = (payload ?? {}) as ApiError
    if (response.status === 401) setToken(null)
    throw new PehraError(response.status, {
      ...err,
      error: err.error || 'error',
      message: err.message || `Request failed with status ${response.status}.`,
    })
  }
  return payload as T
}

const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const usp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') usp.set(k, String(v))
  }
  const s = usp.toString()
  return s ? `?${s}` : ''
}

/* ========================================================================== */

export const api = {
  /* ---- system ---------------------------------------------------------- */
  health: () => request<Health>('/api/health'),
  config: () => request<EngineConfig>('/api/config'),
  systemStatus: () => request<{ health: Health; counts: Record<string, number>; clock: SimClock }>('/api/system-status'),
  models: () =>
    request<{ active: string; fallback_chain: string[]; models: ModelInfo[]; note: string }>('/api/models'),
  providers: () => request<{ any_real_feed: boolean; providers: ProviderInfo[] }>('/api/providers'),
  hazards: () => request<{ count: number; hazards: Record<string, unknown>[] }>('/api/hazards'),
  logs: (params: { limit?: number; level?: string; component?: string } = {}) =>
    request<{ count: number; logs: Record<string, unknown>[] }>(`/api/logs${qs(params)}`),

  /* ---- auth ------------------------------------------------------------ */
  login: (username: string, password: string) =>
    request<TokenResponse>('/api/auth/login', { method: 'POST', body: { username, password } }),
  me: () => request<User>('/api/auth/me'),
  setHomeLocation: (locationId: string) =>
    request<User>(`/api/auth/me/location${qs({ location_id: locationId })}`, { method: 'PATCH' }),
  users: () => request<{ count: number; users: Record<string, unknown>[] }>('/api/auth/users'),
  demoAccounts: () =>
    request<{
      note: string
      accounts: { username: string; password: string; role: string; description: string; persona_id?: string }[]
    }>(
      '/api/auth/demo-accounts',
    ),

  /* ---- locations & risk ------------------------------------------------ */
  locations: (params: { q?: string; district?: string } = {}) =>
    request<{ count: number; data_origin: string; locations: LocationSummary[] }>(`/api/locations${qs(params)}`),
  location: (id: string) =>
    request<LocationSummary & { infrastructure: Record<string, unknown>[]; infrastructure_note: string }>(
      `/api/locations/${id}`,
    ),
  nearestLocation: (lat: number, lng: number) =>
    request<{ location: LocationSummary; distance_km: number; within_coverage: boolean; note: string | null }>(
      `/api/locations/nearest${qs({ lat, lng })}`,
    ),
  observations: (id: string) =>
    request<{
      location_id: string
      generated_at: string
      connectivity: Connectivity
      observations: Record<string, ObservationMeta>
      data_health: DataHealth
      data_mode: { is_simulated: boolean; label: string }
    }>(`/api/observations/${id}`),
  forecast: (id: string) =>
    request<{
      location_id: string
      issued_at: string
      source: string
      is_simulated: boolean
      mean_agreement: number | null
      forecasts: ForecastEntry[]
    }>(`/api/forecast/${id}`),
  risk: (
    id: string,
    params: { detail?: boolean; persist?: boolean; model?: string; lang?: Lang } = {},
    signal?: AbortSignal,
  ) => request<RiskResponse>(`/api/risk/${id}${qs(params)}`, { signal }),
  timeline: (id: string) => request<Record<string, unknown>>(`/api/risk/${id}/timeline`),
  riskHistory: (id: string, limit = 50) =>
    request<{ count: number; predictions: Record<string, unknown>[] }>(`/api/risk/${id}/history${qs({ limit })}`),
  riskAtPoint: (lat: number, lng: number) => request<Record<string, unknown>>(`/api/risk/point${qs({ lat, lng })}`),

  /* ---- map ------------------------------------------------------------- */
  mapField: (params: { step_deg?: number; min_severity?: number } = {}) =>
    request<RiskField>(`/api/map/field${qs(params)}`),
  mapLayers: () => request<MapLayers>('/api/map/layers'),
  threats: (status: 'active' | 'dissipating' | 'resolved' | 'all' = 'active') =>
    request<{ count: number; threat_cells: ThreatCell[] }>(`/api/threats${qs({ status })}`),
  threat: (id: string) => request<ThreatCell & Record<string, unknown>>(`/api/threats/${id}`),
  earlySignals: (params: { location_id?: string; limit?: number } = {}) =>
    request<{ count: number; signals: EarlySignal[] }>(`/api/early-signals${qs(params)}`),
  dataHealth: () => request<DataHealth & { sampled_locations: number; clock: SimClock }>('/api/data-health'),

  /* ---- alerts ---------------------------------------------------------- */
  alerts: (params: { status?: string; location_id?: string; level?: string; limit?: number; offset?: number } = {}) =>
    request<{ total: number; count: number; offset: number; alerts: Alert[]; note: string }>(`/api/alerts${qs(params)}`),
  alert: (id: string) => request<Alert>(`/api/alerts/${id}`),
  createAlert: (body: Record<string, unknown>) => request<Alert>('/api/alerts', { method: 'POST', body }),
  previewAlert: (body: { location_id: string; hazard?: string; level?: AlertLevel; language?: Lang }) =>
    request<Record<string, unknown>>('/api/alerts/preview', { method: 'POST', body }),
  issueAlert: (id: string, note = '') =>
    request<Alert>(`/api/alerts/${id}/issue${qs({ note })}`, { method: 'POST' }),
  patchAlert: (id: string, body: Record<string, unknown>) =>
    request<Alert>(`/api/alerts/${id}`, { method: 'PATCH', body }),
  acknowledgeAlert: (id: string, note = '') =>
    request<Alert>(`/api/alerts/${id}/acknowledge`, { method: 'POST', body: { note } }),
  deliverAlert: (id: string) =>
    request<{ alert_id: string; deliveries: Record<string, unknown>[]; warning: string }>(
      `/api/alerts/${id}/deliver`,
      { method: 'POST' },
    ),
  alertsForLocation: (id: string) =>
    request<{ count: number; issued: Alert[]; pending_recommendations: Alert[]; note: string }>(
      `/api/alerts/for-location/${id}`,
    ),
  incidents: (params: { status?: string; location_id?: string; limit?: number } = {}) =>
    request<{ count: number; incidents: Record<string, unknown>[] }>(`/api/incidents${qs(params)}`),
  incident: (id: string) => request<Record<string, unknown>>(`/api/incidents/${id}`),
  actions: (hazard: string, level: AlertLevel) =>
    request<{ hazard: string; level: string; actions: string[]; label: string; disclaimer: string }>(
      `/api/actions/${hazard}/${level}`,
    ),

  /* ---- simulation ------------------------------------------------------ */
  scenarios: () => request<{ count: number; current: SimClock; scenarios: Scenario[] }>('/api/scenarios'),
  simState: () =>
    request<SimClock & { sliders: Record<string, number>; active_model: string; sse_subscribers: number }>(
      '/api/simulation/state',
    ),
  runScenario: (id: string, body: { reset_tick?: boolean; auto_advance_to?: number | null } = {}) =>
    request<{ scenario: SimClock; summary: Record<string, unknown> }>(`/api/scenarios/${id}/run`, {
      method: 'POST',
      body: { reset_tick: true, ...body },
    }),
  step: (steps = 1, runAlerts = true) =>
    request<{ clock: SimClock } & Record<string, unknown>>('/api/simulation/step', {
      method: 'POST',
      body: { steps, run_alerts: runAlerts },
    }),
  refresh: () =>
    request<{ clock: SimClock; summary: Record<string, unknown> }>('/api/simulation/refresh', { method: 'POST' }),
  setOverrides: (sliders: Record<string, number>) =>
    request<Record<string, unknown>>('/api/simulation/overrides', { method: 'POST', body: sliders }),
  setConnectivity: (mode: Connectivity) =>
    request<Record<string, unknown>>('/api/simulation/connectivity', { method: 'POST', body: { mode } }),
  setFailure: (component: string, enabled: boolean) =>
    request<Record<string, unknown>>('/api/simulation/failure', { method: 'POST', body: { component, enabled } }),
  setModel: (modelKey: string) =>
    request<{ active: string; models: ModelInfo[]; summary: Record<string, unknown> }>('/api/simulation/model', {
      method: 'POST',
      body: { model_key: modelKey },
    }),
  resetDemo: (scenarioId?: string) =>
    request<Record<string, unknown> & { clock: SimClock }>('/api/simulation/reset', {
      method: 'POST',
      body: { scenario_id: scenarioId ?? null },
    }),
  whatIf: (body: Record<string, unknown>) => request<Record<string, unknown>>('/api/what-if', { method: 'POST', body }),
  replay: (scenarioId: string, locationId?: string) =>
    request<Record<string, unknown>>(`/api/replay/${scenarioId}${qs({ location_id: locationId })}`),
  verify: (scenarioId: string, locationId?: string) =>
    request<Record<string, unknown>>('/api/verify', {
      method: 'POST',
      body: { scenario_id: scenarioId, location_id: locationId ?? null },
    }),
  recentEvents: (limit = 20) =>
    request<{ events: Record<string, unknown>[]; subscribers: number }>(`/api/events/recent${qs({ limit })}`),

  /* ---- live external data --------------------------------------------- */
  liveWeather: (lat: number, lng: number, grid = 1) =>
    request<LiveWeather>(`/api/live/weather${qs({ lat, lng, grid })}`),

  /* ---- analytics ------------------------------------------------------- */
  overview: () => request<Overview>('/api/overview'),
  analytics: () => request<Record<string, unknown>>('/api/analytics'),
  modelPerformance: () => request<Record<string, unknown>>('/api/analytics/model'),
  compare: (sortBy = 'risk') =>
    request<{ count: number; sort_by: string; areas: Record<string, unknown>[] }>(
      `/api/analytics/compare${qs({ sort_by: sortBy })}`,
    ),
  audit: (params: { limit?: number; action?: string; entity_type?: string } = {}) =>
    request<{ count: number; entries: Record<string, unknown>[] }>(`/api/audit${qs(params)}`),

  /* ---- terrain / DEM --------------------------------------------------- */
  terrain: (params: { step_deg?: number; padding_deg?: number } = {}) =>
    request<TerrainGrid>(`/api/terrain${qs(params)}`),
  terrainPoint: (lat: number, lng: number) =>
    request<Record<string, unknown>>(`/api/terrain/point${qs({ lat, lng })}`),

  /* ---- Mumbai topology (Predict map) ------------------------------------ */
  topology: () => request<TopologyResponse>('/api/map/topology'),

  /* ---- storm system ---------------------------------------------------- */
  storm: (params: { lead_ticks?: number } = {}) => request<StormState>(`/api/storm${qs(params)}`),
  stormTrack: () => request<StormTrack>('/api/storm/track'),

  /* ---- rainfall -------------------------------------------------------- */
  rainfall: (locationId = 'loc_kurla') =>
    request<RainfallState>(`/api/rainfall${qs({ location_id: locationId })}`),
  rainfallForecast: (locationId = 'loc_kurla', horizonHours = 6) =>
    request<RainfallForecast>(`/api/rainfall/forecast${qs({ location_id: locationId, horizon_hours: horizonHours })}`),

  /* ---- traffic --------------------------------------------------------- */
  traffic: () => request<TrafficState>('/api/traffic'),

  /* ---- routes ---------------------------------------------------------- */
  planRoute: (fromLat: number, fromLng: number, toLat: number, toLng: number) =>
    request<RoutePlan>(`/api/routes${qs({ from_lat: fromLat, from_lng: fromLng, to_lat: toLat, to_lng: toLng })}`),
  evacuationPlan: (locationId = 'loc_kurla') =>
    request<EvacuationPlan>(`/api/routes/evacuation${qs({ location_id: locationId })}`),

  /* ---- safe navigation (RoutingProvider, Section 29) ------------------- */
  routingProviders: () => request<RoutingProvidersResponse>('/api/routes/providers'),
  planSafeRoute: (body: {
    from_lat: number
    from_lng: number
    to_lat: number
    to_lng: number
    preference?: 'fastest' | 'balanced' | 'safest'
  }) => request<SafeRoutePlan>('/api/routes/plan', { method: 'POST', body }),
  getRoute: (routeId: string) => request<SafeRoute>(`/api/routes/${routeId}`),
  reroute: (routeId: string) =>
    request<ReRouteResult>(`/api/routes/${routeId}/re-route`, { method: 'POST' }),

  /* ---- response assets ------------------------------------------------- */
  shelters: (locationId?: string) =>
    request<ShelterList>(`/api/shelters${qs({ location_id: locationId })}`),
  sheltersNearest: (lat: number, lng: number, limit = 3) =>
    request<{ query: { lat: number; lng: number }; count: number; shelters: (Shelter & { distance_km: number })[]; is_simulated: boolean; clock: SimClock }>(
      `/api/shelters/nearest${qs({ lat, lng, limit })}`,
    ),
  shelter: (id: string) => request<Shelter & Record<string, unknown>>(`/api/shelters/${id}`),
  hospitals: (locationId?: string) =>
    request<HospitalList>(`/api/hospitals${qs({ location_id: locationId })}`),
  hospitalsNearest: (lat: number, lng: number, limit = 3) =>
    request<{ query: { lat: number; lng: number }; count: number; hospitals: (Hospital & { distance_km: number })[]; is_simulated: boolean; clock: SimClock }>(
      `/api/hospitals/nearest${qs({ lat, lng, limit })}`,
    ),
  hospital: (id: string) => request<Hospital & Record<string, unknown>>(`/api/hospitals/${id}`),

  /* ---- grid-cell risk -------------------------------------------------- */
  riskCell: (lat: number, lng: number) => request<RiskCell>(`/api/risk/cell${qs({ lat, lng })}`),

  /* ---- simulation clock controls --------------------------------------- */
  simulationStart: () => request<ClockControlResponse>('/api/simulation/start', { method: 'POST' }),
  simulationPause: () => request<ClockControlResponse>('/api/simulation/pause', { method: 'POST' }),
  simulationSpeed: (speed: number) =>
    request<ClockControlResponse>('/api/simulation/speed', { method: 'POST', body: { speed } }),
  simulationJump: (tick: number, runAlerts = true) =>
    request<ClockControlResponse>(
      '/api/simulation/jump',
      { method: 'POST', body: { tick, run_alerts: runAlerts } },
    ),

  /* ---- citizen mobile app ⇄ authority People screen ---------------------- */
  personas: () => request<PersonasResponse>('/api/citizens/personas'),
  citizenHeartbeat: (body: HeartbeatBody) =>
    request<HeartbeatResponse>('/api/citizens/heartbeat', { method: 'POST', body }),
  citizens: () => request<CitizensResponse>('/api/citizens'),
  citizenHelp: (personaId: string, message = '') =>
    request<{ help: CitizenEntry['help']; is_simulated: boolean; state: string }>(
      `/api/citizens/${personaId}/help`,
      { method: 'POST', body: { message } },
    ),
  ackCitizenHelp: (personaId: string, acknowledged_by = '') =>
    request<{ help: CitizenEntry['help']; is_simulated: boolean }>(
      `/api/citizens/${personaId}/help/ack`,
      { method: 'POST', body: { acknowledged_by } },
    ),
  resolveCitizenHelp: (personaId: string) =>
    request<{ help: CitizenEntry['help']; is_simulated: boolean }>(
      `/api/citizens/${personaId}/help/resolve`,
      { method: 'POST' },
    ),
  resetCitizens: () => request<{ count: number; reset: boolean; note: string }>('/api/citizens/reset', {
    method: 'POST',
  }),
}

export type { PriorityEntry }
