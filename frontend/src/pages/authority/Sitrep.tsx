/**
 * SITREP — the "Command & Map" screen from the tactical design.
 * Everything plotted is live engine data: the map is the real hyperlocal
 * layer, the vectors are the current priority queue and metrics, and the
 * incident feed is the actual alert lifecycle.
 */
import {
  Activity,
  BedDouble,
  Building2,
  ChevronRight,
  Compass,
  Crosshair,
  Radio,
  Route,
  Siren,
  Timer,
  Users,
  Waves,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { HeroMapWithSelection } from '../../components/HeroMap'
import { Page, Rise, Stagger } from '../../components/anim'
import { MetricCard, Panel, SeverityBadge, StatusPip } from '../../components/ui'
import { api } from '../../lib/api'
import { fmtNumber, relativeTime, titleCase } from '../../lib/format'
import { useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import type { Alert, AlertLevel } from '../../lib/types'

function stageFromAlerts(alerts: Alert[]): { label: string; tone: 'good' | 'warn' | 'danger' | 'info' } {
  const active = alerts.filter((a) => a.is_active)
  const levels = active.map((a) => a.level)
  if (levels.includes('CRITICAL')) return { label: 'STAGE 3: CONFIRMED', tone: 'danger' }
  if (levels.includes('WARNING')) return { label: 'STAGE 2: WARNING', tone: 'warn' }
  if (levels.includes('WATCH')) return { label: 'STAGE 1: WATCH', tone: 'info' }
  return { label: 'STAGE 0: MONITOR', tone: 'good' }
}

export default function Sitrep() {
  const { t } = useI18n()
  const navigate = useNavigate()

  const overview = useApi(() => api.overview())
  const alerts = useApi(() => api.alerts({ limit: 6 }))
  const threats = useApi(() => api.threats())
  const layers = useApi(() => api.mapLayers())
  const sim = useApi(() => api.simState())

  const queue = overview.data?.priority_queue ?? []
  const top = queue[0]
  const topZone = top ? { id: top.location_id, name: top.location_name, lat: top.latitude, lng: top.longitude } : null

  const riskTop = useApi((s) => api.risk(top!.location_id, { detail: true, lang: 'en' }, s), {
    enabled: !!top,
    deps: [top?.location_id, overview.data?.generated_at],
  })

  const stage = stageFromAlerts(alerts.data?.alerts ?? [])

  const shelters = useMemo(
    () => (layers.data?.infrastructure ?? []).filter((i) => i.kind === 'shelter'),
    [layers.data],
  )
  const bedCapacity = shelters.reduce((sum, s) => sum + (s.capacity ?? 0), 0)

  const topCell = useMemo(
    () => (threats.data?.threat_cells ?? []).slice().sort((a, b) => b.current_severity - a.current_severity)[0],
    [threats.data],
  )

  const river = riskTop.data?.inputs?.river_level

  if (overview.loading && !overview.data) {
    return (
      <Page className="p-4">
        <div className="grid h-64 place-items-center">
          <span className="font-mono text-xs text-ink-400">ACQUIRING SITUATIONAL PICTURE…</span>
        </div>
      </Page>
    )
  }

  const m = overview.data?.metrics

  return (
    <Page className="p-4">
      {/* ------------------------------------------------- SITREP sub-bar -- */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-ink-600 bg-ink-850 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <StatusPip tone="info" label="" ping />
          <span className="truncate font-mono text-xs font-semibold tracking-[0.1em] text-accent-bright uppercase">
            SITREP // {titleCase(overview.data?.clock.scenario_id ?? 'live')}
          </span>
          {sim.data && (
            <span className="hidden font-mono text-[10px] text-ink-400 uppercase sm:inline">
              T{sim.data.tick}/{sim.data.total_ticks} · {sim.data.elapsed_label}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 rounded bg-ink-700 px-2 py-0.5">
          <span className="hud-label text-ink-400">AI ENGINE:</span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            <span className="hud-label text-accent-bright">{sim.data?.active_model ?? '—'}</span>
          </span>
        </div>
      </div>

      {/* ------------------------------------------------------ hero map -- */}
      <HeroMapWithSelection className="mb-3 h-[26rem] rounded-md">
        {/* top-left status HUD */}
        <div className="pointer-events-none absolute top-3 left-3 z-[500] flex flex-col gap-1">
          <span
            className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 backdrop-blur-md ${
              stage.tone === 'danger'
                ? 'border-critical bg-critical/20 text-critical glow-critical'
                : stage.tone === 'warn'
                  ? 'border-moderate bg-moderate/15 text-moderate'
                  : stage.tone === 'info'
                    ? 'border-accent bg-accent/10 text-accent-bright'
                    : 'border-safe bg-safe/10 text-safe'
            }`}
          >
            <span className="relative flex h-2 w-2">
              <span className={`h-2 w-2 rounded-full ${stage.tone === 'danger' ? 'bg-critical' : stage.tone === 'warn' ? 'bg-moderate' : stage.tone === 'info' ? 'bg-accent' : 'bg-safe'} animate-ping opacity-75`} />
              <span className={`absolute h-2 w-2 rounded-full ${stage.tone === 'danger' ? 'bg-critical' : stage.tone === 'warn' ? 'bg-moderate' : stage.tone === 'info' ? 'bg-accent' : 'bg-safe'}`} />
            </span>
            <span className="hud-label">{stage.label}</span>
          </span>
          <span className="rounded bg-ink-950/80 px-2 py-0.5 font-mono text-[10px] text-ink-300 backdrop-blur-sm">
            RADAR: {topCell ? `${topCell.hazard_label ?? topCell.hazard} CELL` : 'NO ACTIVE CELLS'}
          </span>
        </div>

        {/* top-right compass */}
        <div className="pointer-events-none absolute top-3 right-3 z-[500] flex items-center gap-1.5 rounded border border-ink-600 bg-ink-800/90 px-2 py-0.5 backdrop-blur-md">
          <Compass size={13} className="text-accent-bright" aria-hidden />
          <span className="font-mono text-[11px] text-ink-100">
            {topCell?.movement.bearing_deg !== null && topCell?.movement.bearing_deg !== undefined
              ? `${topCell.movement.bearing_deg.toFixed(0)}° ${topCell.movement.compass}`
              : '— °'}
          </span>
        </div>

        {/* floating spatial chips */}
        <div className="pointer-events-none absolute inset-x-3 bottom-8 z-[500] flex flex-wrap gap-1">
          {topCell && (
            <span className="pointer-events-auto inline-flex items-center gap-1 rounded bg-ink-800/90 px-1.5 py-0.5 backdrop-blur-md">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-critical" />
              <span className="font-mono text-[10px] text-critical">
                DANGER RING · {topCell.radius_km.toFixed(1)} km
              </span>
            </span>
          )}
          {top && (
            <span className="pointer-events-auto inline-flex items-center gap-1 rounded bg-ink-800/90 px-1.5 py-0.5 backdrop-blur-md">
              <Route size={11} className="text-accent-bright" aria-hidden />
              <span className="font-mono text-[10px] text-accent-bright">
                PRIORITY CORRIDOR: {titleCase(top.location_name)}
              </span>
            </span>
          )}
          {shelters[0] && (
            <span className="pointer-events-auto inline-flex items-center gap-1 rounded bg-ink-800/90 px-1.5 py-0.5 backdrop-blur-md">
              <Building2 size={11} className="text-secondary" aria-hidden />
              <span className="font-mono text-[10px] text-secondary">
                SHELTER: {shelters.length} SITE{shelters.length === 1 ? '' : 'S'}
              </span>
            </span>
          )}
        </div>

        {/* bottom telemetry ribbon */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[500] flex items-center justify-between border-t border-ink-700/60 bg-ink-950/90 px-3 py-1 backdrop-blur-md">
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-ink-300">
            <Crosshair size={11} className="text-accent" aria-hidden />
            {topZone ? `${topZone.lat.toFixed(5)}N ${topZone.lng.toFixed(5)}E` : '— N — E'}
          </span>
          <span className="font-mono text-[10px] text-ink-400">
            SYNC: <span className="text-accent-bright">{relativeTime(overview.data?.generated_at)}</span>
          </span>
        </div>
      </HeroMapWithSelection>

      {/* ------------------------------------------------- tactical vectors -- */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-accent-bright" aria-hidden />
          <h2 className="font-head text-sm font-bold tracking-wide text-ink-100 uppercase">Tactical Vectors</h2>
        </div>
        <span className="font-mono text-[10px] text-ink-400 uppercase">
          REFRESH {relativeTime(overview.data?.generated_at).replace(' ago', '')}
        </span>
      </div>

      <Stagger className="mb-4 grid grid-cols-2 gap-2 xl:grid-cols-4">
        <Rise>
          <MetricCard
            label="Affected Pop."
            icon={<Users size={14} aria-hidden />}
            value={m ? fmtNumber(m.people_potentially_exposed) : '—'}
            sub={`${m?.critical_zones ?? 0} critical / ${m?.high_zones ?? 0} high zones`}
            subTone="var(--color-accent-bright)"
            track={m && m.monitored_locations ? Math.min(100, (m.people_potentially_exposed / Math.max(1, m.monitored_locations * 300000)) * 100) : 0}
          />
        </Rise>
        <Rise>
          <MetricCard
            label="Peak Surge"
            icon={<Timer size={14} aria-hidden />}
            value={top ? (top.peak.available ? top.peak.label.replace(/^in\s+/i, '') : '—') : '—'}
            sub={top ? `at ${titleCase(top.location_name)}` : 'no active priorities'}
            subTone="var(--color-tertiary-container, var(--color-high))"
            track={top ? top.risk : 0}
            trackTone="var(--color-high)"
          />
        </Rise>
        <Rise>
          <MetricCard
            label="River Crest"
            icon={<Waves size={14} aria-hidden />}
            value={river?.value != null ? river.value.toFixed(2) : '—'}
            unit={river?.value != null ? `${river.unit} gauge` : undefined}
            sub={river?.freshness_label ?? 'no river gauge in top-priority zone'}
            subTone="var(--color-critical)"
            track={river?.normalised != null ? river.normalised * 100 : 0}
            trackTone="var(--color-critical)"
          />
        </Rise>
        <Rise>
          <MetricCard
            label="Shelter Capacity"
            icon={<BedDouble size={14} aria-hidden />}
            value={shelters.length ? fmtNumber(bedCapacity) : '—'}
            sub={`${shelters.length} site${shelters.length === 1 ? '' : 's'} seeded`}
            subTone="var(--color-secondary)"
            track={bedCapacity > 0 ? Math.min(100, bedCapacity / 60) : 0}
            trackTone="var(--color-secondary)"
          />
        </Rise>
      </Stagger>

      {/* ------------------------------------------------- action directive -- */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="mb-4"
      >
        <button
          type="button"
          onClick={() => navigate('/authority/alerts')}
          className="glow-critical flex h-12 w-full items-center justify-center gap-2 rounded-md border border-critical/60 bg-critical/15 font-mono text-sm font-bold tracking-[0.12em] text-critical uppercase transition-colors hover:bg-critical/25 active:scale-[0.99]"
        >
          <Siren size={18} className="animate-pulse" aria-hidden />
          OPEN ALERTS CONSOLE — {m?.alerts_awaiting_approval ? `${m.alerts_awaiting_approval} AWAITING APPROVAL` : 'REVIEW & ISSUE'}
        </button>
        <div className="mt-1 flex items-center justify-between px-1 font-mono text-[10px] text-ink-400 uppercase">
          <span>BROADCAST: SMS + PUSH + EMAIL (SIMULATED CHANNELS)</span>
          <span className="font-semibold text-critical">AUTHORITY: L3 READY</span>
        </div>
      </motion.div>

      {/* -------------------------------------------------- incident feed -- */}
      <Panel title="Active Incident Feed" icon={<Siren size={14} className="text-critical" />} subtitle="Live alert lifecycle — every row is a real alert record" dense>
        {alerts.loading && !alerts.data ? (
          <div className="space-y-2 p-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-14 w-full" />
            ))}
          </div>
        ) : (alerts.data?.alerts.length ?? 0) === 0 ? (
          <div className="p-4">
            <p className="font-mono text-xs text-ink-400">
              NO ACTIVE INCIDENTS — SYSTEM MONITORING. {t('label.simulated')} SCENARIO IN PROGRESS.
            </p>
          </div>
        ) : (
          <ul>
            {(alerts.data?.alerts ?? []).map((a, i) => {
              const level = a.level as AlertLevel
              const border = level === 'CRITICAL' ? 'bg-critical' : level === 'WARNING' ? 'bg-high' : 'bg-moderate'
              return (
                <motion.li
                  key={a.id}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="relative border-b border-ink-700/50 px-3 py-2 last:border-b-0 odd:bg-ink-850/40"
                >
                  <span className={`absolute top-0 bottom-0 left-0 w-1 ${border}`} aria-hidden />
                  <div className="flex flex-col gap-1 pl-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-head text-sm font-semibold text-ink-100">{a.title}</span>
                      <SeverityBadge level={level === 'WATCH' ? 'MODERATE' : level === 'WARNING' ? 'HIGH' : 'CRITICAL'} label={a.level} size="sm" showAscii={false} />
                    </div>
                    <p className="line-clamp-2 text-xs text-ink-400">{a.message}</p>
                    <div className="flex items-center justify-between font-mono text-[10px] text-ink-400">
                      <span className="flex items-center gap-1">
                        <Radio size={11} className="text-accent" aria-hidden />
                        {titleCase(a.location.name)} · risk {a.risk_score.toFixed(0)}/100
                      </span>
                      <span>{relativeTime(a.created_at)}</span>
                    </div>
                  </div>
                </motion.li>
              )
            })}
          </ul>
        )}
        <div className="border-t border-ink-700/50 px-3 py-1.5">
          <Link to="/authority/alerts" className="inline-flex items-center gap-1 font-mono text-[10px] text-accent-bright uppercase hover:underline">
            FULL CONSOLE <ChevronRight size={11} aria-hidden />
          </Link>
        </div>
      </Panel>
    </Page>
  )
}
