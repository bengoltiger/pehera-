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
import type { MapLayers, PriorityEntry, RiskField } from '../lib/types'

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

function FitBounds({ bounds }: { bounds: L.LatLngBoundsExpression | null }) {
  const map = useMap()
  const done = useRef(false)
  useEffect(() => {
    if (!bounds || done.current) return
    const tryFit = () => {
      // A zero-size container (headless/jsdom, or a not-yet-laid-out panel)
      // makes fitBounds compute a NaN zoom and corrupt every projection, so
      // we only fit once the map actually has pixels to fit into.
      const size = map.getSize()
      if (size.x < 2 || size.y < 2) return false
      map.fitBounds(bounds, { padding: [24, 24] })
      done.current = true
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
  }, [bounds, map])
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
}

/** A journey overlay: user position → destination (nearest shelter). */
export interface MapRoute {
  from: [number, number]
  to: [number, number]
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
}

const INFRA_COLOR: Record<string, string> = {
  hospital: '#e0607e',
  school: '#5aa9e6',
  shelter: '#3fbf8f',
  pumping_station: '#c98a17',
  substation: '#d1600f',
  bridge: '#8496ae',
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
    if (!layers?.zones?.length) return null
    const pts = layers.zones.map((z) => [z.latitude, z.longitude] as [number, number])
    return L.latLngBounds(pts).pad(0.15)
  }, [layers])

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

      <FitBounds bounds={bounds} />
      <MapSizeWatcher />

      {/* ---------------------------------------------- journey route -- */}
      {route && (
        <Pane name="pehra-route" style={{ zIndex: 420 }}>
          <Polyline
            positions={[route.from, route.to]}
            pathOptions={{ color: '#4d9ff0', weight: 4, opacity: 0.9, dashArray: '10 6' }}
          />
          {/* start: the user */}
          <CircleMarker
            center={route.from}
            radius={7}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#4d9ff0', fillOpacity: 1 }}
          >
            <Tooltip direction="top" offset={[0, -8]} opacity={1}>
              <span className="text-[11px] font-semibold text-ink-50">You are here</span>
            </Tooltip>
          </CircleMarker>
          {/* destination: the shelter */}
          <CircleMarker
            center={route.to}
            radius={7}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#3fbf8f', fillOpacity: 1 }}
          >
            <Tooltip direction="top" offset={[0, -8]} opacity={1}>
              <span className="text-[11px] font-semibold text-ink-50">Nearest shelter</span>
            </Tooltip>
          </CircleMarker>
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
