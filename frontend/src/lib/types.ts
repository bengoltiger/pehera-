/**
 * Shared API types.
 *
 * These mirror what the backend actually returns. Engine payloads are rich and
 * nested by design (the API documents them rather than flattening them), so a
 * handful of index signatures are used deliberately where the shape is
 * genuinely open-ended.
 */

export type Role = 'citizen' | 'authority' | 'administrator'
export type SeverityKey = 'SAFE' | 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL'
export type AlertLevel = 'WATCH' | 'WARNING' | 'CRITICAL'
export type Connectivity = 'online' | 'degraded' | 'offline'
export type Lang = 'en' | 'hi'

export interface User {
  id: string
  username: string
  full_name: string
  role: Role
  organisation?: string | null
  home_location_id?: string | null
  language: Lang
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_at: string
  user: User
}

export interface Severity {
  key: SeverityKey
  label: string
  icon: string
  ascii: string
  color: string
  pattern: string
  explanation: string
  action: string
  range: [number, number]
}

export interface Momentum {
  rate_per_hour: number
  delta: number
  minutes: number
  band: string
  label: string
  arrow: string
  previous_risk: number | null
  current_risk: number
  note: string
}

export interface ConfidenceBreakdown {
  value: number
  /** Band key from the backend (very_low … very_high). */
  band: string
  label: string
  band_note: string
  /** Component name -> 0..100 sub-score. */
  components: Record<string, number>
  /** Component name -> weight in the blend. */
  weights: Record<string, number>
  penalties: { kind: string; points: number; detail: string }[]
  reasons: string[]
  is_reduced: boolean
}

export interface Uncertainty {
  plus_minus: number
  low: number
  high: number
  note: string
}

export interface Peak {
  available: boolean
  risk: number | null
  in_minutes: number | null
  at: string | null
  label: string
  reason_unavailable: string | null
  at_peak_now?: boolean
}

export interface DecisionWindow {
  available: boolean
  minutes: number | null
  threshold: number
  already_critical: boolean
  label: string
  reason_unavailable: string | null
}

export interface TimelineEntry {
  horizon_minutes: number
  label: string
  available: boolean
  reason?: string
  risk?: number
  hazard_score?: number
  exposure_score?: number
  severity?: Severity
  confidence?: number
  uncertainty?: Uncertainty
  main_hazard?: string
  main_hazard_key?: string | null
  expected_intensity?: string | null
  valid_at?: string
}

export interface Contributor {
  feature: string
  label: string
  points: number
  percent: number
  raw_value: number | null
  unit: string
  normalised: number | null
  component: string
  direction: string
  share?: number
  bar?: string
  text?: string
}

export interface LocationSummary {
  id: string
  name: string
  name_hi?: string
  admin_type: string
  district: string
  state: string
  latitude: number
  longitude: number
  elevation_m: number
  area_km2: number
  population: number
  vulnerable_population: number
  households?: number
  terrain_vulnerability: number
  drainage_deficiency: number
  river_id: string | null
  polygon: number[][] | null
  primary_hazards: string[]
  data_origin: string
}

export interface RiskResponse {
  available: boolean
  detail?: string
  location: LocationSummary
  generated_at: string
  scenario: Record<string, unknown>
  risk: {
    overall: number
    hazard_score: number
    exposure_score: number
    severity: Severity
    confidence: ConfidenceBreakdown
    uncertainty: Uncertainty
    momentum: Momentum
  }
  hazard: {
    dominant: string
    label: string
    icon?: string
    results?: HazardResult[]
    compound?: CompoundRisk
  }
  exposure: {
    score: number
    population: number
    vulnerable_population: number
    critical_facilities: number
    breakdown: Record<string, number>
    estimate_note: string
  }
  model: { name: string; version: string; kind: string; is_fallback: boolean; notes?: string[]; attempts?: unknown[] }
  data_health: DataHealth
  inputs: Record<string, ObservationMeta>
  data_mode: { is_simulated: boolean; label: string }
  connectivity: Connectivity
  // detail = true
  explanation?: {
    rank: number
    feature: string
    label: string
    text: string
    percent: number
    points: number
    component: string
    source: string
    freshness: string
    age_human: string
  }[]
  contributors?: Contributor[]
  early_signals?: EarlySignal[]
  peak?: Peak
  decision_window?: DecisionWindow
  lead_time?: { available: boolean; seconds: number | null; label: string | null; explanation: string }
  trajectory?: { offset_minutes: number; risk: number | null }[]
  timeline?: TimelineEntry[]
  comparison?: { one_hour_ago: number | null; now: number; predicted_peak: number | null; peak_in_minutes: number | null; note: string }
  narrative?: Record<string, string | Record<string, string>>
  forecasts?: ForecastEntry[]
  prediction_id?: string
}

