/**
 * Hyperlocal map (Sections 15, 16, 17, 18).
 *
 * Basemap policy: PEHRA tries to load OpenStreetMap raster tiles. If they
 * cannot be reached — offline device, restricted network, sandboxed preview —
 * it does NOT show a broken grey grid. It automatically falls back to a
 * locally drawn basemap built from the seeded ward polygons and river chains,
 * and says so on screen. Every data layer keeps working either way, because
 * the layers are vectors served by our own API.
 */
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Circle,
  CircleMarker,
  MapContainer,
  Marker,
  Pane,
  Polygon,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'
import { SEVERITY_COLOR, fmtPeople, severityFromScore, withAlpha } from '../lib/format'
import type {
  Hospital,
  MapLayers,
  PriorityEntry,
  RiskField,
  Shelter,
  StormState,
  StormTrack,
  TerrainGrid,
  TrafficState,
} from '../lib/types'

export type TileStatus = 'probing' | 'available' | 'unavailable'

/** Probe a single tile so we know whether the basemap can render at all. */
export function useTileAvailability(tileUrl: string): TileStatus {
  const [status, setStatus] = useState<TileStatus>('probing')
  useEffect(() => {
    let done = false
    const probe = tileUrl.replace('{z}', '10').replace('{x}', '739').replace('{y}', '440').replace('{s}', 'a')
    const img = new Image()
    const timer = window.setTimeout(() => {
      if (!done) {
        done = true
        setStatus('unavailable')
      }
    }, 4000)
    img.onload = () => {
      if (done) return
      done = true
      window.clearTimeout(timer)
      setStatus('available')
    }
    img.onerror = () => {
      if (done) return
      done = true
      window.clearTimeout(timer)
      setStatus('unavailable')
    }
    img.src = probe
    return () => {
      done = true
      window.clearTimeout(timer)
    }
  }, [tileUrl])
  return status
}

/** Latitude/longitude graticule drawn locally when there are no tiles. */
function Graticule({ bounds }: { bounds: L.LatLngBoundsExpression }) {
  const b = L.latLngBounds(bounds as L.LatLngBoundsLiteral)
  const lines: [number, number][][] = []
  const step = 0.1
  for (let lat = Math.floor(b.getSouth() * 10) / 10; lat <= b.getNorth(); lat += step) {
    lines.push([
      [lat, b.getWest()],
      [lat, b.getEast()],
    ])
  }
  for (let lng = Math.floor(b.getWest() * 10) / 10; lng <= b.getEast(); lng += step) {
    lines.push([
      [b.getSouth(), lng],
      [b.getNorth(), lng],
    ])
  }
  return (
    <>
      {lines.map((positions, i) => (
        <Polyline
          key={i}
          positions={positions}
          pathOptions={{ color: '#26303e', weight: 1, opacity: 0.6, interactive: false }}
        />
      ))}
    </>
  )
}

/**
 * Fits the view to `bounds`. Fits once per distinct target: re-fetching the
 * same layers (new array identity, same coords) must not fight the user's
 * pan, but a NEW route (e.g. the citizen taps a different ward, or the GPS
 * fix replaces the zone centre) SHOULD re-centre on it.
 */
function FitBounds({ bounds, routeKey }: { bounds: L.LatLngBoundsExpression | null; routeKey?: string }) {
  const map = useMap()
  const fittedFor = useRef<string | null>(null)
  const key = routeKey ?? 'default'
  useEffect(() => {
    if (!bounds || fittedFor.current === key) return
    const tryFit = () => {
      // A zero-size container (headless/jsdom, or a not-yet-laid-out panel)
      // makes fitBounds compute a NaN zoom and corrupt every projection, so
      // we only fit once the map actually has pixels to fit into.
      const size = map.getSize()
      if (size.x < 2 || size.y < 2) return false
      map.fitBounds(bounds, { padding: [24, 24] })
      fittedFor.current = key
      return true
    }
    if (tryFit()) return
    // The container may gain pixels after mount (late layout, a sidebar
    // toggling). Leaflet fires 'resize' from invalidateSize, so retry then
    // — without this the map would stay on its default view forever.
    const onResize = () => {
      if (tryFit()) {
        map.off('resize', onResize)
      }
    }
    map.on('resize', onResize)
    return () => {
      map.off('resize', onResize)
    }
  }, [bounds, key, map])
  return null
}

