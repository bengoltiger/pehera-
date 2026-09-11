/**
 * Citizen app — "Village Defense" + "Evacuate" screens from the tactical
 * design, in a mobile-first column.
 *
 * Data honesty: the alert, risk, lead time, zone and shelter values all come
 * from the live engine for THIS user's home ward. The mesh network, GPS
 * accuracy and SOS beacon are demonstrated capabilities of the offline-first
 * design and are labelled SIMULATED — nothing is transmitted.
 */
import {
  Check,
  ChevronRight,
  Compass,
  Crosshair,
  Database,
  Droplets,
  Footprints,
  Home,
  LogOut,
  Map as MapIcon,
  MapPin,
  Moon,
  PersonStanding,
  Phone,
  Radio,
  Route,
  Siren,
  Sun,
  Timer,
  TriangleAlert,
  User as UserIcon,
  Wifi,
  Waves,
} from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { DataHonestyBanner } from '../../components/AppShell'
import { HeroMap } from '../../components/HeroMap'
import type { MapRoute, ShelterMark } from '../../components/RiskMap'
import { RadarCanvas } from '../../components/RadarCanvas'
import { Chip, PeHraLogo, SeverityBadge, SeverityBar, StatusPip } from '../../components/ui'
import { Rise } from '../../components/anim'
import { api } from '../../lib/api'
import { clsx, fmtClock, fmtMinutes, fmtNumber, haversineKm, relativeTime, titleCase, walkMinutes } from '../../lib/format'
import { useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import { useAuth, useLive } from '../../lib/providers'
import { useTheme } from '../../lib/theme'
import type { Alert, InfrastructureItem, RiskResponse } from '../../lib/types'
import { MobileCitizen } from './MobileCitizen'
import { SafeRouteScreen } from './SafeRoute'

/* -------------------------------------------------------------------------- */
/* helpers                                                                     */
/* -------------------------------------------------------------------------- */

interface ShelterPick {
  shelter: InfrastructureItem
  distanceKm: number
}

function useShelters(locationId: string | null | undefined): ShelterPick[] {
  const layers = useApi(() => api.mapLayers(), { enabled: !!locationId, liveUpdate: false })
  const locations = useApi(() => api.locations(), { liveUpdate: false })
  return useMemo(() => {
    const zone = locations.data?.locations.find((l) => l.id === locationId)
    const shelters = (layers.data?.infrastructure ?? []).filter((i) => i.kind === 'shelter')
    if (!zone) return []
    return shelters
      .map((s) => ({ shelter: s, distanceKm: haversineKm(zone.latitude, zone.longitude, s.lat, s.lng) }))
      .sort((a, b) => a.distanceKm - b.distanceKm)
  }, [layers.data, locations.data, locationId])
}

function useCountdown(totalSeconds: number | null | undefined): number {
  const [left, setLeft] = useState(totalSeconds ?? 0)
  useEffect(() => {
    setLeft(totalSeconds ?? 0)
    if (totalSeconds == null || totalSeconds <= 0) return
    const id = window.setInterval(() => setLeft((l) => Math.max(0, l - 1)), 1000)
    return () => window.clearInterval(id)
  }, [totalSeconds])
  return left
}

/* -------------------------------------------------------------------------- */
/* Live location — ALWAYS ON: the app acquires and continuously tracks GPS    */
/* itself; the citizen never has to press anything.                           */
/* -------------------------------------------------------------------------- */

interface GpsFix {
  lat: number
  lng: number
  accuracy: number
  at: number
}

function useLiveFix() {
  const [fix, setFix] = useState<GpsFix | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [getting, setGetting] = useState(true)

  useEffect(() => {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      setError('This browser cannot access GPS — distances below are measured from your registered zone centre instead.')
      setGetting(false)
      return
    }
    setGetting(true)
    setError(null)
    let settled = false
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        if (settled) return
        settled = true
        setGetting(false)
        setError(null)
        setFix({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          at: Date.now(),
        })
      },
      (err) => {
        // Permission denial is permanent for this session — stop and say so.
        // Unavailable/timeout are transient: keep the watch running.
        if (err.code === 1) {
          if (settled) return
          settled = true
          setGetting(false)
          setError('Location permission was denied — distances below are measured from your registered zone centre instead.')
        }
      },
      { enableHighAccuracy: true, maximumAge: 60000, timeout: 15000 },
    )
    return () => {
      settled = true
      navigator.geolocation.clearWatch(watchId)
    }
  }, [])

  return { fix, error, getting }
}

interface NearestState {
  data: {
    location: { name: string }
    distance_km: number
    within_coverage: boolean
    note: string | null
  } | null
}

function LiveLocationCard({
  fix,
  error,
  getting,
  nearest,
}: {
  fix: GpsFix | null
  error: string | null
  getting: boolean
  nearest: NearestState
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-ink-600 bg-ink-850 p-3 shadow-md">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-head text-sm font-semibold text-ink-100">
          <Crosshair size={15} className="text-accent-bright" aria-hidden />
          Your location
        </span>
        <Chip tone={fix ? 'good' : 'neutral'}>{fix ? 'FINDING YOU' : 'ON'}</Chip>
      </div>
      {getting && !fix && !error && (
        <p className="flex items-center gap-1.5 text-[11px] text-ink-400">
          <span className="h-1.5 w-1.5 animate-ping rounded-full bg-accent" aria-hidden />
          Finding your location — this happens automatically, you do not need to press anything.
        </p>
      )}
      {error && <p className="rounded bg-moderate/10 px-2 py-1 text-[11px] leading-snug text-moderate">{error}</p>}
      {fix && (
        <div className="space-y-1">
          <p className="font-mono text-[11px] text-ink-200">
            {fix.lat.toFixed(5)}N {fix.lng.toFixed(5)}E · ±{Math.round(fix.accuracy)} m ·{' '}
            {relativeTime(new Date(fix.at).toISOString())}
          </p>
          {nearest.data ? (
            <p className="text-[11px] leading-snug text-ink-300">
              You are in:{' '}
              <strong className="text-ink-100">{titleCase(nearest.data.location.name)}</strong>
              {nearest.data.within_coverage
                ? null
                : ` — this is outside the area we cover${nearest.data.note ? ` (${nearest.data.note})` : ''}`}
            </p>
          ) : (
            <p className="text-[10px] text-ink-500">Checking which area you are in…</p>
          )}
        </div>
      )}
    </div>
  )
}

