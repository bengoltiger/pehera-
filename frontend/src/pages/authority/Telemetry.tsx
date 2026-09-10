/**
 * Predict — "Real-Time Telemetry Feed" (Atmospheric Ingest & Runoff Model).
 *
 * The atmosphere card shows a REAL map (OSM tiles / local vector fallback)
 * with live wind particles advected through the Open-Meteo u/v field — a
 * god's-eye view of the actual sky over the top-priority zone. The ribbon,
 * rainfall vector and lead-time values mix LIVE external measurements
 * (Open-Meteo) with the engine's runoff model; every simulated value is
 * labelled as such. If the live provider is unreachable the card honestly
 * falls back to the simulated radar and says so.
 *
 * The timeline, confidence and vector metrics are the engine's real values
 * for the current top-priority zone. The scrubber only interpolates between
 * those engine horizons — it never invents a forecast.
 */
import {
  CloudFog,
  Droplets,
  Eye,
  Gauge,
  Hourglass,
  Radar as RadarIcon,
  ShieldCheck,
  Timer,
  TrendingUp,
  Waves,
  Zap,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { useMemo, useState } from 'react'
import { Page, Rise, Stagger } from '../../components/anim'
import { RadarCanvas } from '../../components/RadarCanvas'
import { RiskMap, useTileAvailability } from '../../components/RiskMap'
import { WindParticles } from '../../components/WindParticles'
import { Chip, MetricCard, Panel, SegmentedGauge, StatusPip, Unavailable } from '../../components/ui'
import { api } from '../../lib/api'
import { LEVEL_VAR, fmtNumber, relativeTime, titleCase } from '../../lib/format'
import { useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import { useEngineConfig } from '../../lib/providers'
import type { Alert, TimelineEntry } from '../../lib/types'

const COMPASS_16 = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
/** Meteorological direction (wind blows FROM `deg`). */
const compassFromDeg = (deg: number | null | undefined) =>
  deg == null || !Number.isFinite(deg) ? '—' : COMPASS_16[((Math.round(deg / 22.5) % 16) + 16) % 16]

function lerpTimeline(entries: TimelineEntry[], minutes: number): { risk: number | null; confidence: number | null; low: number | null; high: number | null } {
  const pts = entries.filter((e) => e.available && e.risk != null)
  if (pts.length === 0) return { risk: null, confidence: null, low: null, high: null }
  if (minutes <= pts[0].horizon_minutes) {
    const e = pts[0]
    return { risk: e.risk!, confidence: e.confidence ?? null, low: e.uncertainty?.low ?? null, high: e.uncertainty?.high ?? null }
  }
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i]
    const b = pts[i + 1]
    if (minutes >= a.horizon_minutes && minutes <= b.horizon_minutes) {
      const t = (minutes - a.horizon_minutes) / Math.max(1, b.horizon_minutes - a.horizon_minutes)
      return {
        risk: a.risk! + t * (b.risk! - a.risk!),
        confidence: a.confidence != null && b.confidence != null ? a.confidence + t * (b.confidence - a.confidence) : null,
        low: a.uncertainty?.low != null && b.uncertainty?.low != null ? a.uncertainty.low + t * (b.uncertainty!.low - a.uncertainty!.low) : null,
        high: a.uncertainty?.high != null && b.uncertainty?.high != null ? a.uncertainty.high + t * (b.uncertainty!.high - a.uncertainty!.high) : null,
      }
    }
  }
  const e = pts[pts.length - 1]
  return { risk: e.risk!, confidence: e.confidence ?? null, low: e.uncertainty?.low ?? null, high: e.uncertainty?.high ?? null }
}