/**
 * Leaflet's built-in trackResize only watches the WINDOW. When the map's own
 * container resizes (e.g. the detail sidebar on the map screen toggles), the
 * map keeps a stale size and every layer renders offset. Keep it in sync.
 */
function MapSizeWatcher() {
  const map = useMap()
  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return // jsdom / very old browsers
    const el = map.getContainer()
    const ro = new ResizeObserver(() => map.invalidateSize({ pan: false }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [map])
  return null
}

export interface MapToggles {
  heat: boolean
  zones: boolean
  threats: boolean
  tracks: boolean
  infrastructure: boolean
  rivers: boolean
  alerts: boolean
  labels: boolean
  terrain: boolean
  storm: boolean
  traffic: boolean
  assets: boolean
}

/** A journey overlay: user position → destination (nearest shelter). */
export interface MapRoute {
  from: [number, number]
  to: [number, number]
  /** Small always-visible label on the destination (default: "Nearest shelter"). */
  label?: string
}

/** A shelter pin to mark on the map (citizens need every shelter visible). */
export interface ShelterMark {
  id: string
  name: string
  lat: number
  lng: number
  nearest?: boolean
  distanceKm?: number | null
}

export const DEFAULT_TOGGLES: MapToggles = {
  heat: true,
  zones: true,
  threats: true,
  tracks: true,
  infrastructure: false,
  rivers: true,
  alerts: true,
  labels: true,
  terrain: true,
  storm: true,
  traffic: false,
  assets: false,
}

const INFRA_COLOR: Record<string, string> = {
  hospital: '#e0607e',
  school: '#5aa9e6',
  shelter: '#3fbf8f',
  pumping_station: '#c98a17',
  substation: '#d1600f',
  bridge: '#8496ae',
}

/** DEM flood-susceptibility ramp: the blue-er the node, the more likely it is
 *  to hold standing water. This is the spatial input the risk engine leans
 *  on, drawn directly from /api/terrain so map and engine cannot disagree. */
function terrainColor(floodSusceptibility: number): string {
  if (floodSusceptibility >= 0.7) return '#1d4ed8'
  if (floodSusceptibility >= 0.5) return '#3b82f6'
  if (floodSusceptibility >= 0.3) return '#7dd3fc'
  return '#9db2c5'
}

const TRAFFIC_COLOR: Record<string, string> = {
  freeflow: '#22c55e',
  light: '#3b82f6',
  moderate: '#f5b942',
  heavy: '#f97316',
  blocked: '#ef4444',
  unknown: '#8496ae',
}

const SHELTER_COLOR: Record<string, string> = {
  ready: '#3fbf8f',
  at_risk: '#f5b942',
  impacted: '#ef4444',
}

const HOSPITAL_COLOR: Record<string, string> = {
  operational: '#4d9ff0',
  diverting: '#f97316',
  stretched: '#ef4444',
}

export function RiskMap({
  layers,
  field,
  queue,
  toggles,
  tileStatus,
  tileUrl,
  attribution,
  selectedLocationId,
  onSelectLocation,
  selectedCellId,
  onSelectCell,
  route,
  shelters,
  fitRoute = false,
  terrain,
  storm,
  stormTrack,
  traffic,
  responseShelters,
  responseHospitals,
  children,
}: {
  layers: MapLayers | null
  field: RiskField | null
  queue: PriorityEntry[]
  toggles: MapToggles
  tileStatus: TileStatus
  tileUrl: string
  attribution: string
  selectedLocationId?: string | null
  onSelectLocation?: (id: string) => void
  selectedCellId?: string | null
  onSelectCell?: (id: string) => void
  route?: MapRoute | null
  /** Shelters to pin with always-visible labels (nearest one highlighted). */
  shelters?: ShelterMark[]
  /**
   * When a route is given, fit the view to the route instead of the zone
   * layer — a 0.6 km walk is invisible at district zoom, and the citizen's
   * question is "where do I walk?", not "where are all wards?".
   */
  fitRoute?: boolean
  /** DEM/terrain grid for the elevation overlay (Phase G). */
  terrain?: TerrainGrid | null
  /** Active weather system + its short lead track (Phase G). */
  storm?: StormState | null
  stormTrack?: StormTrack | null
  /** Named road corridors derived from the risk field (Phase G). */
  traffic?: TrafficState | null
  /** Response assets with derived readiness/status (Phase G). */
  responseShelters?: Shelter[] | null
  responseHospitals?: Hospital[] | null
  /**
   * Rendered INSIDE the MapContainer — anything passed here may safely use
   * react-leaflet hooks like useMap() (e.g. the WindParticles canvas).
   */
  children?: ReactNode
}) {
  const riskByLocation = useMemo(() => {
    const m = new Map<string, PriorityEntry>()
    for (const q of queue) m.set(q.location_id, q)
    return m
  }, [queue])

  const bounds = useMemo<L.LatLngBoundsExpression | null>(() => {
    if (route && fitRoute) {
      // pad so the endpoints + their labels get breathing room
      return L.latLngBounds([route.from, route.to]).pad(1.4)
    }
    if (!layers?.zones?.length) return null
    const pts = layers.zones.map((z) => [z.latitude, z.longitude] as [number, number])
    return L.latLngBounds(pts).pad(0.15)
  }, [layers, route, fitRoute])

  const center: [number, number] = [18.52, 73.86]

  return (
    <MapContainer
      center={center}
      zoom={10}
      className="h-full w-full"
      preferCanvas
      zoomControl
      attributionControl={tileStatus === 'available'}
    >
      {tileStatus === 'available' ? (
        <TileLayer url={tileUrl} attribution={attribution} maxZoom={18} />
      ) : (
        bounds && <Graticule bounds={bounds} />
      )}

      <FitBounds
        bounds={bounds}
        routeKey={
          route
            ? `route:${route.from[0].toFixed(4)},${route.from[1].toFixed(4)},${route.to[0].toFixed(4)},${route.to[1].toFixed(4)}`
            : undefined
        }
      />
      <MapSizeWatcher />

      {/* ---------------------------------------------- journey route -- */}
      {route && (
        <Pane name="pehra-route" style={{ zIndex: 420 }}>
          {/* the blue line: exactly where to walk */}
          <Polyline
            positions={[route.from, route.to]}
            pathOptions={{ color: '#4d9ff0', weight: 5, opacity: 0.95, dashArray: '12 7' }}
          />
          {/* start: the user */}
          <CircleMarker
            center={route.from}
            radius={8}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#4d9ff0', fillOpacity: 1 }}
          >
            <Tooltip direction="top" offset={[0, -10]} opacity={1}>
              <span className="text-[11px] font-semibold text-ink-50">You are here</span>
            </Tooltip>
          </CircleMarker>
          {/* destination: the shelter */}
          <CircleMarker
            center={route.to}
            radius={8}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#3fbf8f', fillOpacity: 1 }}
          >
            <Tooltip direction="top" offset={[0, -10]} opacity={1}>
              <span className="text-[11px] font-semibold text-ink-50">Nearest shelter</span>
            </Tooltip>
          </CircleMarker>
          {/* always-visible labels so a non-technical user reads the route
              without hovering or zooming */}
          <Marker
            position={route.from}
            interactive={false}
            icon={L.divIcon({
              className: '',
              html: `<div style="transform:translate(-50%,10px);white-space:nowrap;font:700 10px/1 Inter,system-ui,sans-serif;color:#dbeafe;background:rgba(10,20,35,.85);border:1px solid #4d9ff0;border-radius:8px;padding:2px 6px;pointer-events:none">YOU ARE HERE</div>`,
            })}
          />
          <Marker
            position={route.to}
            interactive={false}
            icon={L.divIcon({
              className: '',
              html: `<div style="transform:translate(-50%,-16px);white-space:nowrap;font:700 10px/1 Inter,system-ui,sans-serif;color:#04150d;background:#3fbf8f;border:1px solid rgba(255,255,255,.4);border-radius:8px;padding:2px 6px;pointer-events:none">${route.label ?? 'NEAREST SHELTER'}</div>`,
            })}
          />
        </Pane>
      )}

      {/* ------------------------------------------- shelter markers -- */}
      {shelters && shelters.length > 0 && (
        <Pane name="pehra-shelters" style={{ zIndex: 430 }}>
          {shelters.map((s) => (
            <Marker
              key={s.id}
              position={[s.lat, s.lng]}
              icon={L.divIcon({
                className: '',
                html: `<div style="display:flex;flex-direction:column;align-items:center;transform:translate(-50%,-100%);pointer-events:none">
                  <div style="white-space:nowrap;font:700 10px/1.2 Inter,system-ui,sans-serif;color:${s.nearest ? '#04150d' : '#d1fae5'};background:${s.nearest ? '#3fbf8f' : 'rgba(8,46,34,.92)'};border:1.5px solid ${s.nearest ? 'rgba(255,255,255,.55)' : '#3fbf8f'};border-radius:10px;padding:3px 7px;box-shadow:0 1px 5px rgba(0,0,0,.5)">${s.nearest ? '★ NEAREST · ' : ''}${s.name.toUpperCase()}</div>
                  <div style="width:2px;height:9px;background:#3fbf8f"></div>
                </div>`,
              })}
            >
              <Tooltip direction="top" offset={[0, -14]} opacity={1}>
                <div className="text-[11px]">
                  <div className="font-semibold text-ink-50">{s.name}</div>
                  {s.distanceKm != null && (
                    <div className="text-ink-400">
                      {s.distanceKm.toFixed(1)} km away
                      {s.nearest ? ' · walk this blue line' : ''}
                    </div>
                  )}
                </div>
              </Tooltip>
            </Marker>
          ))}
        </Pane>
      )}

      {/* -------------------------------------------------- heat field -- */}
      {toggles.heat && field && (
        <Pane name="pehra-field" style={{ zIndex: 320 }}>
          {field.points.map((p, i) => {
            const key = severityFromScore(p.severity)
            return (
              <CircleMarker
                key={i}
                center={[p.lat, p.lng]}
                radius={7}
                pathOptions={{
                  color: 'transparent',
                  fillColor: SEVERITY_COLOR[key],
                  fillOpacity: 0.1 + Math.min(0.45, p.severity / 220),
                  interactive: false,
                }}
              />
            )
          })}
        </Pane>
      )}

      {/* ------------------------------------------- DEM/terrain layer -- */}
      {toggles.terrain && terrain && terrain.points.length > 0 && (
        <Pane name="pehra-terrain" style={{ zIndex: 310 }}>
          {terrain.points.map((p, i) => (
            <CircleMarker
              key={i}
              center={[p.lat, p.lng]}
              radius={3}
              pathOptions={{
                color: 'transparent',
                fillColor: terrainColor(p.flood_susceptibility),
                fillOpacity: 0.4,
                weight: 0,
                interactive: false,
              }}
            />
          ))}
        </Pane>
      )}

      {/* ---------------------------------------- storm system + track -- */}
      {toggles.storm && storm?.system && (
        <Pane name="pehra-storm" style={{ zIndex: 425 }}>
          {storm.track.length > 1 && (
            <Polyline
              positions={storm.track.map((p) => [p.lat, p.lng] as [number, number])}
              pathOptions={{ color: '#7c3aed', weight: 3, opacity: 0.9, dashArray: '8 5' }}
            />
          )}
          {stormTrack && stormTrack.points.length > 1 && (
            <Polyline
              positions={stormTrack.points.map((p) => [p.lat, p.lng] as [number, number])}
              pathOptions={{ color: '#9f7aea', weight: 1.5, opacity: 0.5, dashArray: '2 6' }}
            />
          )}
          {storm.system.active && (
            <>
              <Circle
                center={[storm.system.latitude, storm.system.longitude]}
                radius={Math.max(storm.system.radius_km * 1000, 4000)}
                pathOptions={{
                  color: '#7c3aed',
                  weight: 1.5,
                  fillColor: '#7c3aed',
                  fillOpacity: 0.06,
                  dashArray: '4 6',
                }}
              >
                <Tooltip direction="top" opacity={1}>
                  <div className="text-[11px]">
                    <div className="font-semibold text-ink-50">{storm.system.name}</div>
                    <div className="text-ink-300">{storm.system.type}</div>
                    <div className="text-ink-400">
                      winds {storm.intensity.wind_speed_kmh.toFixed(0)} km/h · surge{' '}
                      {storm.intensity.surge_m.toFixed(2)} m · {storm.intensity.trend_3h}
                    </div>
                  </div>
                </Tooltip>
              </Circle>
              <CircleMarker
                center={[storm.system.latitude, storm.system.longitude]}
                radius={7}
                pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#7c3aed', fillOpacity: 1 }}
              />
            </>
          )}
          {storm.system.bearing_deg != null && storm.system.speed_kmh != null && (
            <CircleMarker
              center={[storm.system.latitude, storm.system.longitude]}
              radius={2}
              pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#ffffff', fillOpacity: 1 }}
            />
          )}
        </Pane>
      )}

      {/* ------------------------------------------------------ rivers -- */}
      {toggles.rivers &&
        layers?.rivers?.map((r) =>
          r.points.length > 1 ? (
            <Polyline
              key={r.id}
              positions={r.points.map((p) => [p.lat, p.lng] as [number, number])}
              pathOptions={{ color: '#3f7fbf', weight: 2.5, opacity: 0.65, dashArray: '1 0' }}
            >
              <Tooltip sticky>{r.id.replace(/_/g, ' ')}</Tooltip>
            </Polyline>
          ) : null,
        )}

      {/* ------------------------------------------------------- zones -- */}
      {toggles.zones &&
        layers?.zones?.map((z) => {
          const entry = riskByLocation.get(z.id)
          const color = entry ? entry.severity.color : '#38455a'
          const selected = selectedLocationId === z.id
          const positions = (z.polygon ?? []) as [number, number][]
          const common = {
            color: selected ? '#4d9ff0' : color,
            weight: selected ? 2.5 : 1.4,
            fillColor: color,
            fillOpacity: entry ? 0.18 + Math.min(0.3, entry.risk / 320) : 0.06,
          }
          const label = (
            <Tooltip direction="top" offset={[0, -6]} opacity={1}>
              <div className="text-[11px]">
                <div className="font-semibold text-ink-50">{z.name}</div>
                {entry ? (
                  <>
                    <div style={{ color }}>
                      {entry.severity.label} · {entry.risk.toFixed(0)}/100 {entry.momentum.arrow}
                    </div>
                    <div className="text-ink-400">
                      {entry.hazard_label} · {fmtPeople(entry.exposed_population)} exposed
                    </div>
                  </>
                ) : (
                  <div className="text-ink-400">No prediction yet</div>
                )}
              </div>
            </Tooltip>
          )
          return positions.length >= 3 ? (
            <Polygon
              key={z.id}
              positions={positions}
              pathOptions={common}
              eventHandlers={{ click: () => onSelectLocation?.(z.id) }}
            >
              {label}
            </Polygon>
          ) : (
            <CircleMarker
              key={z.id}
              center={[z.latitude, z.longitude]}
              radius={10}
              pathOptions={common}
              eventHandlers={{ click: () => onSelectLocation?.(z.id) }}
            >
              {label}
            </CircleMarker>
          )
        })}

      {/* ------------------------------------------------ threat cells -- */}
      {toggles.threats &&
        layers?.threat_cells?.map((cell) => {
          const key = severityFromScore(cell.current_severity)
          const color = SEVERITY_COLOR[key]
          const selected = selectedCellId === cell.id
          return (
            <Circle
              key={cell.id}
              center={[cell.center.lat, cell.center.lng]}
              radius={cell.radius_km * 1000}
              pathOptions={{
                color,
                weight: selected ? 3 : 2,
                dashArray: '6 4',
                fillColor: color,
                fillOpacity: 0.12,
              }}
              eventHandlers={{ click: () => onSelectCell?.(cell.id) }}
            >
              <Tooltip direction="top" opacity={1}>
                <div className="text-[11px]">
                  <div className="font-semibold text-ink-50 capitalize">
                    {(cell.hazard_label ?? cell.hazard).replace(/_/g, ' ')} cell
                  </div>
                  <div style={{ color }}>{cell.current_severity.toFixed(0)}/100</div>
                  <div className="text-ink-400">
                    {cell.movement?.is_moving && cell.movement.speed_kmh
                      ? `${cell.movement.speed_kmh.toFixed(1)} km/h ${cell.movement.compass}`
                      : (cell.movement?.note ?? 'movement not measurable yet')}
                  </div>
                </div>
              </Tooltip>
            </Circle>
          )
        })}

      {/* ---------------------------------------------- movement track -- */}
      {toggles.tracks &&
        layers?.threat_cells?.map((cell) => {
          const key = severityFromScore(cell.current_severity)
          const color = SEVERITY_COLOR[key]
          const past = (cell.track ?? []).map((p) => [p.lat, p.lng] as [number, number])
          const future = (cell.predicted_track ?? []).map((p) => [p.lat, p.lng] as [number, number])
          return (
            <div key={`${cell.id}-track`}>
              {past.length > 1 && (
                <Polyline positions={past} pathOptions={{ color, weight: 2, opacity: 0.85 }} />
              )}
              {future.length > 0 && (
                <Polyline
                  positions={[[cell.center.lat, cell.center.lng], ...future]}
                  pathOptions={{ color, weight: 2, opacity: 0.55, dashArray: '3 6' }}
                />
              )}
              {future.map((p, i) => (
                <CircleMarker
                  key={i}
                  center={p}
                  radius={2.5}
                  pathOptions={{ color, fillColor: color, fillOpacity: 0.8 }}
                />
              ))}
            </div>
          )
        })}

      {/* -------------------------------------------------- traffic -- */}
      {toggles.traffic && traffic && traffic.corridors.length > 0 && (
        <Pane name="pehra-traffic" style={{ zIndex: 415 }}>
          {traffic.corridors.map((c) => (
            <Polyline
              key={c.id}
              positions={[
                [c.from.lat, c.from.lng],
                [c.to.lat, c.to.lng],
              ]}
              pathOptions={{
                color: TRAFFIC_COLOR[c.status] ?? '#8496ae',
                weight: c.status === 'blocked' ? 6 : 4,
                opacity: 0.9,
              }}
            >
              <Tooltip sticky opacity={1}>
                <div className="text-[11px]">
                  <div className="font-medium text-ink-50">{c.name}</div>
                  <div className="capitalize text-ink-300">
                    {c.status} · {c.congestion.toFixed(0)}/100 congested
                  </div>
                  <div className="text-ink-400">
                    {c.speed_kmh} km/h{c.bound_ward_risk != null ? ` · ward ${c.bound_ward_risk.toFixed(0)}/100` : ''}
                  </div>
                </div>
              </Tooltip>
            </Polyline>
          ))}
        </Pane>
      )}

      {/* ------------------------------------------------ alert fences -- */}
      {toggles.alerts &&
        layers?.alerts?.map((a) => {
          const g = a.geofence as { lat?: number; lng?: number; radius_km?: number }
          if (!g?.lat || !g?.lng) return null
          const color = a.level === 'CRITICAL' ? '#b3161c' : a.level === 'WARNING' ? '#d1600f' : '#c98a17'
          return (
            <Circle
              key={a.id}
              center={[g.lat, g.lng]}
              radius={(g.radius_km ?? 6) * 1000}
              pathOptions={{ color, weight: 1.5, fillOpacity: 0.04, dashArray: '2 5' }}
            >
              <Tooltip direction="top" opacity={1}>
                <div className="text-[11px]">
                  <span style={{ color }} className="font-semibold">
                    {a.level}
                  </span>{' '}
                  — {a.title}
                </div>
              </Tooltip>
            </Circle>
          )
        })}

      {/* ---------------------------------------------- infrastructure -- */}
      {toggles.infrastructure &&
        layers?.infrastructure?.map((inf) => (
          <CircleMarker
            key={inf.id}
            center={[inf.lat, inf.lng]}
            radius={3.5}
            pathOptions={{
              color: INFRA_COLOR[inf.kind] ?? '#8496ae',
              fillColor: INFRA_COLOR[inf.kind] ?? '#8496ae',
              fillOpacity: 0.9,
              weight: 1,
            }}
          >
            <Tooltip direction="top" opacity={1}>
              <div className="text-[11px]">
                <div className="font-medium text-ink-50">{inf.name}</div>
                <div className="text-ink-400 capitalize">
                  {inf.kind.replace(/_/g, ' ')} · {inf.criticality}
                </div>
              </div>
            </Tooltip>
          </CircleMarker>
        ))}

      {/* ---------------------------------- response assets (Phase G) -- */}
      {toggles.assets && (
        <Pane name="pehra-assets" style={{ zIndex: 432 }}>
          {responseShelters?.map((s) => (
            <CircleMarker
              key={`s-${s.id}`}
              center={[s.latitude, s.longitude]}
              radius={6}
              pathOptions={{
                color: '#ffffff',
                weight: 1.5,
                fillColor: SHELTER_COLOR[s.readiness] ?? '#8496ae',
                fillOpacity: 0.95,
              }}
            >
              <Tooltip direction="top" opacity={1}>
                <div className="text-[11px]">
                  <div className="font-semibold text-ink-50">{s.name}</div>
                  <div className="capitalize text-ink-300">
                    shelter · {s.readiness.replace(/_/g, ' ')}
                  </div>
                  <div className="text-ink-400">
                    {s.capacity ? `${s.capacity} capacity` : 'capacity unknown'}
                    {s.host_ward_risk != null && s.host_ward_risk >= 60
                      ? ` · ward ${s.host_ward_risk.toFixed(0)}/100`
                      : ''}
                  </div>
                </div>
              </Tooltip>
            </CircleMarker>
          ))}
          {responseHospitals?.map((h) => (
            <CircleMarker
              key={`h-${h.id}`}
              center={[h.latitude, h.longitude]}
              radius={5}
              pathOptions={{
                color: '#ffffff',
                weight: 1.5,
                fillColor: HOSPITAL_COLOR[h.status] ?? '#4d9ff0',
                fillOpacity: 0.95,
              }}
            >
              <Tooltip direction="top" opacity={1}>
                <div className="text-[11px]">
                  <div className="font-semibold text-ink-50">{h.name}</div>
                  <div className="capitalize text-ink-300">
                    hospital · {h.status}
                    {h.beds ? ` · ${h.beds} beds` : ''}
                  </div>
                  {h.host_ward_risk != null && h.host_ward_risk >= 60 && (
                    <div className="text-ink-400">ward {h.host_ward_risk.toFixed(0)}/100</div>
                  )}
                </div>
              </Tooltip>
            </CircleMarker>
          ))}
        </Pane>
      )}

      {/* ------------------------------------------------------ labels -- */}
      {toggles.labels &&
        layers?.zones?.map((z) => {
          const entry = riskByLocation.get(z.id)
          const color = entry ? entry.severity.color : '#8496ae'
          return (
            <Marker
              key={`${z.id}-label`}
              position={[z.latitude, z.longitude]}
              interactive={false}
              icon={L.divIcon({
                className: '',
                html: `<div style="
                    transform:translate(-50%,-50%);
                    white-space:nowrap;
                    font:600 10px/1.2 Inter,system-ui,sans-serif;
                    color:#e9eff5;
                    text-shadow:0 1px 3px #000,0 0 6px #000;
                    pointer-events:none;">
                    ${z.name.replace(/ (Ward|Village|Town)$/, '')}
                    ${entry ? `<span style="color:${color}"> ${entry.risk.toFixed(0)}</span>` : ''}
                  </div>`,
              })}
            />
          )
        })}

      {/* ------------------------------------------------- inner overlays -- */}
      {children}
    </MapContainer>
  )
}

export function MapLegend({ tileStatus }: { tileStatus: TileStatus }) {
  return (
    <div className="pointer-events-none absolute bottom-3 left-3 z-[500] rounded-lg border border-ink-600 bg-ink-950/90 px-2.5 py-2 backdrop-blur">
      <div className="mb-1 text-[9px] font-semibold tracking-wide text-ink-500 uppercase">Risk level</div>
      <ul className="space-y-0.5">
        {(['SAFE', 'LOW', 'MODERATE', 'HIGH', 'CRITICAL'] as const).map((k) => (
          <li key={k} className="flex items-center gap-1.5 text-[10px] text-ink-300">
            <span
              className="h-2.5 w-4 rounded-sm border"
              style={{ background: withAlpha(SEVERITY_COLOR[k], 0.4), borderColor: SEVERITY_COLOR[k] }}
              aria-hidden
            />
            {k[0] + k.slice(1).toLowerCase()}
          </li>
        ))}
      </ul>
      {tileStatus === 'unavailable' && (
        <p className="mt-1.5 max-w-[13rem] border-t border-ink-700 pt-1.5 text-[9px] leading-snug text-moderate">
          Street tiles unreachable — showing PEHRA's own vector basemap. All risk layers are
          unaffected.
        </p>
      )}
    </div>
  )
}