/** Google-Maps-style journey strip: mode · time · distance · origin label. */
function JourneyBanner({
  distanceKm,
  fromLabel,
}: {
  distanceKm: number | null
  fromLabel: string
}) {
  if (distanceKm == null) return null
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-md border border-accent/40 bg-accent/12 px-2.5 py-1.5">
      <Footprints size={14} className="text-accent-bright" aria-hidden />
      <span className="font-mono text-[12px] font-bold text-accent-bright">
        {walkMinutes(distanceKm)} MIN WALK
      </span>
      <span className="font-mono text-[10px] text-ink-200">· {distanceKm.toFixed(1)} km</span>
      <span className="font-mono text-[10px] text-ink-400">· from {fromLabel}</span>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* When to move — the engine's own trend, peak and lead time, in one verdict   */
/* -------------------------------------------------------------------------- */

/**
 * Display-only mapping of the engine's own outputs (lead time, momentum) to a
 * citizen verdict. No risk arithmetic here — the numbers are the backend's.
 */
function moveGuidance(risk: RiskResponse): { tone: 'danger' | 'warn' | 'good' | 'info'; text: string } {
  const lead = risk.lead_time
  const rate = risk.risk.momentum.rate_per_hour
  const severity = risk.risk.severity.key
  if (severity === 'CRITICAL') {
    return { tone: 'danger', text: 'LEAVE NOW. Your area is in danger — go to the shelter right away.' }
  }
  if (lead?.available && lead.seconds != null && lead.seconds <= 30 * 60) {
    const label = lead.label ?? `${Math.round(lead.seconds / 60)} min`
    return { tone: 'danger', text: `LEAVE NOW — danger is expected within ${label}.` }
  }
  if (lead?.available && lead.seconds != null && lead.seconds <= 120 * 60) {
    const label = lead.label ?? 'the next two hours'
    return { tone: 'warn', text: `START MOVING — reach the shelter within ${label}.` }
  }
  if (severity === 'HIGH') {
    return { tone: 'warn', text: 'Get ready to move. Pack your things and be ready to leave quickly.' }
  }
  if (rate > 1.5) return { tone: 'warn', text: 'Danger is rising — keep this app open and stay ready to move.' }
  if (rate < -1.5) return { tone: 'good', text: 'Danger is going down — no need to move yet. Keep watching.' }
  return { tone: 'info', text: 'Danger level is steady — keep watching. This updates automatically.' }
}

function WhenToMoveCard({ risk }: { risk: RiskResponse }) {
  const g = moveGuidance(risk)
  const mom = risk.risk.momentum
  const lead = risk.lead_time
  const peak = risk.peak
  const toneText = { danger: 'text-critical', warn: 'text-moderate', good: 'text-safe', info: 'text-accent-bright' }[g.tone]
  const toneBox = {
    danger: 'border-critical/50 bg-critical/10',
    warn: 'border-moderate/50 bg-moderate/10',
    good: 'border-safe/40 bg-safe/10',
    info: 'border-accent/40 bg-accent/8',
  }[g.tone]
  return (
    <div className={`rounded-lg border p-3 shadow-md ${toneBox}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-head text-sm font-semibold text-ink-100">
          <Timer size={15} className={toneText} aria-hidden />
          When to move
        </span>
        <span className={`font-mono text-[10px] font-bold ${toneText}`}>
          DANGER LEVEL {risk.risk.overall.toFixed(0)}/100
        </span>
      </div>
      <p className={`mt-1.5 text-xs font-semibold ${toneText}`}>{g.text}</p>
      <div className="mt-2 space-y-1 text-[11px] text-ink-300">
        <p>
          Trend:{' '}
          <span className="text-ink-100">
            {mom.arrow} {mom.label.toLowerCase()}
          </span>{' '}
          <span className="font-mono text-ink-400">
            {mom.rate_per_hour >= 0 ? '+' : ''}
            {mom.rate_per_hour.toFixed(1)} pts/h
          </span>
        </p>
        <p className="leading-snug text-ink-400">{mom.note}</p>
        <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1">
          <span>
            Peak danger:{' '}
            {peak?.available && peak.in_minutes != null ? (
              <span className="font-mono text-ink-100">
                {peak.risk?.toFixed(0)}/100 in {fmtMinutes(peak.in_minutes)}
              </span>
            ) : (
              <span className="text-ink-500">{peak?.reason_unavailable ?? 'none predicted'}</span>
            )}
          </span>
          <span>
            Time before danger:{' '}
            {lead?.available && lead.label ? (
              <span className="font-mono text-ink-100">{lead.label}</span>
            ) : (
              <span className="text-ink-500">no danger expected soon</span>
            )}
          </span>
        </div>
      </div>
    </div>
  )
}

const CHECKLIST = [
  { id: 'gobag', title: 'Pack your go-bag', detail: 'Aadhaar and other ID cards, bank passbooks, prescription medicine, 3 days of dry food.' },
  { id: 'livestock', title: 'Move your animals', detail: 'Untie tethered animals and lead them along the high path toward the community pens.' },
  { id: 'house', title: 'Make your house safe', detail: 'Turn off the main electric switch and cover the drinking well.' },
  { id: 'path', title: 'Use only the marked high path', detail: 'Do NOT cross the low eastern drain or the bridge, no matter what.' },
]

function useChecklist() {
  const [done, setDone] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem('pehra.checklist') ?? '{}')
    } catch {
      return {}
    }
  })
  const toggle = (id: string) => {
    setDone((d) => {
      const next = { ...d, [id]: !d[id] }
      try {
        localStorage.setItem('pehra.checklist', JSON.stringify(next))
      } catch {
        /* storage disabled */
      }
      return next
    })
  }
  return { done, toggle, count: CHECKLIST.filter((c) => done[c.id]).length }
}

function Checklist() {
  const { done, toggle, count } = useChecklist()
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-ink-600 bg-ink-850 p-3 shadow-md">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 font-head text-sm font-semibold text-ink-100">
          <Check size={15} className="text-accent-bright" aria-hidden />
          Pack these first
        </span>
        <span className={clsx('font-mono text-[11px]', count === CHECKLIST.length ? 'font-bold text-safe' : 'text-accent-bright')}>
          {count}/{CHECKLIST.length} DONE
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {CHECKLIST.map((c) => (
          <label
            key={c.id}
            className="flex cursor-pointer items-start gap-2 rounded-md bg-ink-900 p-2 transition-colors hover:bg-ink-800"
          >
            <input
              type="checkbox"
              checked={!!done[c.id]}
              onChange={() => toggle(c.id)}
              className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded accent-[var(--color-accent)]"
            />
            <span className="min-w-0">
              <span className={clsx('block text-xs font-medium text-ink-100', done[c.id] && 'line-through opacity-60')}>{c.title}</span>
              <span className="block text-[11px] leading-snug text-ink-400">{c.detail}</span>
            </span>
          </label>
        ))}
      </div>
    </div>
  )
}

function SosBeacon() {
  const [sent, setSent] = useState(false)
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-ink-600 bg-ink-800 p-3">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Siren size={16} className="text-critical" aria-hidden />
          <span className="hud-label tracking-wider text-critical">IF YOU ARE IN TROUBLE</span>
        </span>
        <span className="font-mono text-[10px] text-ink-400">DEMO — NOTHING IS SENT</span>
      </div>
      <p className="text-[11px] leading-snug text-ink-400">
        Tap the button if you are trapped, injured, or cannot walk out. In this demo nothing is sent — it shows how
        the real system would tell the rescue team where you are.
      </p>
      <motion.button
        type="button"
        whileTap={{ scale: 0.98 }}
        onClick={() => setSent(true)}
        className={clsx(
          'flex h-12 w-full items-center justify-center gap-2 rounded font-mono text-xs font-bold tracking-[0.15em] uppercase transition-colors',
          sent ? 'bg-critical text-ink-50' : 'bg-critical/15 text-critical hover:bg-critical/25',
        )}
      >
        <Radio size={16} className={sent ? 'animate-ping' : ''} aria-hidden />
        {sent ? 'HELP REQUESTED (DEMO)' : 'I NEED HELP — SEND MY LOCATION'}
      </motion.button>
      {sent && (
        <p className="rounded bg-ink-950 px-2 py-1 text-center font-mono text-[10px] text-accent-bright">
          DEMO ONLY: NO REAL SIGNAL WAS SENT. IN THE REAL SYSTEM YOUR LOCATION GOES TO THE RELIEF TEAM.
        </p>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Home (Village Defense)                                                      */
/* -------------------------------------------------------------------------- */

function VillageDefense({
  onEvacuate,
}: {
  onEvacuate: () => void
}) {
  const { user } = useAuth()
  const { t } = useI18n()
  const locationId = user?.home_location_id ?? 'loc_colaba'
  const risk = useApi((s) => api.risk(locationId, { detail: true, lang: user?.language ?? 'en' }, s), { deps: [locationId] })
  const locAlerts = useApi(() => api.alertsForLocation(locationId), { deps: [locationId] })
  const shelters = useShelters(locationId)
  const topShelter = shelters[0]

  const { fix, error: gpsError, getting: gpsGetting } = useLiveFix()
  // Round to ~100 m so the continuous watch only refetches the nearest zone
  // once the user has meaningfully moved.
  const fixKey = fix ? `${Math.round(fix.lat * 1000)}:${Math.round(fix.lng * 1000)}` : null
  const nearest = useApi(() => api.nearestLocation(fix!.lat, fix!.lng), {
    enabled: !!fix,
    deps: [fixKey],
    liveUpdate: false,
  })
  const shelterFromYouKm =
    fix && topShelter ? haversineKm(fix.lat, fix.lng, topShelter.shelter.lat, topShelter.shelter.lng) : null

  const activeAlerts = (locAlerts.data?.issued ?? []).filter((a) => a.is_active)
  const alert = activeAlerts[0]
  const stage = alert
    ? alert.level === 'CRITICAL'
      ? { label: 'STAGE 3: CRITICAL — EVACUATE', tone: 'danger' as const }
      : alert.level === 'WARNING'
        ? { label: 'STAGE 2: WARNING — PREPARE', tone: 'warn' as const }
        : { label: 'STAGE 1: WATCH', tone: 'info' as const }
    : { label: 'ALL CLEAR — MONITORING', tone: 'good' as const }

  const r = risk.data
  const zone = r?.location

  if (risk.loading && !r) {
    return (
      <div className="space-y-2 p-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton h-24 w-full" />
        ))}
      </div>
    )
  }
  if (risk.error || !r) {
    return (
      <div className="p-4">
        <Chip tone="danger">No connection</Chip>
        <p className="mt-2 text-xs text-ink-400">
          {risk.error?.message ?? 'Could not load your area.'} Showing last saved information where possible.
        </p>
      </div>
    )
  }

  /* Journey: straight-line walk from the user (live GPS, or the zone centre
     when there is no fix) to the nearest shelter — text on Home; the route
     itself is drawn on the Map tab and while Evacuate is tracking. */
  const journeyKm = fix ? (shelterFromYouKm ?? null) : topShelter ? topShelter.distanceKm : null
  const journeyFromLabel = fix ? 'your location' : 'your area'

  return (
    <div className="flex flex-col gap-3 p-3 pb-6">
      {/* identity header */}
      <Rise>
        <div className="flex flex-col gap-2 rounded-lg border border-ink-600 bg-ink-850 p-3 shadow-md">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 font-head text-sm font-bold tracking-tight text-ink-50 uppercase">
              <Waves size={17} className="text-accent-bright" aria-hidden />
              {t('citizen.defense')}
            </span>
            <Chip tone="info">WORKS OFFLINE</Chip>
          </div>
          <div className="flex items-center justify-between gap-2 pt-0.5">
            <span
              className={clsx(
                'flex items-center gap-1.5 font-mono text-[11px] font-bold',
                stage.tone === 'danger' ? 'text-critical' : stage.tone === 'warn' ? 'text-moderate' : stage.tone === 'info' ? 'text-accent-bright' : 'text-safe',
              )}
            >
              {stage.tone !== 'good' && <span className="h-2 w-2 animate-ping rounded-full bg-current" />}
              {stage.label}
            </span>
            <span className="font-mono text-[10px] text-ink-400">
              SYNC: {relativeTime(r.generated_at)}
            </span>
          </div>
        </div>
      </Rise>

      {/* zone badge */}
      <Rise>
        <div className="flex flex-col gap-1.5 rounded-lg border border-ink-700 bg-ink-900 p-3">
          <div className="flex items-center gap-1.5 text-accent-bright">
            <MapIcon size={15} aria-hidden />
            <span className="font-mono text-xs font-bold tracking-[0.08em] uppercase">
              {titleCase(zone?.name ?? locationId)}
            </span>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-1.5">
            <span className="text-[11px] text-ink-400">
              About {fmtNumber(zone?.population)} people live here
            </span>
            <Chip tone="info">YOUR LOCAL AREA</Chip>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <SeverityBadge level={r.risk.severity.key} label={r.risk.severity.label} score={r.risk.overall} size="sm" />
            <SeverityBar value={r.risk.overall} level={r.risk.severity.key} height={6} className="flex-1" />
          </div>
        </div>
      </Rise>

      {/* alert / all-clear banner */}
      <AnimatePresence mode="wait">
        {alert ? (
          <motion.div
            key="alert"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            className="glow-critical flex flex-col gap-1.5 rounded-lg border border-critical/50 bg-critical/15 p-3"
            role="alert"
          >
            <div className="flex items-center gap-1.5">
              <TriangleAlert size={18} className="animate-pulse text-critical" aria-hidden />
              <span className="font-head text-sm font-bold tracking-tight text-ink-50 uppercase">
                {alert.title}
              </span>
            </div>
            <p className="text-xs leading-relaxed text-ink-200">{alert.message}</p>
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              <SeverityBadge level={r.risk.severity.key} label={r.risk.severity.label} size="sm" />
              {r.lead_time?.available && r.lead_time.label && (
                <Chip tone="danger" icon={<Timer size={10} />}>
                  {r.lead_time.label}
                </Chip>
              )}
              <Chip tone="neutral">RISK {r.risk.overall.toFixed(0)}/100</Chip>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="clear"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col gap-1.5 rounded-lg border border-safe/40 bg-safe/10 p-3"
          >
            <div className="flex items-center gap-1.5">
              <Wifi size={16} className="text-safe" aria-hidden />
              <span className="font-head text-sm font-bold text-safe uppercase">All clear — system watching</span>
            </div>
            <p className="text-xs leading-relaxed text-ink-300">
              Current risk {r.risk.overall.toFixed(0)}/100 ({r.risk.severity.label}), confidence{' '}
              {r.risk.confidence.value.toFixed(0)}%. {r.risk.momentum.label} — {r.risk.momentum.note}
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* when to move — risk rate, trend, peak and lead time */}
      <Rise>
        <WhenToMoveCard risk={r} />
      </Rise>

      {/* live GPS location */}
      <Rise>
        <LiveLocationCard fix={fix} error={gpsError} getting={gpsGetting} nearest={nearest} />
      </Rise>

      {/* journey to the nearest shelter (text only — the map lives on the
          Map tab and during Evacuate, so the home screen stays lean for
          low-network phones: zero tile downloads on the main screen) */}
      <Rise>
        <div className="flex flex-col gap-1.5">
          <JourneyBanner distanceKm={journeyKm} fromLabel={journeyFromLabel} />
          {alert && (
            <p className="flex items-center gap-1.5 rounded-md bg-critical/10 px-2.5 py-1.5 font-mono text-[11px] font-bold text-critical">
              ⚠ You are inside the danger area
            </p>
          )}
        </div>
      </Rise>

      {/* shelter card */}
      {topShelter && (
        <Rise>
          <div className="flex flex-col gap-2 rounded-lg border border-ink-600 bg-ink-850 p-3 shadow-md">
            <div className="flex items-start justify-between gap-2">
              <div className="flex flex-col">
                <span className="hud-label text-accent-bright">YOUR NEAREST SAFE PLACE</span>
                <h2 className="font-head text-sm font-bold text-ink-50">{titleCase(topShelter.shelter.name)}</h2>
                {topShelter.shelter.address && (
                  <p className="mt-0.5 flex items-start gap-1 text-[11px] leading-snug text-ink-300">
                    <MapPin size={11} className="mt-0.5 shrink-0 text-ink-500" aria-hidden />
                    {topShelter.shelter.address}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <span className="rounded bg-ink-700 px-1.5 py-0.5 font-mono text-[11px] font-bold text-accent-bright">
                  {topShelter.distanceKm.toFixed(1)} KM
                </span>
                {shelterFromYouKm != null && (
                  <span className="rounded bg-safe/15 px-1.5 py-0.5 font-mono text-[9px] font-bold text-safe">
                    {shelterFromYouKm.toFixed(1)} KM FROM YOU
                  </span>
                )}
              </div>
            </div>
            {topShelter.shelter.phone && (
              <a
                href={`tel:${topShelter.shelter.phone.replace(/\s/g, '')}`}
                className="flex items-center gap-1.5 rounded-md border border-ink-600 px-2 py-1.5 text-[11px] text-accent-bright transition-colors hover:bg-ink-800"
              >
                <Phone size={12} aria-hidden />
                Call the shelter: {topShelter.shelter.phone}
              </a>
            )}
            <div className="flex items-center justify-between rounded-md bg-ink-900 p-2">
              <span className="flex items-center gap-1.5">
                <Footprints size={20} className="text-accent-bright" aria-hidden />
                <span className="flex flex-col">
                  <span className="font-mono text-xs font-bold text-ink-100">{walkMinutes(topShelter.distanceKm)} MIN WALK</span>
                  <span className="font-mono text-[9px] text-ink-400">STRAIGHT-LINE ESTIMATE</span>
                </span>
              </span>
              {topShelter.shelter.capacity != null && (
                <span className="font-mono text-[10px] text-accent-bright">
                  SPACE FOR ~{fmtNumber(topShelter.shelter.capacity)}
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-1 pt-0.5">
              <span className="flex items-center gap-1 rounded bg-ink-700 px-1.5 py-0.5">
                <Droplets size={11} className="text-accent-bright" aria-hidden />
                <span className="hud-label text-ink-100">DRINKING WATER</span>
              </span>
              <span className="flex items-center gap-1 rounded bg-ink-700 px-1.5 py-0.5">
                <UserIcon size={11} className="text-secondary" aria-hidden />
                <span className="hud-label text-ink-100">MEDICAL HELP</span>
              </span>
              <span className="flex items-center gap-1 rounded bg-ink-700 px-1.5 py-0.5">
                <PersonStanding size={11} className="text-accent-bright" aria-hidden />
                <span className="hud-label text-ink-100">SHELTER</span>
              </span>
            </div>
            <p className="font-mono text-[9px] text-ink-500 uppercase">
              Distance and time are straight-line estimates — not a road map.
            </p>
          </div>
        </Rise>
      )}

      {/* primary CTA */}
      <motion.button
        type="button"
        whileTap={{ scale: 0.99 }}
        onClick={onEvacuate}
        className="glow-ai flex h-14 w-full items-center justify-center gap-2 rounded-lg border border-accent/50 bg-accent/20 font-head text-sm font-bold tracking-[0.1em] text-accent-bright uppercase transition-colors hover:bg-accent/30"
      >
        <Route size={20} aria-hidden />
        SHOW ME THE WAY TO SAFETY
      </motion.button>

      <Checklist />

      {/* mesh card */}
      <Rise>
        <div className="flex items-start gap-2.5 rounded-lg border border-ink-600 bg-ink-800 p-3">
          <Wifi size={22} className="mt-0.5 shrink-0 text-accent-bright" aria-hidden />
          <div className="min-w-0 flex flex-col gap-0.5">
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-xs font-bold text-accent-bright">WORKS WITHOUT INTERNET</span>
              <Chip tone="neutral">DEMO</Chip>
            </div>
            <p className="text-[11px] leading-snug text-ink-400">
              The app stores the important information on your phone, so it keeps working when there is no network.
              The home screen is kept light on purpose so it uses as little data as possible.
            </p>
          </div>
        </div>
      </Rise>

      <SosBeacon />
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Evacuate                                                                    */
/* -------------------------------------------------------------------------- */

function Evacuate({ user }: { user: { home_location_id?: string | null; language?: 'en' | 'hi' } }) {
  const locationId = user.home_location_id ?? 'loc_colaba'
  const risk = useApi((s) => api.risk(locationId, { detail: true, lang: user.language ?? 'en' }, s), { deps: [locationId] })
  const locAlerts = useApi(() => api.alertsForLocation(locationId), { deps: [locationId] })
  const shelters = useShelters(locationId)
  const threats = useApi(() => api.threats())
  const topShelter = shelters[0]

  const { fix, error: gpsError, getting: gpsGetting } = useLiveFix()
  const fixKey = fix ? `${Math.round(fix.lat * 1000)}:${Math.round(fix.lng * 1000)}` : null
  const nearest = useApi(() => api.nearestLocation(fix!.lat, fix!.lng), {
    enabled: !!fix,
    deps: [fixKey],
    liveUpdate: false,
  })
  const shelterFromYouKm =
    fix && topShelter ? haversineKm(fix.lat, fix.lng, topShelter.shelter.lat, topShelter.shelter.lng) : null

  const activeAlerts = (locAlerts.data?.issued ?? []).filter((a) => a.is_active)
  const alert: Alert | undefined = activeAlerts[0]
  const leadSeconds = risk.data?.lead_time?.available ? risk.data.lead_time.seconds : null
  const countdown = useCountdown(leadSeconds)
  const [tracking, setTracking] = useState(false)

  const r = risk.data
  const zone = r?.location

  /* Journey shown on the map while tracking: user → nearest shelter. */
  const evacFrom: [number, number] | null = fix
    ? [fix.lat, fix.lng]
    : r
      ? [r.location.latitude, r.location.longitude]
      : null
  const evacJourneyKm = fix ? (shelterFromYouKm ?? null) : topShelter ? topShelter.distanceKm : null
  const evacFromLabel = fix ? 'your location' : 'your area'
  const evacRoute: MapRoute | null =
    evacFrom && topShelter
      ? {
          from: evacFrom,
          to: [topShelter.shelter.lat, topShelter.shelter.lng],
          label: evacJourneyKm != null ? `NEAREST SHELTER · ${walkMinutes(evacJourneyKm)} MIN WALK` : 'NEAREST SHELTER',
        }
      : null
  const evacShelterMarks: ShelterMark[] = shelters.map((s, i) => ({
    id: s.shelter.id,
    name: s.shelter.name,
    lat: s.shelter.lat,
    lng: s.shelter.lng,
    nearest: i === 0,
    distanceKm: s.distanceKm,
  }))

  return (
    <div className="flex flex-col gap-3 p-3 pb-6">
      {/* critical notice */}
      <div
        className={clsx(
          'relative flex flex-col gap-2 overflow-hidden rounded-lg p-3 shadow-lg',
          alert ? 'glow-critical border border-critical/60 bg-critical/20' : 'border border-safe/40 bg-safe/10',
        )}
        role="alert"
        aria-live="assertive"
      >
        <div className="flex items-start justify-between gap-2">
          <span className="flex items-center gap-2">
            <span className={clsx('h-2.5 w-2.5 rounded-full', alert ? 'animate-ping bg-critical' : 'bg-safe')} />
            <span className={clsx('hud-label tracking-[0.15em]', alert ? 'text-critical' : 'text-safe')}>
              {alert ? `DANGER — LEAVE NOW · ${titleCase(zone?.name ?? 'YOUR AREA').toUpperCase()}` : 'ALL CLEAR'}
            </span>
          </span>
          {alert && leadSeconds != null && (
            <span className="rounded bg-ink-950/70 px-1.5 py-0.5 font-mono text-[11px] font-bold text-ink-50">
              TIME LEFT: {fmtClock(countdown)}
            </span>
          )}
        </div>
        {alert ? (
          <>
            <h1 className="font-head text-xl font-bold tracking-tight text-ink-50 uppercase">{alert.title}</h1>
            <p className="text-xs leading-relaxed text-ink-100">{alert.message}</p>
          </>
        ) : (
          <>
            <h1 className="font-head text-lg font-bold tracking-tight text-safe uppercase">No evacuation required</h1>
            <p className="text-xs leading-relaxed text-ink-300">
              There is no alert for your area right now. Keep the app open — it will tell you the moment action is
              needed.
            </p>
          </>
        )}
        {alert && (
          <div className="absolute inset-0 bg-gradient-to-r from-critical/10 via-transparent to-critical/20 pointer-events-none" />
        )}
      </div>

      {/* primary action */}
      <motion.button
        type="button"
        whileTap={{ scale: 0.98 }}
        onClick={() => setTracking((t) => !t)}
        aria-pressed={tracking}
        className="flex h-14 w-full items-center justify-between rounded-lg border border-accent/50 bg-accent/25 px-4 shadow-xl transition-colors hover:bg-accent/35"
      >
        <span className="flex items-center gap-2.5 text-left">
          <PersonStanding size={26} className="text-accent-bright" aria-hidden />
          <span className="flex flex-col">
            <span className="font-head text-sm font-bold tracking-tight text-ink-50 uppercase">
              {tracking ? 'HIDING THE ROUTE' : 'SHOW ME THE WAY TO SAFETY'}
            </span>
            <span className="font-mono text-[10px] text-ink-200 opacity-80">WORKS WITHOUT SIGNAL</span>
          </span>
        </span>
        <ChevronRight
          size={22}
          className={clsx('text-accent-bright transition-transform', tracking && 'rotate-90')}
          aria-hidden
        />
      </motion.button>

      {/* tracking status — the toggle above must show a real consequence */}
      {tracking && (
        <div className="rounded-lg border border-accent/50 bg-accent/10 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 font-mono text-[11px] font-bold tracking-wider text-accent-bright">
              <span className="relative flex h-2 w-2">
                <span className="absolute h-2 w-2 animate-ping rounded-full bg-accent opacity-75" />
                <span className="relative h-2 w-2 rounded-full bg-accent" />
              </span>
              ROUTE SHOWN
            </span>
            {topShelter && (
              <span className="font-mono text-[10px] text-ink-300">ETA {walkMinutes(topShelter.distanceKm)} min</span>
            )}
          </div>
          <p className="mt-1 text-[11px] leading-snug text-ink-300">
            {topShelter
              ? `Route: ${titleCase(zone?.name ?? 'your area')} → ${titleCase(topShelter.shelter.name)} · ${topShelter.distanceKm.toFixed(1)} km (straight line). Demo: the GPS position is simulated.`
              : 'Finding the nearest shelter…'}
          </p>
        </div>
      )}

      {/* live GPS location — matters most mid-evacuation */}
      <LiveLocationCard fix={fix} error={gpsError} getting={gpsGetting} nearest={nearest} />

      {/* journey to the shelter while tracking */}
      {tracking && <JourneyBanner distanceKm={evacJourneyKm} fromLabel={evacFromLabel} />}

      {/* radar / journey map card */}
      <div className="flex flex-col overflow-hidden rounded-lg border border-ink-600 shadow-md">
        {tracking ? (
          <div className="relative">
            <HeroMap
              className="h-72"
              selectedLocationId={locationId}
              route={evacRoute}
              shelters={evacShelterMarks}
              fitRoute
            >
              <div className="pointer-events-none absolute top-2 left-12 flex items-center gap-1.5 rounded bg-ink-950/85 px-2 py-1 backdrop-blur-md">
                <Compass size={13} className="text-accent-bright" aria-hidden />
                <span className="font-mono text-[10px] text-ink-100">
                  {fix
                    ? `${fix.lat.toFixed(5)}N ${fix.lng.toFixed(5)}E · GPS`
                    : zone
                      ? `${zone.latitude.toFixed(5)}N ${zone.longitude.toFixed(5)}E`
                      : '—'}
                </span>
              </div>
            </HeroMap>
          </div>
        ) : (
          <div className="relative">
            <RadarCanvas cells={threats.data?.threat_cells ?? []} heightClass="aspect-[16/10]" />
            <div className="pointer-events-none absolute top-2 left-2 flex items-center gap-1.5 rounded bg-ink-950/85 px-2 py-1 backdrop-blur-md">
              <Compass size={13} className="text-accent-bright" aria-hidden />
              <span className="font-mono text-[10px] text-ink-100">
                {zone ? `${zone.latitude.toFixed(5)}N ${zone.longitude.toFixed(5)}E` : '—'}
              </span>
            </div>
            {topShelter && (
              <div className="pointer-events-none absolute top-5 right-5 flex flex-col items-center gap-0.5">
                <span className="animate-bounce text-accent-bright">⛨</span>
                <span className="rounded bg-accent px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wider text-ink-950 uppercase">
                  {titleCase(topShelter.shelter.name).toUpperCase()} (SAFE)
                </span>
              </div>
            )}
            <div className="pointer-events-none absolute bottom-8 left-5 flex items-center gap-1.5">
              <span className="relative flex h-4 w-4 items-center justify-center">
                <span className="absolute h-4 w-4 animate-ping rounded-full bg-critical/60" />
                <span className="relative h-2.5 w-2.5 rounded-full bg-critical" />
              </span>
              <span className="flex flex-col rounded bg-ink-950/90 px-1.5 py-0.5">
                <span className="hud-label tracking-wider text-critical">YOU ARE HERE</span>
                <span className="font-mono text-[9px] text-ink-300">{titleCase(zone?.name ?? 'your zone')}</span>
              </span>
            </div>
          </div>
        )}
        <div className="flex items-center justify-between bg-ink-800 px-2.5 py-1.5">
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-ink-300">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            {tracking ? 'ROUTE TO SHELTER · ESTIMATED WALK' : 'THREAT RADAR (DEMO)'}
          </span>
          <span className="font-mono text-[10px] text-accent-bright">
            {topShelter
              ? `SHELTER ${topShelter.distanceKm.toFixed(1)} KM${evacJourneyKm != null ? ` · ${walkMinutes(evacJourneyKm)} MIN WALK` : ''}`
              : 'NO SHELTER FOUND'}
          </span>
        </div>
      </div>

      {/* nearest safe haven */}
      {topShelter && (
        <div className="flex flex-col gap-2 rounded-lg border border-ink-600 bg-ink-850 p-3 shadow-md">
          <div className="flex items-center justify-between">
            <span className="hud-label tracking-[0.15em] text-ink-400">YOUR NEAREST SAFE PLACE</span>
            <Chip tone="good">OPEN</Chip>
          </div>
          <div>
            <h2 className="font-head text-base font-bold text-ink-50">{titleCase(topShelter.shelter.name)}</h2>
            <p className="font-mono text-[10px] text-ink-400">{topShelter.shelter.location_id.toUpperCase()} · SEED DATA</p>
            {topShelter.shelter.address && (
              <p className="mt-1 flex items-start gap-1 text-[11px] leading-snug text-ink-300">
                <MapPin size={11} className="mt-0.5 shrink-0 text-ink-500" aria-hidden />
                {topShelter.shelter.address}
              </p>
            )}
          </div>
          <div className="mt-0.5 grid grid-cols-2 gap-2">
            <div className="flex flex-col rounded bg-ink-900 p-2">
              <span className="font-mono text-[9px] text-ink-400 uppercase">Distance</span>
              <span className="font-head text-sm font-bold text-ink-100">{topShelter.distanceKm.toFixed(1)} km</span>
              {shelterFromYouKm != null && (
                <span className="mt-0.5 font-mono text-[9px] font-bold text-safe">
                  {shelterFromYouKm.toFixed(1)} KM FROM YOU
                </span>
              )}
            </div>
            <div className="flex flex-col rounded bg-ink-900 p-2">
              <span className="font-mono text-[9px] text-ink-400 uppercase">Time to reach</span>
              <span className="font-head text-sm font-bold text-accent-bright">
                {walkMinutes(topShelter.distanceKm)}m <span className="text-[10px] font-normal text-ink-400">walk</span>
              </span>
            </div>
          </div>
          {topShelter.shelter.phone && (
            <a
              href={`tel:${topShelter.shelter.phone.replace(/\s/g, '')}`}
              className="flex items-center gap-1.5 rounded-md border border-ink-600 px-2 py-1.5 text-[11px] text-accent-bright transition-colors hover:bg-ink-800"
            >
              <Phone size={12} aria-hidden />
              {topShelter.shelter.phone}
            </a>
          )}
          {topShelter.shelter.capacity != null && (
            <p className="font-mono text-[10px] text-ink-400">
              Space for about {fmtNumber(topShelter.shelter.capacity)} people
            </p>
          )}
        </div>
      )}

      <Checklist />

      {/* offline + mesh tiles */}
      <div className="grid grid-cols-2 gap-2">
        <div className="flex items-center gap-2 rounded-lg border border-ink-600 bg-ink-850 p-2.5">
          <Database size={18} className="shrink-0 text-accent-bright" aria-hidden />
          <div className="min-w-0 flex flex-col">
            <span className="hud-label text-ink-400">OFFLINE MAP</span>
            <span className="font-mono text-[10px] text-ink-100 truncate">WORKING</span>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-ink-600 bg-ink-850 p-2.5">
          <Wifi size={18} className="shrink-0 text-accent-bright" aria-hidden />
          <div className="min-w-0 flex flex-col">
            <span className="hud-label text-ink-400">MESH NETWORK</span>
            <span className="font-mono text-[10px] text-ink-100 truncate">DEMO</span>
          </div>
        </div>
      </div>

      <SosBeacon />
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Map tab                                                                     */
/* -------------------------------------------------------------------------- */

function CitizenMap({ user }: { user: { home_location_id?: string | null } }) {
  const homeId = user.home_location_id ?? 'loc_colaba'
  const [pickedId, setPickedId] = useState<string | null>(null)
  const locationId = pickedId ?? homeId
  const isHome = locationId === homeId
  const risk = useApi(() => api.risk(locationId, { detail: true }), { deps: [locationId] })
  const { fix } = useLiveFix()
  const shelters = useShelters(locationId)
  const topShelter = shelters[0]

  /* Journey from the ward on screen (or your live GPS) to its nearest shelter. */
  const center = risk.data?.location
  const journeyFrom: [number, number] | null = fix
    ? [fix.lat, fix.lng]
    : center
      ? [center.latitude, center.longitude]
      : null
  const journeyKm = fix
    ? topShelter
      ? haversineKm(fix.lat, fix.lng, topShelter.shelter.lat, topShelter.shelter.lng)
      : null
    : topShelter
      ? topShelter.distanceKm
      : null
  const journeyFromLabel = fix ? 'your location' : 'this area'
  const journeyRoute: MapRoute | null =
    journeyFrom && topShelter
      ? {
          from: journeyFrom,
          to: [topShelter.shelter.lat, topShelter.shelter.lng],
          label: journeyKm != null ? `NEAREST SHELTER · ${walkMinutes(journeyKm)} MIN WALK` : 'NEAREST SHELTER',
        }
      : null
  /* Every shelter gets a pin, so the citizen can see ALL options — the
     blue line goes to the nearest one, the others are there too. */
  const shelterMarks: ShelterMark[] = shelters.map((s, i) => ({
    id: s.shelter.id,
    name: s.shelter.name,
    lat: s.shelter.lat,
    lng: s.shelter.lng,
    nearest: i === 0,
    distanceKm: s.distanceKm,
  }))

  return (
    <div className="flex flex-col gap-3 p-3 pb-6">
      <JourneyBanner distanceKm={journeyKm} fromLabel={journeyFromLabel} />
      <HeroMap
        className="h-[26rem] rounded-lg"
        selectedLocationId={locationId}
        onSelectLocation={(id) => setPickedId(id)}
        route={journeyRoute}
        shelters={shelterMarks}
        fitRoute
      >
        <div className="pointer-events-none absolute top-2 left-12 z-[500] flex flex-col items-start gap-1">
          <span className="rounded bg-ink-950/90 px-2 py-1 font-mono text-[9px] font-bold text-accent-bright backdrop-blur-md">
            VIEWING: {titleCase(risk.data?.location?.name ?? 'YOUR AREA').toUpperCase()}
            {!isHome && risk.data?.location?.name ? ' · TAPPED AREA' : ''}
          </span>
          {shelterMarks.length > 0 && (
            <span className="rounded bg-ink-950/90 px-2 py-1 font-mono text-[9px] font-bold text-safe backdrop-blur-md">
              {shelterMarks.length} SHELTER{shelterMarks.length === 1 ? '' : 'S'} MARKED · BLUE LINE = NEAREST
            </span>
          )}
        </div>
      </HeroMap>
      {risk.data && (
        <div className="rounded-lg border border-ink-600 bg-ink-850 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-head text-sm font-semibold text-ink-100">{titleCase(risk.data.location.name)}</span>
            <SeverityBadge level={risk.data.risk.severity.key} label={risk.data.risk.severity.label} score={risk.data.risk.overall} size="sm" />
          </div>
          <SeverityBar value={risk.data.risk.overall} level={risk.data.risk.severity.key} height={8} className="mt-2" showTicks />
          <p className="mt-2 text-[11px] leading-snug text-ink-400">
            Trend: {risk.data.risk.momentum.note} How sure: {risk.data.risk.confidence.value.toFixed(0)}%.
          </p>
          {!isHome && (
            <button
              type="button"
              onClick={() => setPickedId(null)}
              className="mt-2 rounded-md border border-ink-600 px-2 py-1 text-[11px] text-ink-200 transition-colors hover:bg-ink-800"
            >
              ← Back to your area
            </button>
          )}
        </div>
      )}
      <p className="font-mono text-[9px] leading-snug text-ink-500 uppercase">
        The blue line is your walk to the NEAREST shelter (★). Green pins mark ALL shelters so you can see every
        option. Tap any area to see its danger level. Distances are straight-line, not road distances.
      </p>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Shell                                                                       */
/* -------------------------------------------------------------------------- */

type Tab = 'home' | 'map' | 'safe' | 'evacuate' | 'connect'

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'home', label: 'Home', icon: <Home size={19} aria-hidden /> },
  { id: 'map', label: 'Map', icon: <MapIcon size={19} aria-hidden /> },
  { id: 'safe', label: 'Route', icon: <Route size={19} aria-hidden /> },
  { id: 'connect', label: 'Relay', icon: <Radio size={19} aria-hidden /> },
  { id: 'evacuate', label: 'Safety', icon: <Siren size={19} aria-hidden /> },
]

export default function CitizenApp({ initialTab = 'home' }: { initialTab?: Tab }) {
  const { user, signOut } = useAuth()
  const { theme, toggle } = useTheme()
  const { connected } = useLive()
  const location = useLocation()
  const [tab, setTab] = useState<Tab>(initialTab)

  useEffect(() => {
    if (location.pathname.endsWith('/evacuate')) setTab('evacuate')
    else if (location.pathname === '/citizen') setTab(initialTab)
  }, [location.pathname, initialTab])

  return (
    <div className="flex h-full min-h-0 justify-center bg-ink-950">
      <div className="flex h-full min-h-0 w-full max-w-[440px] flex-col border-ink-700/60 sm:border-x">
        <DataHonestyBanner />

        {/* header */}
        <header className="flex shrink-0 items-center gap-2 border-b border-ink-700/60 bg-ink-900/95 px-3 py-2 backdrop-blur">
          <PeHraLogo size={30} />
          <span className="min-w-0 flex-1 leading-none">
            <span className="flex items-baseline gap-1.5">
              <span className="font-head text-xs font-extrabold tracking-[0.12em] text-ink-50 uppercase">PEHRA</span>
              <span className="font-mono text-[10px] font-semibold tracking-[0.18em] text-accent-bright">//VILLAGE</span>
            </span>
            <span className="mt-0.5 block truncate font-mono text-[9px] tracking-[0.06em] text-ink-400 uppercase">
              {user?.full_name ?? 'citizen'}
            </span>
          </span>
          <StatusPip tone={connected ? 'good' : 'danger'} label={connected ? 'ONLINE' : 'OFFLINE'} ping={!connected} />
          <button
            type="button"
            onClick={toggle}
            aria-label="Toggle theme"
            className="grid h-7 w-7 place-items-center rounded-md border border-ink-600 text-ink-300 hover:bg-ink-800 hover:text-accent-bright"
          >
            {theme === 'dark' ? <Sun size={13} aria-hidden /> : <Moon size={13} aria-hidden />}
          </button>
          <button
            type="button"
            onClick={signOut}
            aria-label="Sign out"
            title="Sign out"
            className="grid h-7 w-7 place-items-center rounded-md border border-ink-600 text-ink-300 transition-colors hover:bg-ink-800 hover:text-critical"
          >
            <LogOut size={13} aria-hidden />
          </button>
        </header>

        {/* content */}
        <main className="min-h-0 flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              {tab === 'home' && <VillageDefense onEvacuate={() => setTab('evacuate')} />}
              {tab === 'map' && <CitizenMap user={user ?? {}} />}
              {tab === 'safe' && <SafeRouteScreen user={user ?? {}} />}
              {tab === 'connect' && <MobileCitizen user={user ?? {}} />}
              {tab === 'evacuate' && <Evacuate user={user ?? {}} />}
            </motion.div>
          </AnimatePresence>
        </main>

        {/* bottom nav */}
        <nav className="flex shrink-0 items-stretch gap-1 border-t border-ink-700/60 bg-ink-900 px-2 py-1.5" aria-label="Citizen navigation">
          {TABS.map((t) => {
            const active = tab === t.id
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                aria-current={active ? 'page' : undefined}
                className={clsx(
                  'flex min-w-14 flex-1 flex-col items-center gap-0.5 rounded-md py-1.5 transition-colors',
                  active ? 'bg-accent/15 text-accent-bright' : t.id === 'evacuate' ? 'text-critical/80 hover:text-critical' : 'text-ink-400 hover:text-ink-200',
                )}
              >
                {t.icon}
                <span className="font-mono text-[9px] font-semibold tracking-wider uppercase">{t.label}</span>
              </button>
            )
          })}
        </nav>
      </div>
    </div>
  )
}