export interface ObservationMeta {
  feature: string
  label: string
  value: number | null
  unit: string
  source: string
  source_kind?: string
  observed_at: string | null
  age_seconds: number | null
  age_human: string
  freshness: string
  quality: number
  observed_or_predicted: string
  normalised: number | null
  freshness_label?: string
  unavailable_reason: string | null
  validation_error?: string | null
  is_simulated: boolean
}

export interface ForecastEntry {
  feature: string
  label?: string
  value: number | null
  unit: string
  source: string
  horizon_minutes: number
  issued_at: string
  valid_at: string
  model_agreement: number | null
  is_simulated: boolean
}

export interface DataHealth {
  score: number
  grade: string
  by_source: {
    source: string
    key: string
    kind: string
    score: number
    grade: string
    status: string
    reason?: string | null
    is_simulated: boolean
    features: number
    age_human: string
  }[]
  stale_features: string[]
  missing_features: string[]
  failed_providers: { provider: string; reason: string; features?: string[] }[]
  notes: string[]
}

export interface HazardResult {
  hazard: string
  label: string
  icon?: string
  severity_index: number
  components: Record<string, number>
  contributions: Contributor[]
  missing_features?: string[]
}

export interface CompoundRisk {
  is_compound: boolean
  dominant_hazard: string
  contributing_hazards: string[]
  base_severity: number
  compound_severity: number
  bonus: number
  interactions: { hazard: string; label: string; severity: number; bonus: number; note?: string }[]
  explanation: string
}

export interface EarlySignal {
  id?: string
  location_id?: string
  kind: string
  label: string
  detail: string
  magnitude: number | null
  risk_at_detection?: number
  detected_at?: string
  tick?: number
}

export interface PriorityEntry {
  location_id: string
  location_name: string
  location_name_hi?: string
  district: string
  latitude: number
  longitude: number
  hazard: string
  hazard_label: string
  risk: number
  severity: Severity
  hazard_score: number
  exposure_score: number
  exposed_population: number
  momentum: Momentum
  confidence: number
  priority: number
  priority_factors: { risk: number; exposure: number; urgency: number; confidence: number }
  peak: Peak
  decision_window: DecisionWindow
  rank: number
  why_priority: string
}

export interface ThreatCell {
  id: string
  hazard: string
  hazard_label?: string
  center: { lat: number; lng: number }
  radius_km: number
  polygon: number[][] | null
  current_severity: number
  predicted_severity: number | null
  /** Severity band key, e.g. "CRITICAL". */
  severity_label: string
  movement: {
    bearing_deg: number | null
    speed_kmh: number | null
    compass: string | null
    is_moving: boolean
    note?: string
  }
  confidence: number
  status: string
  location_ids: string[]
  track: { lat: number; lng: number; at: string; tick: number; severity?: number }[]
  predicted_track: { lat: number; lng: number; in_minutes?: number; severity?: number }[]
  first_detected_at: string
  last_updated_at: string
  age_minutes?: number
  tick?: number
}

export interface AlertTransition {
  from_status: string | null
  to_status: string
  from_level: string | null
  to_level: string | null
  actor: string
  actor_role: string
  reason: string
  at: string
}