function EscalationStage({ alerts }: { alerts: Alert[] }) {
  const active = alerts.filter((a) => a.is_active)
  const idx = active.some((a) => a.level === 'CRITICAL') ? 2 : active.some((a) => a.level === 'WARNING') ? 1 : active.some((a) => a.level === 'WATCH') ? 0 : -1
  const stages = [
    { key: 'STAGE 1', label: 'WATCH', note: 'Trend attention' },
    { key: 'STAGE 2', label: 'WARNING', note: 'Prepare protocols' },
    { key: 'STAGE 3', label: 'CONFIRMED', note: 'Immediate action' },
  ]
  return (
    <div className="grid grid-cols-3 gap-2">
      {stages.map((s, i) => {
        const state = i < idx ? 'cleared' : i === idx ? 'active' : 'pending'
        return (
          <motion.div
            key={s.key}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.07 }}
            className={`rounded-md border p-2 ${
              state === 'active'
                ? 'border-accent/60 bg-ink-700 glow-ai'
                : state === 'cleared'
                  ? 'border-ink-600 bg-ink-850 opacity-70'
                  : 'border-ink-700 bg-ink-850/60 opacity-45'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className={`hud-label ${state === 'active' ? 'text-accent-bright' : 'text-ink-400'}`}>{s.key}</span>
              {state === 'cleared' ? (
                <ShieldCheck size={12} className="text-safe" aria-hidden />
              ) : state === 'active' ? (
                <span className="h-2 w-2 animate-ping rounded-full bg-accent" />
              ) : (
                <Hourglass size={12} className="text-ink-500" aria-hidden />
              )}
            </div>
            <span className={`font-mono text-[11px] font-bold ${state === 'active' ? 'text-accent-bright' : 'text-ink-300'}`}>{s.label}</span>
            <span className="hud-label text-ink-500">{s.note}</span>
          </motion.div>
        )
      })}
    </div>
  )
}

export default function Telemetry() {
  const { t } = useI18n()
  const { config } = useEngineConfig()
  const tileUrl = config?.map?.tile_url ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
  const attribution = config?.map?.attribution ?? '© OpenStreetMap contributors'
  const tileStatus = useTileAvailability(tileUrl)

  const overview = useApi(() => api.overview())
  const threats = useApi(() => api.threats())
  const alerts = useApi(() => api.alerts({ limit: 10 }))
  const models = useApi(() => api.models())
  const sim = useApi(() => api.simState())
  const mapLayers = useApi(() => api.mapLayers(), { liveUpdate: false })

  const top = overview.data?.priority_queue?.[0]
  const risk = useApi((s) => api.risk(top!.location_id, { detail: true, lang: 'en' }, s), {
    enabled: !!top,
    deps: [top?.location_id, overview.data?.generated_at],
  })

  // LIVE external atmosphere over the top zone. Server-side Open-Meteo proxy
  // (10-min cache) → one small request even for a 144-point wind grid.
  const live = useApi(
    (s) => api.liveWeather(risk.data!.location.latitude, risk.data!.location.longitude, 1),
    {
      enabled: !!risk.data?.location && risk.data.location.latitude != null,
      liveUpdate: false,
      deps: [risk.data?.location?.latitude, risk.data?.location?.longitude],
    },
  )
  const livePoint = live.data?.point ?? null

  const [scrub, setScrub] = useState(0)
  const entries = risk.data?.timeline ?? []
  const scrubbed = useMemo(() => lerpTimeline(entries, scrub), [entries, scrub])

  if (overview.loading && !overview.data) {
    return (
      <Page className="p-4">
        <div className="grid h-64 place-items-center">
          <span className="font-mono text-xs text-ink-400">ACQUIRING TELEMETRY FEED…</span>
        </div>
      </Page>
    )
  }

  const r = risk.data
  const cells = threats.data?.threat_cells ?? []
  const topCell = cells.slice().sort((a, b) => b.current_severity - a.current_severity)[0]
  const lead = r?.lead_time
  const rain = r?.inputs?.forecast_rain_3h ?? r?.inputs?.rainfall
  const soil = r?.inputs?.soil_moisture
  const river = r?.inputs?.river_level
  const conf = r?.risk.confidence
  const zone = r?.location
  const liveRain3h = livePoint?.next_3h_rain_mm ?? null

  return (
    <Page className="mx-auto max-w-4xl p-4">
      {/* ------------------------------------------------------ micro-head -- */}
      <div className="mb-3 flex flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 animate-ping rounded-full bg-accent" />
          <span className="hud-label tracking-[0.25em] text-accent-bright">REAL-TIME TELEMETRY FEED</span>
          {live.data ? (
            <Chip tone="good" className="ml-auto">
              LIVE EXTERNAL FEED
            </Chip>
          ) : (
            <Chip tone="sim" className="ml-auto">
              {t('label.simulated')} FEED
            </Chip>
          )}
        </div>
        <h1 className="font-head text-2xl font-bold tracking-tight text-ink-50 uppercase">
          Atmospheric Ingest &amp; Runoff Model
        </h1>
        <p className="font-mono text-[11px] text-ink-400">
          STEP 01 // "Watching the sky, not just the river." · {titleCase(sim.data?.scenario_id ?? 'live')} · T
          {sim.data?.tick}/{sim.data?.total_ticks}
        </p>
      </div>

      {/* ------------------------------------------------- atmosphere card -- */}
      <Rise>
        <div className="relative mb-3 overflow-hidden rounded-lg border border-ink-600 bg-ink-950 shadow-xl">
          <div className="relative h-[26rem]">
            {live.data?.field ? (
              <>
                {/* the real map: streets, wards, rivers, threat cells, tracks.
                    WindParticles is a CHILD of RiskMap so it lives inside the
                    MapContainer and can use the Leaflet context. */}
                <RiskMap
                  layers={mapLayers.data}
                  field={null}
                  queue={overview.data?.priority_queue ?? []}
                  toggles={{ heat: false, zones: true, threats: true, tracks: true, infrastructure: false, rivers: true, alerts: true, labels: true }}
                  tileStatus={tileStatus}
                  tileUrl={tileUrl}
                  attribution={attribution}
                  selectedLocationId={top?.location_id ?? null}
                >
                  {/* live god's-eye wind field advected over the basemap */}
                  <WindParticles field={live.data.field} />
                </RiskMap>
              </>
            ) : live.error ? (
              <div className="grid h-full place-items-center bg-ink-950">
                <div className="w-full">
                  <RadarCanvas cells={cells} />
                </div>
              </div>
            ) : (
              <div className="grid h-full place-items-center">
                <span className="font-mono text-xs text-ink-400">CONNECTING TO LIVE ATMOSPHERIC FEED…</span>
              </div>
            )}

            {/* top status badges (pl-12 keeps the map's zoom control clear) */}
            <div className="absolute top-2 right-2 left-2 z-[500] flex items-center justify-between pointer-events-none pl-12">
              {live.data ? (
                <span className="flex items-center gap-1.5 rounded bg-ink-950/85 px-2 py-1 backdrop-blur-md">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-safe" aria-hidden />
                  <span className="font-mono text-[11px] text-safe">
                    LIVE: OPEN-METEO · {livePoint?.time ? livePoint.time.slice(11, 16) : '--:--'} LOCAL
                  </span>
                </span>
              ) : (
                <span className="flex items-center gap-1.5 rounded bg-ink-950/85 px-2 py-1 backdrop-blur-md">
                  <RadarIcon size={13} className="text-accent-bright" aria-hidden />
                  <span className="font-mono text-[11px] text-ink-100">
                    {live.error ? 'LIVE FEED UNREACHABLE — SIMULATED RADAR' : 'ACQUIRING LIVE FEED…'}
                  </span>
                </span>
              )}
              <span className="flex items-center gap-1.5 rounded bg-critical/25 px-2 py-1 backdrop-blur-md">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-critical" />
                <span className="hud-label text-ink-100">
                  ZONE: {top ? titleCase(top.location_name).toUpperCase() : '—'}
                </span>
              </span>
            </div>

            {/* wind legend (live only) */}
            {live.data?.field && (
              <div className="absolute bottom-2 left-2 z-[500] rounded-md bg-ink-950/85 px-2 py-1.5 backdrop-blur-md pointer-events-none">
                <div className="hud-label mb-1 text-ink-300">
                  LIVE WIND FIELD · {live.data.field.hour ? `${live.data.field.hour.slice(11, 16)} LOCAL` : '—'}
                </div>
                <div
                  className="h-1.5 w-32 rounded-full"
                  style={{ background: 'linear-gradient(90deg, #7dd3fc, #5eead4, #facc15, #f87171)' }}
                  aria-hidden
                />
                <div className="mt-0.5 flex justify-between font-mono text-[8px] text-ink-400">
                  <span>0</span>
                  <span>12</span>
                  <span>25</span>
                  <span>40+ KM/H</span>
                </div>
              </div>
            )}

            {/* floating trajectory chip */}
            {topCell && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="absolute bottom-2 right-2 z-[500] flex max-w-[80%] items-center gap-2 rounded-md bg-ink-800/95 p-2 shadow-md backdrop-blur-md"
              >
                <Zap size={16} className="shrink-0 text-accent-bright" aria-hidden />
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="hud-label text-ink-100">{titleCase(topCell.hazard_label ?? topCell.hazard).toUpperCase()} CELL</span>
                    <span className="font-mono text-[10px] text-accent-bright">
                      {topCell.movement.speed_kmh != null ? `${topCell.movement.speed_kmh.toFixed(1)} km/h ${topCell.movement.compass}` : 'STATIC'}
                    </span>
                  </div>
                  <span className="block truncate font-mono text-[9px] text-ink-400">
                    CONF {topCell.confidence.toFixed(0)}% · STATUS {topCell.status.toUpperCase()}
                  </span>
                </div>
              </motion.div>
            )}
          </div>
          {/* telemetry sub-ribbon: live measurements + engine runoff values */}
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-ink-700/60 bg-ink-850 px-2.5 py-1.5 font-mono text-[10px] text-ink-400">
            {livePoint ? (
              <>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-safe" />
                  TEMP: <strong className="font-medium text-ink-100">{livePoint.temperature_c != null ? `${livePoint.temperature_c.toFixed(1)}°C` : '—'}</strong>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-safe" />
                  WIND: <strong className="font-medium text-ink-100">{livePoint.wind_speed_kmh != null ? `${livePoint.wind_speed_kmh.toFixed(1)} km/h ${compassFromDeg(livePoint.wind_direction_deg)}` : '—'}</strong>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-safe" />
                  RAIN NOW / 3H: <strong className="font-medium text-ink-100">{livePoint.precipitation_mm != null ? `${livePoint.precipitation_mm.toFixed(1)}mm` : '—'} / {livePoint.next_3h_rain_mm != null ? `${livePoint.next_3h_rain_mm.toFixed(1)}mm` : '—'}</strong>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-accent-bright" />
                  RIVER (ENGINE): <strong className="font-medium text-ink-100">{river?.value != null ? `${river.value.toFixed(2)} ${river.unit}` : '—'}</strong>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                  ALGO: <strong className="font-medium text-ink-100">{models.data?.active ?? '—'}</strong>
                </span>
              </>
            ) : (
              <>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-secondary" />
                  RAIN 3H FORECAST:{' '}
                  <strong className="font-medium text-ink-100">
                    {rain?.value != null ? `${rain.value.toFixed(1)} ${rain.unit}` : '—'}
                  </strong>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-accent-bright" />
                  RIVER LEVEL: <strong className="font-medium text-ink-100">{river?.value != null ? `${river.value.toFixed(2)} ${river.unit}` : '—'}</strong>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                  ALGO: <strong className="font-medium text-ink-100">{models.data?.active ?? '—'}</strong>
                </span>
              </>
            )}
          </div>
        </div>
      </Rise>

      {/* ------------------------------------------------- lead-time hero -- */}
      <Rise>
        <div className="relative mb-3 overflow-hidden rounded-lg border border-ink-600 bg-ink-850 p-3">
          <div className="pointer-events-none absolute -right-8 -bottom-8 h-28 w-28 rounded-full bg-accent/10 blur-2xl" />
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent/15 text-accent-bright">
              <Timer size={22} aria-hidden />
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-head text-sm font-bold text-accent-bright">
                  {lead?.available && lead.label ? lead.label : 'LEAD TIME UNAVAILABLE'}
                </span>
                <span className="rounded bg-accent/15 px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wider text-accent-bright uppercase">
                  PEHRA DELTA
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-ink-300">
                {lead?.explanation ??
                  'No warning threshold crossing has been predicted for the current top-priority zone yet.'}
                <span className="mt-0.5 block font-mono text-[10px] text-ink-500">
                  CONVENTIONAL GAUGE-ONLY DETECTION: TYPICALLY +2H AFTER TRENDBEGIN
                </span>
              </p>
            </div>
          </div>
        </div>
      </Rise>

      {/* -------------------------------------------------- time to crest -- */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp size={15} className="text-accent-bright" aria-hidden />
          <h2 className="font-head text-sm font-bold tracking-wide text-ink-100 uppercase">Time-To-Crest Forecast</h2>
        </div>
        <span className="font-mono text-[10px] text-ink-400">HORIZON: +6.0 HRS · {zone ? titleCase(zone.name).toUpperCase() : '—'}</span>
      </div>

      <Stagger className="relative mb-4 flex flex-col gap-2 pl-5">
        <div className="absolute top-2 bottom-2 left-[9px] w-0.5 rounded-full bg-ink-700" aria-hidden />
        {entries.length === 0 && (
          <div className="rounded-md border border-ink-700 bg-ink-850/60 p-3 text-xs text-ink-400">
            <Unavailable label="Timeline unavailable" reason={r?.detail ?? 'load the top-priority zone first'} />
          </div>
        )}
        {entries.map((e) => {
          const isNow = e.horizon_minutes === 0
          const isPeak = r?.peak?.at && e.valid_at === r.peak.at
          const level = e.severity?.key ?? 'LOW'
          const col = level === 'CRITICAL' ? LEVEL_VAR.CRITICAL : level === 'HIGH' ? LEVEL_VAR.HIGH : level === 'MODERATE' ? LEVEL_VAR.MODERATE : level === 'LOW' ? LEVEL_VAR.LOW : 'var(--color-safe)'
          return (
            <Rise key={e.horizon_minutes}>
              <div className="relative flex items-start gap-3">
                <span
                  className={`relative z-10 mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ring-4 ring-ink-950 ${isPeak ? 'animate-pulse' : ''}`}
                  style={{ backgroundColor: col }}
                  aria-hidden
                />
                <div className={`w-full rounded-md border p-2.5 ${isNow ? 'border-ink-600 bg-ink-850' : 'border-ink-700/60 bg-ink-900'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] font-bold" style={{ color: isNow ? 'var(--color-accent-bright)' : 'var(--color-ink-300)' }}>
                      {e.label.toUpperCase()}
                      {isNow ? ` (${relativeTime(r?.generated_at)})` : ''}
                    </span>
                    <span className="flex items-center gap-1.5">
                      {isPeak && (
                        <span className="rounded bg-critical/20 px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wider text-critical uppercase">
                          PROJECTED PEAK
                        </span>
                      )}
                      {e.available && e.risk != null ? (
                        <span className="font-mono text-[11px] font-semibold" style={{ color: col }}>
                          {e.risk.toFixed(0)}/100 {e.severity?.ascii}
                        </span>
                      ) : (
                        <Unavailable reason={e.reason} compact />
                      )}
                    </span>
                  </div>
                  {e.available && e.risk != null && (
                    <div className="mt-1 flex items-center justify-between font-mono text-[10px] text-ink-400">
                      <span>
                        CONF {e.confidence != null ? `${e.confidence.toFixed(0)}%` : '—'} · ±{e.uncertainty?.plus_minus.toFixed(1) ?? '—'}
                      </span>
                      {isNow && river?.value != null && (
                        <span>
                          GAUGE: <span className="text-secondary">{river.value.toFixed(2)} {river.unit}</span>
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </Rise>
          )
        })}
      </Stagger>

      {/* ---------------------------------------------------- vector bento -- */}
      <h2 className="mb-2 font-head text-sm font-bold tracking-wide text-ink-100 uppercase">Atmospheric Vectors</h2>
      <Stagger className="mb-4 grid grid-cols-2 gap-2 xl:grid-cols-4">
        <Rise>
          <MetricCard
            label={liveRain3h != null ? 'Rainfall 3H · LIVE' : 'Rainfall Acc. (3H)'}
            icon={<Droplets size={14} aria-hidden />}
            value={liveRain3h != null ? liveRain3h.toFixed(1) : rain?.value != null ? rain.value.toFixed(0) : '—'}
            unit={liveRain3h != null ? 'mm' : rain?.value != null ? rain.unit : undefined}
            sub={liveRain3h != null ? `Open-Meteo · ${livePoint?.time ? livePoint.time.slice(11, 16) : '--:--'} local` : (rain?.freshness_label ?? 'next 3h forecast window')}
            track={liveRain3h != null ? Math.min(100, (liveRain3h / 60) * 100) : rain?.normalised != null ? rain.normalised * 100 : 0}
          />
        </Rise>
        <Rise>
          <MetricCard
            label="Soil Saturation"
            icon={<Waves size={14} aria-hidden />}
            value={soil?.value != null ? soil.value.toFixed(0) : '—'}
            unit={soil?.value != null ? soil.unit : undefined}
            sub={soil?.value != null && soil.value >= 80 ? 'NEAR POROSITY MAX · ENGINE' : `${soil?.freshness_label ?? '—'} · ENGINE`}
            subTone={soil?.value != null && soil.value >= 80 ? 'var(--color-accent-bright)' : undefined}
            track={soil?.normalised != null ? soil.normalised * 100 : 0}
            trackTone="var(--color-secondary)"
          />
        </Rise>
        <Rise>
          <MetricCard
            label="River Stage"
            icon={<CloudFog size={14} aria-hidden />}
            value={river?.value != null ? river.value.toFixed(2) : '—'}
            unit={river?.value != null ? river.unit : undefined}
            sub={river ? `${river.freshness_label ?? ''} · quality ${(river.quality * 100).toFixed(0)}% · ENGINE` : 'no gauge in zone'}
            track={river?.normalised != null ? river.normalised * 100 : 0}
            trackTone="var(--color-critical)"
          />
        </Rise>
        <Rise>
          <div className="panel-tight flex flex-col justify-between p-3">
            <div className="mb-1 flex items-center justify-between text-ink-400">
              <span className="hud-label">Model Certainty</span>
              <Gauge size={14} aria-hidden />
            </div>
            <div className="my-1">
              <div className="font-head text-base font-bold text-accent-bright">
                {conf ? `${conf.value.toFixed(1)}%` : '—'}
              </div>
              <span className="font-mono text-[10px] text-ink-400">{conf?.label ?? 'no assessment'}</span>
            </div>
            {conf ? (
              <SegmentedGauge value={conf.value} />
            ) : (
              <Unavailable compact />
            )}
          </div>
        </Rise>
      </Stagger>

      {/* ---------------------------------------------------- escalation -- */}
      <Panel title="Escalation Protocol" subtitle="Stage derived from the live alert state of the monitored network">
        <EscalationStage alerts={alerts.data?.alerts ?? []} />
      </Panel>

      {/* ------------------------------------------------------ scrubber -- */}
      <div className="mt-3 rounded-lg border border-ink-600 bg-ink-850 p-3 shadow-lg">
        <div className="flex items-center justify-between">
          <span className="font-head text-sm font-semibold text-ink-100">Prediction Horizon Scrubber</span>
          <span className="font-mono text-xs text-accent-bright">T +{(scrub / 60).toFixed(1)} HRS</span>
        </div>
        <input
          type="range"
          min={0}
          max={360}
          step={10}
          value={scrub}
          onChange={(e) => setScrub(Number(e.target.value))}
          className="mt-2 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-ink-700 accent-[var(--color-accent)]"
          aria-label="Prediction horizon in minutes"
        />
        <div className="mt-1 flex items-center justify-between font-mono text-[9px] text-ink-500">
          <span>NOW (INGEST)</span>
          <span>+1H</span>
          <span>+2H</span>
          <span>+3H (PEAK ZONE)</span>
          <span>+6H</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-ink-700 bg-ink-900 px-2.5 py-1.5 font-mono text-[11px]">
          <span className="text-ink-400">
            ENGINE PREDICTION @ T+{scrub / 60 >= 1 ? `${(scrub / 60).toFixed(1)}H` : `${scrub}M`}:
          </span>
          {scrubbed.risk != null ? (
            <>
              <span className="font-semibold text-ink-100">RISK {scrubbed.risk.toFixed(0)}/100</span>
              {scrubbed.low != null && scrubbed.high != null && (
                <span className="text-ink-400">
                  BAND {scrubbed.low.toFixed(0)}–{scrubbed.high.toFixed(0)}
                </span>
              )}
              {scrubbed.confidence != null && <span className="text-accent-bright">CONF {scrubbed.confidence.toFixed(0)}%</span>}
            </>
          ) : (
            <Unavailable compact label="no horizon data" />
          )}
        </div>
        <p className="mt-1.5 font-mono text-[9px] leading-snug text-ink-500 uppercase">
          Interpolated between engine horizons — display only, never a new forecast.
        </p>
      </div>

      {/* ------------------------------------------------ hyperlocal note -- */}
      <div className="mt-3 flex items-start gap-3 rounded-lg border border-ink-700 bg-ink-900/60 p-3">
        <Eye size={18} className="mt-0.5 shrink-0 text-accent-bright" aria-hidden />
        <div className="min-w-0">
          <span className="font-head text-sm font-semibold text-ink-100">Hyperlocal 1–3 km Precision</span>
          <p className="mt-0.5 text-xs leading-relaxed text-ink-400">
            Warnings target specific wards rather than blanket district alarms — preserving community trust and
            eliminating evacuation fatigue.
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px]">
            <span className="text-accent-bright">{zone ? zone.id.toUpperCase() : '—'}</span>
            {zone && <span className="text-ink-400">· {fmtNumber(zone.population)} RESIDENTS</span>}
            {zone && <span className="text-ink-400">· {zone.area_km2.toFixed(1)} KM²</span>}
            <StatusPip tone="info" label={zone?.data_origin ?? 'simulated'} className="ml-auto" />
          </div>
        </div>
      </div>
    </Page>
  )
}
