/**
 * SafeRoute — hazard-aware navigation (Section 29).
 *
 * The citizen journey's third leg: once the app knows where you are (live GPS
 * or your home ward) it can take you anywhere a hazard does not. This screen
 * plans a route through the RoutingProvider abstraction, lets the user weigh
 * Fastest vs Balanced vs Safest, and listens on the SSE bus for
 * `route.updated` — when conditions change, the app *offers* to re-route
 * rather than silently overriding the user's choice.
 *
 * Honesty: every route payload is labelled SIMULATED; the road layer is a
 * corridor-seeded lattice, not an OSM street map. The map line is the planned
 * geometry; the banner states what kind of data the route is based on.
 */
import { Loader2, Route as RouteIcon, Siren, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { HeroMap } from '../../components/HeroMap'
import type { MapRoute } from '../../components/RiskMap'
import { Chip, SeverityBadge } from '../../components/ui'
import { api } from '../../lib/api'
import { clsx, fmtMinutes, titleCase } from '../../lib/format'
import { useApi } from '../../lib/hooks'
import { useLive } from '../../lib/providers'
import type { LocationSummary, ReRouteResult, RoutePreference, SafeRoute as SafeRouteT, SafeRoutePlan } from '../../lib/types'

type Dest = { id: string; name: string; lat: number; lng: number }

const PREFERENCES: { value: RoutePreference; label: string; hint: string }[] = [
  { value: 'fastest', label: 'Fastest', hint: 'least time' },
  { value: 'balanced', label: 'Balanced', hint: 'time + risk' },
  { value: 'safest', label: 'Safest', hint: 'lowest risk' },
]

function PrefPill({
  pref,
  active,
  onClick,
}: {
  pref: (typeof PREFERENCES)[number]
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'flex flex-1 flex-col items-center gap-0.5 rounded-md border px-2 py-1.5 font-mono text-[10px] font-semibold tracking-wider uppercase transition-colors',
        active
          ? 'border-accent-bright bg-accent/15 text-accent-bright'
          : 'border-ink-600 text-ink-400 hover:border-ink-500 hover:text-ink-200',
      )}
    >
      {pref.label}
      <span className="text-[8px] font-normal tracking-normal normal-case opacity-70">{pref.hint}</span>
    </button>
  )
}