export interface Alert {
  id: string
  location: LocationRef
  incident_id?: string | null
  hazard: string
  hazard_label: string
  hazard_icon?: string
  level: AlertLevel
  status: string
  title: string
  message: string
  message_hi?: string
  recommended_actions: string[]
  recommendation_label?: string
  what: string
  where: string
  when: string
  why: string
  what_to_do: string
  risk_score: number
  confidence: number
  prediction_id?: string | null
  threat_cell_id?: string | null
  geofence: {
    kind?: string
    lat?: number
    lng?: number
    radius_km?: number
    points?: number[][] | null
    covered_location_ids?: string[]
  }
  estimated_exposed_population: number
  exposure_note?: string
  target_audience: string[]
  trigger_reason: string
  trigger_kinds: string[]
  is_ai_generated: boolean
  is_active: boolean
  approved_by?: string | null
  approved_at?: string | null
  issued_at?: string | null
  expires_at?: string | null
  resolved_at?: string | null
  update_count: number
  lead_time_seconds?: number | null
  created_at: string
  timeline?: AlertTransition[]
  deliveries?: Delivery[]
  acknowledgements?: { user_id: string | null; role: string; note: string; at: string }[]
  funnel?: {
    issued: number
    delivered: number
    opened: number
    acknowledged: number
    note: string
  }
}

export interface LocationRef {
  id: string
  name: string
  name_hi?: string
  district?: string
  latitude: number
  longitude: number
}

export interface Delivery {
  id?: string
  channel: string
  channel_label?: string
  status: string
  recipient_count: number
  opened_count: number
  provider: string
  is_simulated: boolean
  detail: string
  sent_at?: string
}

export interface Overview {
  generated_at: string
  clock: SimClock
  metrics: {
    active_threats: number
    critical_zones: number
    high_zones: number
    people_potentially_exposed: number
    alerts_issued: number
    alerts_awaiting_approval: number
    average_lead_time_seconds: number | null
    average_lead_time_note: string | null
    data_health: number
    data_health_grade: string
    monitored_locations: number
  }
  priority_queue: PriorityEntry[]
  threat_cells: ThreatCell[]
  risk_field_points: number
  changes: { what: string; severity: string; message: string }[]
  data_mode: { is_simulated: boolean; label: string }
}

export interface SimClock {
  scenario_id: string
  scenario_name?: string
  tick: number
  total_ticks: number
  tick_minutes: number
  elapsed_minutes?: number
  elapsed_label?: string
  simulated_time?: string
  connectivity: Connectivity
  forced_failures: Record<string, boolean>
  overrides: Record<string, number>
  running?: boolean
  speed?: number
  at_end?: boolean
  expected_peak_tick?: number | null
  narrative?: string
  progress?: number
  is_simulated?: boolean
  note?: string
}

export interface ProviderInfo {
  key: string
  name: string
  kind: string
  status: string
  is_simulated: boolean
  features: string[]
  latency_seconds: number | null
  note: string
  reason?: string | null
}

export interface Scenario {
  id: string
  name: string
  description: string
  hazard_focus: string[]
  focus_location_id: string
  tick_minutes: number
  total_ticks: number
  duration_minutes: number
  narrative: string
  expected_peak_tick: number | null
  is_deterministic: boolean
  has_outages: boolean
  outages: Record<string, unknown>[]
}

export interface HealthComponent {
  name: string
  key: string
  status: string
  detail?: string | null
  is_simulated?: boolean
  is_active?: boolean
  latency_ms?: number
}

export interface Health {
  status: string
  app: string
  full_name: string
  version: string
  environment: string
  uptime_seconds: number
  server_time_utc: string
  python: string
  demo_mode: boolean
  data_mode: { is_simulated: boolean; label: string; note: string }
  connectivity: Connectivity
  components: HealthComponent[]
  degraded_components: string[]
  security_warnings: string[]
}

export interface ModelInfo {
  name: string
  version: string
  kind: string
  description: string
  trained_on: string | null
  available: boolean
  unavailable_reason: string | null
  training_metrics?: { train?: Metrics; holdout?: Metrics } | null
  training_samples?: number | null
  feature_importance?: { feature: string; importance?: number; weight?: number }[] | null
  metrics_caveat?: string
}

export interface Metrics {
  r2: number
  mae: number
  rmse: number
  bias: number
  p95_abs_error: number
  n: number
}

/* ---- live external weather (Predict screen) ---------------------------- */

export interface LiveWeatherHour {
  time: string
  precip_mm: number | null
  wind_kmh: number | null
  wind_dir_deg: number | null
}

