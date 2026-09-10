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