function RouteCard({ route, active }: { route: SafeRouteT; active: boolean }) {
  const riskLevel = route.risk_level
  return (
    <div
      className={clsx(
        'flex flex-col gap-1.5 rounded-lg border p-2.5 transition-colors',
        active ? 'border-accent-bright bg-ink-800' : 'border-ink-600 bg-ink-850',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-mono text-[10px] font-bold tracking-wider text-ink-100 uppercase">
          <RouteIcon size={13} className="text-accent-bright" aria-hidden />
          {titleCase(route.preference)}
        </span>
        <SeverityBadge level={riskLevel} label={riskLevel} score={route.risk_score} size="sm" />
      </div>
      <div className="flex items-center justify-between gap-2 font-mono text-[11px] text-ink-300">
        <span>{(route.distance_m / 1000).toFixed(1)} km</span>
        <span>{fmtMinutes(route.duration_s / 60)}</span>
        <span>{route.confidence.toFixed(0)}% sure</span>
      </div>
      {route.hazard_factors.length > 0 && (
        <p className="text-[10px] leading-snug text-ink-400">
          {route.hazard_factors.map((h) => titleCase(h.label)).join(' · ')}
        </p>
      )}
    </div>
  )
}

export function SafeRouteScreen({ user }: { user: { home_location_id?: string | null } }) {
  const { fix, error: gpsError } = useLiveFixFallback()
  const { subscribe } = useLive()
  const [origin, setOrigin] = useState<Dest | null>(null)
  const [dest, setDest] = useState<Dest | null>(null)
  const [preference, setPreference] = useState<RoutePreference>('balanced')
  const [plan, setPlan] = useState<SafeRoutePlan | null>(null)
  const [routeId, setRouteId] = useState<string | null>(null)
  const [reroute, setReroute] = useState<ReRouteResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const locations = useApi(() => api.locations(), { liveUpdate: false })
  useEffect(() => {
    const list: Dest[] =
      locations.data?.locations.map((l) => ({
        id: l.id,
        name: l.name,
        lat: l.latitude,
        lng: l.longitude,
      })) ?? []
    const home = user?.home_location_id && list.find((l) => l.id === user.home_location_id)
    if (home) setOrigin(home)
    else if (fix) setOrigin({ id: 'live', name: 'Your live location', lat: fix.lat, lng: fix.lng })
    if (!dest && list.length > 0) setDest(list[1] ?? list[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locations.data, user?.home_location_id])

  useEffect(() => {
    if (fix && !origin) setOrigin({ id: 'live', name: 'Your live location', lat: fix.lat, lng: fix.lng })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fix])

  // Re-route offer: the bus tells us the stored route's conditions changed.
  useEffect(() => {
    return subscribe((e) => {
      if (e.type !== 'route.updated') return
      const data = e.data
      if (typeof data.route_id === 'string' && data.route_id === routeId) {
        setReroute(data as unknown as ReRouteResult)
      }
    })
  }, [subscribe, routeId])

  const planRoute = async (pref: RoutePreference) => {
    if (!origin || !dest) {
      setError('Choose both an origin and a destination.')
      return
    }
    setLoading(true)
    setError(null)
    setReroute(null)
    try {
      const resp = await api.planSafeRoute({
        from_lat: origin.lat,
        from_lng: origin.lng,
        to_lat: dest.lat,
        to_lng: dest.lng,
        preference: pref,
      })
      setPlan(resp)
      setRouteId(resp.route_id)
      setPreference(pref)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not plan a route.')
    } finally {
      setLoading(false)
    }
  }

  const doReroute = async () => {
    if (!routeId) return
    setLoading(true)
    try {
      await api.reroute(routeId)
      setError(null)
      setReroute(null)
      await planRoute(preference)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not re-route.')
    } finally {
      setLoading(false)
    }
  }

  const mapRoute: MapRoute | null = useMemo(() => {
    if (!origin || !dest) return null
    return {
      from: [origin.lat, origin.lng],
      to: [dest.lat, dest.lng],
      label: dest.name,
    }
  }, [origin, dest])

  const selected = plan

  return (
    <div className="flex flex-col gap-3 p-3 pb-6">
      <HeroMap className="h-[18rem] rounded-lg" route={mapRoute} fitRoute>
        <div className="pointer-events-none absolute top-2 left-12 z-[500] flex flex-col items-start gap-1">
          <span className="rounded bg-ink-950/90 px-2 py-1 font-mono text-[9px] font-bold text-accent-bright backdrop-blur-md">
            SAFE ROUTE · {origin ? titleCase(origin.name).toUpperCase() : '…'} →{' '}
            {dest ? titleCase(dest.name).toUpperCase() : 'PICK A DESTINATION'}
          </span>
          {plan && (
            <span className="rounded bg-ink-950/90 px-2 py-1 font-mono text-[9px] font-bold text-ink-300 backdrop-blur-md">
              PLAN {titleCase(plan.preference)} · {plan.data_mode.label.toUpperCase()}
            </span>
          )}
        </div>
      </HeroMap>

      {/* origin / destination pickers */}
      {locations.data?.locations && (
        <div className="grid grid-cols-2 gap-2">
          <DestSelect
            label="From"
            value={origin}
            options={locations.data.locations}
            liveFix={fix}
            onChange={setOrigin}
          />
          <DestSelect label="To" value={dest} options={locations.data.locations} onChange={setDest} />
        </div>
      )}
      {gpsError && <p className="font-mono text-[10px] text-critical">{gpsError}</p>}

      {/* preference */}
      <div className="flex gap-1.5">
        {PREFERENCES.map((p) => (
          <PrefPill key={p.value} pref={p} active={preference === p.value} onClick={() => planRoute(p.value)} />
        ))}
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-critical/40 bg-critical/10 p-2 text-[11px] text-critical">
          <TriangleAlert size={14} aria-hidden />
          {error}
        </div>
      )}
      {loading && (
        <div className="flex items-center gap-2 rounded-lg border border-ink-600 bg-ink-800 p-3 font-mono text-[10px] text-ink-300">
          <Loader2 size={14} className="animate-spin" aria-hidden /> SCORING ROUTES AGAINST THE HAZARD FIELD…
        </div>
      )}

      {/* re-route offer */}
      {reroute && (
        <div className="flex flex-col gap-2 rounded-lg border border-critical/50 bg-critical/10 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 font-mono text-[10px] font-bold tracking-wider text-critical uppercase">
              <Siren size={14} aria-hidden /> CONDITIONS CHANGED
            </span>
            <Chip tone="danger">RE-ROUTE SUGGESTED</Chip>
          </div>
          <p className="text-[11px] leading-snug text-ink-200">
            {reroute.risk_reason}. Route risk is now{' '}
            <span className="font-mono text-critical">{reroute.risk_level}</span> (was{' '}
            <span className="font-mono text-ink-300">{reroute.previous_level}</span>).
          </p>
          <button
            type="button"
            onClick={doReroute}
            className="rounded-md bg-critical px-3 py-1.5 font-mono text-[10px] font-bold tracking-wider text-ink-50 uppercase transition-colors hover:bg-critical/80"
          >
            Re-route for me
          </button>
        </div>
      )}

      {/* chosen route + alternatives */}
      {selected && (
        <>
          <div className="flex flex-col gap-1.5">
            <span className="font-mono text-[10px] font-bold tracking-wider text-ink-400 uppercase">Recommended</span>
            <RouteCard route={selected} active />
            <div className="flex flex-col gap-1.5">
              {PREFERENCES.filter((p) => p.value !== selected.preference).map((p) => {
                const alt = plan?.alternatives?.find((a) => a.preference === p.value)
                return alt ? <RouteCard key={p.value} route={alt} active={false} /> : null
              })}
            </div>
          </div>
          {selected.instructions.length > 0 && (
            <div className="rounded-lg border border-ink-600 bg-ink-850 p-3">
              <span className="font-mono text-[10px] font-bold tracking-wider text-ink-400 uppercase">Turn by turn</span>
              <ol className="mt-2 flex flex-col gap-1.5">
                {selected.instructions.map((ins) => (
                  <li key={ins.index} className="flex items-start gap-2 text-[11px] text-ink-200">
                    <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded bg-ink-700 font-mono text-[9px] text-accent-bright">
                      {ins.index + 1}
                    </span>
                    <span>{ins.text}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      )}

      <p className="font-mono text-[9px] leading-snug text-ink-500 uppercase">
        Route road layer is a corridor-derived approximation ({plan?.data_mode.label.toLowerCase() ?? 'no route yet'}).
        Distances follow the planned geometry, not straight-line walking.
      </p>
    </div>
  )
}

function DestSelect({
  label,
  value,
  options,
  onChange,
  liveFix,
}: {
  label: string
  value: Dest | null
  options: LocationSummary[]
  onChange: (d: Dest) => void
  liveFix?: { lat: number; lng: number } | null
}) {
  return (
    <label className="flex flex-col gap-1 rounded-lg border border-ink-600 bg-ink-850 p-2">
      <span className="font-mono text-[9px] font-bold tracking-wider text-ink-400 uppercase">{label}</span>
      <select
        value={value?.id ?? ''}
        onChange={(e) => {
          const id = e.target.value
          if (!id) return
          if (id === 'live' && liveFix) {
            onChange({ id: 'live', name: 'Your live location', lat: liveFix.lat, lng: liveFix.lng })
            return
          }
          const o = options.find((l) => l.id === id)
          if (o) onChange({ id: o.id, name: o.name, lat: o.latitude, lng: o.longitude })
        }}
        className="w-full rounded bg-ink-900 px-1.5 py-1 text-[11px] text-ink-100 outline-none"
      >
        {label === 'From' && liveFix && <option value="live">📡 Your live location</option>}
        {options.map((l) => (
          <option key={l.id} value={l.id}>
            {titleCase(l.name)}
          </option>
        ))}
      </select>
    </label>
  )
}

/** GPS watch with a graceful fallback to the registered zone centre. */
function useLiveFixFallback(): {
  fix: { lat: number; lng: number } | null
  error: string | null
} {
  const [fix, setFix] = useState<{ lat: number; lng: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      setError('Location unavailable — pick an origin manually.')
      return
    }
    const watchId = navigator.geolocation.watchPosition(
      (pos) => setFix({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setError('Could not reach GPS — pick an origin manually.'),
      { enableHighAccuracy: true, maximumAge: 10000 },
    )
    return () => navigator.geolocation.clearWatch(watchId)
  }, [])

  return { fix, error }
}