export interface LiveWeatherPoint {
  time: string | null
  temperature_c: number | null
  humidity_pct: number | null
  wind_speed_kmh: number | null
  wind_direction_deg: number | null
  precipitation_mm: number | null
  cloud_cover_pct: number | null
  next_3h_rain_mm: number | null
  next_12h: LiveWeatherHour[]
}

export interface LiveWindField {
  origin_lat: number
  origin_lng: number
  step_deg: number
  rows: number
  cols: number
  /** row-major flat arrays, km/h (u = eastward, v = northward) */
  u: number[]
  v: number[]
  hour: string | null
}

export interface LiveWeather {
  provider: string
  provider_url: string
  fetched_at: string
  ttl_seconds: number
  point: LiveWeatherPoint
  field: LiveWindField | null
  note: string
}

export interface InfrastructureItem {
  id: string
  name: string
  kind: string
  lat: number
  lng: number
  criticality: string
  capacity: number | null
  location_id: string
  /** Siting + contact details (shelters & hospitals); demo dataset. */
  address?: string | null
  phone?: string | null
}

export interface MapLayers {
  zones: (LocationSummary & { polygon: number[][] | null })[]
  infrastructure: InfrastructureItem[]
  rivers: { id: string; points: { location_id: string; lat: number; lng: number; name: string }[] }[]
  threat_cells: ThreatCell[]
  alerts: {
    id: string
    level: AlertLevel
    status: string
    hazard: string
    location_id: string
    geofence: Record<string, unknown>
    title: string
    risk_score: number
  }[]
  data_origin: string
  base_maps: {
    key: string
    name: string
    provider: string
    mode: 'NEAR_REAL_TIME' | 'HISTORICAL' | 'SIMULATED'
    label: string
    is_live: boolean
    resolution_m: number | null
    freshness_s: number | null
    acquisition: string
  }[]
}

export interface RiskField {
  points: { lat: number; lng: number; severity: number; hazard: string }[]
  bbox: { min_lat: number; max_lat: number; min_lng: number; max_lng: number }
  step_deg: number
  count: number
  min_severity: number
  note: string
}

export interface EngineConfig {
  risk_levels: (Omit<Severity, 'pattern' | 'range'> & {
    min: number
    max: number
    colorblind_pattern: string
  })[]
  momentum_bands: { key: string; label: string; arrow: string; min: number; max: number }[]
  composite_weights: Record<string, number>
  overall_mix: Record<string, number>
  exposure_weights: Record<string, number>
  normalisation: Record<string, { min: number; max: number; unit: string; curve: string }>
  hazards: Record<string, Record<string, unknown>>
  alerts: Record<string, unknown>
  confidence: Record<string, unknown>
  freshness: Record<string, unknown>
  data_quality_grades: { min: number; label: string }[]
  threat_cells: Record<string, unknown>
  verification: Record<string, number>
  horizons_minutes: number[]
  nowcast_error_model: {
    why: string
    error_modes: { name: string; detail: string }[]
    table: { horizon_minutes: number; persistence_weight: number; noise_amplitude: number }[]
    not_applied_to: string
  }
  map: { tile_url: string; attribution: string }
}

/* ---- Mumbai environment & response layers (Phase G) --------------------- */

export interface TerrainPoint {
  lat: number
  lng: number
  elevation_m: number
  slope_deg: number
  coastal_exposure: number
  drainage_deficiency: number
  flood_susceptibility: number
}

export interface TerrainGrid {
  points: TerrainPoint[]
  bbox: { min_lat: number; max_lat: number; min_lng: number; max_lng: number } | null
  step_deg: number
  count: number
  note: string
}

export interface StormPoint {
  tick: number
  lat: number
  lng: number
  wind_speed: number
  wind_gust: number
  surge_m: number
  rain_intensity: number
}

export interface StormSystem {
  name: string
  type: string
  active: boolean
  latitude: number
  longitude: number
  bearing_deg: number | null
  speed_kmh: number | null
  radius_km: number
}

export interface StormState {
  system: StormSystem
  intensity: {
    wind_speed_kmh: number
    gust_kmh: number
    surge_m: number
    tide_level_m: number
    rain_intensity_mmh: number
    central_pressure_hpa: number | null
    trend_3h: string
  }
  track: StormPoint[]
  clock: SimClock
  is_simulated: boolean
  note: string
}

export interface StormTrack {
  scenario_id: string
  points: { tick: number; lat: number; lng: number; surge_m: number; wind_speed: number }[]
  count: number
  is_simulated: boolean
}

export interface RainfallBucket {
  hours: number
  accumulated_mm: number
}

export interface RainfallState {
  location_id: string
  generated_at: string
  now: {
    rain_intensity_mmh: number
    rain_accumulation_3h_mm: number
    forecast_rain_3h_mm: number
  }
  buckets: RainfallBucket[]
  data_mode: { is_simulated: boolean; label: string }
  clock: SimClock
}

export interface RainfallForecastBucket {
  hours: number
  forecast_mm: number
  confidence: number
}

export interface RainfallForecast {
  location_id: string
  issued_at: string
  source: string
  horizon_hours: number
  buckets: RainfallForecastBucket[]
  data_mode: { is_simulated: boolean; label: string }
  clock: SimClock
}

export interface TrafficCorridor {
  id: string
  name: string
  from: { lat: number; lng: number }
  to: { lat: number; lng: number }
  ward_anchor: string
  congestion: number
  status: string
  speed_kmh: number
  bound_ward_risk: number | null
}

export interface TrafficState {
  count: number
  corridors: TrafficCorridor[]
  blocked: TrafficCorridor[]
  summary: Record<string, number>
  data_mode: { is_simulated: boolean; label: string }
  clock: SimClock
}

export interface RoutePoint {
  lat: number
  lng: number
}

export interface RoutePlan {
  from: RoutePoint
  to: RoutePoint
  scenario_id: string
  tick: number
  best: string
  route: {
    label: string
    polyline: RoutePoint[]
    max_severity: number
    worst_hazard: string | null
    worst_point: RoutePoint | null
    blocked: boolean
    slow: boolean
    distance_km: number
    eta_minutes: number
  }
  alternatives: { label: string; max_severity: number; distance_km: number; blocked: boolean }[]
  note: string
  is_simulated: boolean
  clock: SimClock
}

export interface EvacuationRoute {
  shelter_id: string
  shelter_name: string
  address: string | null
  phone: string | null
  capacity: number | null
  distance_km: number
  eta_minutes: number
  peak_severity: number
  blocked: boolean
  polyline: RoutePoint[]
}

export interface EvacuationPlan {
  from: { location_id: string; name: string }
  routes: EvacuationRoute[]
  is_simulated: boolean
  clock: SimClock
}

export type RoutePreference = 'fastest' | 'balanced' | 'safest'

export interface RoutingProviderInfo {
  key: string
  name: string
  version: string
  is_simulated: boolean
  note: string
  weights?: Record<RoutePreference, Record<string, number>>
}

export interface RouteHazardFactor {
  hazard: string
  severity: number
  label: string
}

export interface RouteInstruction {
  index: number
  text: string
  distance_m: number
  road: string
}

export interface RouteGeometry {
  type: 'LineString'
  coordinates: [number, number][]
}

export interface SafeRoute {
  route_id: string
  provider: {
    key: string
    name: string
    kind: string
    mode: string
  }
  from: RoutePoint
  to: RoutePoint
  preference: RoutePreference
  distance_m: number
  duration_s: number
  risk_score: number
  risk_level: SeverityKey
  risk_reason: string
  confidence: number
  hazard_factors: RouteHazardFactor[]
  instructions: RouteInstruction[]
  geometry: RouteGeometry | null
  last_evaluated_at: string
  cost_weights: Record<string, number>
  data_mode: { is_simulated: boolean; label: string }
  clock: SimClock
}

export interface SafeRoutePlan extends SafeRoute {
  alternatives: SafeRoute[]
}

export interface ReRouteResult {
  route_id: string
  changed: boolean
  previous_level: SeverityKey
  risk_level: SeverityKey
  risk_reason: string
  recommendation: 're-route' | 'continue'
}

export interface RoutingProvidersResponse {
  providers: RoutingProviderInfo[]
  default: string
  is_simulated: boolean
  note: string
}

export interface Shelter {
  id: string
  name: string
  kind: string
  latitude: number
  longitude: number
  capacity: number | null
  criticality: string
  address: string | null
  phone: string | null
  location_id: string
  host_ward_risk: number | null
  readiness: 'ready' | 'at_risk' | 'impacted'
  data_origin: string
}

export interface ShelterList {
  count: number
  total_capacity: number
  shelters: Shelter[]
  data_mode: { is_simulated: boolean; label: string }
  clock: SimClock
}

export interface Hospital {
  id: string
  name: string
  kind: string
  latitude: number
  longitude: number
  beds: number | null
  criticality: string
  address: string | null
  phone: string | null
  location_id: string
  host_ward_risk: number | null
  status: 'operational' | 'diverting' | 'stretched'
  data_origin: string
}

export interface HospitalList {
  count: number
  total_beds: number
  hospitals: Hospital[]
  data_mode: { is_simulated: boolean; label: string }
  clock: SimClock
}

export interface RiskCellHazard {
  hazard: string
  label: string
  severity: number
}

export interface RiskCell {
  lat: number
  lng: number
  severity: number
  severity_band: Severity
  dominant_hazard: string
  hazard_breakdown: RiskCellHazard[]
  nearest_location: { id: string; name: string; distance_km: number | null } | null
  interpolated: boolean
  threat_cells: {
    id: string
    hazard: string
    severity: number
    severity_label: string
    center_lat: number
    center_lng: number
    radius_km: number
    status: string
  }[]
  note: string
}

export interface ClockControlResponse {
  running?: boolean
  speed?: number
  clock: SimClock
}

export interface ApiError {
  error: string
  message: string
  status_code?: number
  path?: string
  problems?: { field: string; message: string; type: string }[]
  detail?: unknown
  required_roles?: string[]
  your_role?: string
}

/* ------------------------------------------------------------------------- */
/* Citizen mobile app ⇄ authority People screen (CD-08, CD-12)               */
/* ------------------------------------------------------------------------- */

export type CitizenConnectivity = 'online' | 'offline' | 'relay'
export type CitizenState = 'online' | 'relay' | 'stale' | 'offline' | 'unseen' | 'helped'

export interface CitizenFix {
  lat: number
  lng: number
  accuracy: number
}

export type CitizenHelp = {
  status: 'requested' | 'acknowledged' | 'resolved'
  requested_at: string
  message: string
  fix: CitizenFix
  is_baseline: boolean
  ack_by: string | null
  ack_at: string | null
  resolved_by: string | null
  resolved_at: string | null
} | null

export interface CitizenPersona {
  id: string
  codename: string
  full_name: string
  ward_id: string
  ward_label: string
  phone: string
  kind: string
  baseline_fix: CitizenFix
  demo_label: string
  last_seen_at: string | null
}

export interface CitizenEntry {
  id: string
  codename: string
  full_name: string
  ward_id: string
  ward_label: string
  phone: string
  kind: string
  state: CitizenState
  state_label: string
  color: string
  help: CitizenHelp
  fix: CitizenFix
  is_baseline: boolean
  last_fix_at: string | null
  last_seen_at: string | null
  age_s: number | null
  announced: CitizenConnectivity
  via_relay: string | null
  relayed_at: string | null
  ble_enabled: boolean
  bt_mode: 'native' | 'web' | 'simulated' | 'off'
  battery: number | null
  heading_deg: number | null
  speed_kmh: number | null
  note: string | null
  history: { at: string; lat: number; lng: number; state: string }[] | null
}

export interface CitizensResponse {
  count: number
  citizens: CitizenEntry[]
  is_simulated: boolean
  note: string
}

export interface PersonasResponse {
  count: number
  personas: CitizenPersona[]
  is_simulated: boolean
  note: string
}

export interface HeartbeatBody {
  persona_id?: string
  codename?: string
  fix?: CitizenFix
  announced?: CitizenConnectivity
  via_relay?: string
  ble_enabled?: boolean
  bt_mode?: CitizenEntry['bt_mode']
  battery?: number | null
  heading_deg?: number | null
  speed_kmh?: number | null
  note?: string
}

export interface HeartbeatResponse {
  persona: CitizenEntry
  is_simulated: boolean
  published_events: number
}
