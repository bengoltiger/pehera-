/**
 * Mumbai regional topology panel (Predict / Telemetry map).
 *
 * Replaces the cartoon circular radar with something the operator actually
 * recognises: an OpenStreetMap view of Mumbai with swappable vector layers —
 * wards, rivers, creeks, lakes, salt pans, mangroves, SGNP, chronic flood
 * spots, reclaimed low ground and the transport skeleton.
 *
 * Every layer is served by PEHRA's own /api/map/topology, so the map keeps
 * working offline or behind a firewall: when street tiles are unreachable the
 * panel falls back to a local vector view (district outlines + light frame)
 * and says so. The geometry is hand-drawn demo data and is labelled as such.
 */
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Circle,
  CircleMarker,
  MapContainer,
  Polygon,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'
import { SEVERITY_COLOR, severityFromScore } from '../lib/format'
import type { ThreatCell, TopologyLayer, TopologyResponse } from '../lib/types'
import { useTileAvailability } from './RiskMap'
import { Spinner } from './ui'

/** Catches a map crash (jsdom, a blocked canvas, an offline leaflet) without
 *  taking down the whole Predict screen. */
class MapBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

/** Fits the region once per data identity, only once the map has pixels. */
function FitRegion({ bounds }: { bounds: [number, number, number, number] | null }) {
  const map = useMap()
  const fitted = useRef<string | null>(null)
  const key = bounds ? bounds.join(',') : ''
  useEffect(() => {
    if (!bounds || !key || fitted.current === key) return
    const tryFit = () => {
      const size = map.getSize()
      if (size.x < 2 || size.y < 2) return false
      map.fitBounds(L.latLngBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]]), { padding: [16, 16] })
      fitted.current = key
      return true
    }
    if (tryFit()) return
    const onResize = () => {
      if (tryFit()) map.off('resize', onResize)
    }
    map.on('resize', onResize)
    return () => {
      map.off('resize', onResize)
    }
  }, [bounds, key, map])
  return null
}

/** Light lat/lng frame so the vector basemap still reads as a map. */
function FrameGrid({ bounds }: { bounds: [number, number, number, number] }) {
  const lines: [number, number][][] = []
  for (let lat = Math.ceil(bounds[0] * 5) / 5; lat <= bounds[2]; lat += 0.05) {
    lines.push([[lat, bounds[1]], [lat, bounds[3]]])
  }
  for (let lng = Math.ceil(bounds[1] * 5) / 5; lng <= bounds[3]; lng += 0.05) {
    lines.push([[bounds[0], lng], [bounds[2], lng]])
  }
  return (
    <>
      {lines.map((positions, i) => (
        <Polyline
          key={i}
          positions={positions}
          pathOptions={{ color: '#233040', weight: 1, opacity: 0.7, interactive: false }}
        />
      ))}
    </>
  )
}

/** Renders one layer's features (points, polylines, polygons). */
function LayerGrouping({ layer, color }: { layer: TopologyLayer; color: string }) {
  if (layer.kind === 'point') {
    return (
      <>
        {layer.features.map((f, i) => {
          const p = f as { lat: number; lng: number; name: string; detail?: string }
          return (
            <CircleMarker
              key={i}
              center={[p.lat, p.lng]}
              radius={4}
              pathOptions={{
                color: '#ffffff',
                weight: 1,
                fillColor: color,
                fillOpacity: 0.9,
              }}
            >
              <Tooltip direction="top" offset={[0, -4]} opacity={1}>
                <div className="text-[11px]">
                  <div className="font-semibold text-ink-50">{p.name}</div>
                  {p.detail && <div className="text-ink-400">{p.detail}</div>}
                </div>
              </Tooltip>
            </CircleMarker>
          )
        })}
      </>
    )
  }
  return (
    <>
      {layer.features.map((f, i) => {
        const line = f as { name?: string; detail?: string; coords: [number, number][] }
        if (!line.coords?.length) return null
        const tooltip = line.name ? (
          <Tooltip sticky opacity={1}>
            <div className="text-[11px]">
              <div className="font-semibold text-ink-50">{line.name}</div>
              {line.detail && <div className="text-ink-400">{line.detail}</div>}
            </div>
          </Tooltip>
        ) : null
        return layer.kind === 'polygon' ? (
          <Polygon
            key={i}
            positions={line.coords}
            pathOptions={{ color, weight: 1.5, fillColor: color, fillOpacity: 0.12 }}
          >
            {tooltip}
          </Polygon>
        ) : (
          <Polyline key={i} positions={line.coords} pathOptions={{ color, weight: 2.5, opacity: 0.8 }}>
            {tooltip}
          </Polyline>
        )
      })}
    </>
  )
}

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '© OpenStreetMap contributors'

export function TopologyPanel({
  data,
  threatCells = [],
  className = '',
}: {
  data: TopologyResponse | null
  threatCells?: ThreatCell[]
  className?: string
}) {
  const tileStatus = useTileAvailability(TILE_URL)
  const [catToggles, setCatToggles] = useState<Record<string, boolean>>({})
  const [showThreats, setShowThreats] = useState(false)

  const catIds = useMemo(() => (data ? data.categories.map((c) => c.id).join('|') : ''), [data])
  useEffect(() => {
    if (data) setCatToggles(Object.fromEntries(data.categories.map((c) => [c.id, true])))
  }, [catIds, data])

  const catColor = useMemo(() => {
    const m = new Map<string, string>()
    data?.categories.forEach((c) => m.set(c.id, c.color))
    return m
  }, [data])

  const visibleLayers = useMemo(
    () => (data ? data.layers.filter((l) => catToggles[l.category]) : []),
    [data, catToggles],
  )

  if (!data) {
    return (
      <div className={`grid h-full min-h-72 place-items-center ${className}`}>
        <span className="flex items-center gap-2 font-mono text-xs text-ink-400">
          <Spinner size={14} /> ACQUIRING MUMBAI TOPOLOGY…
        </span>
      </div>
    )
  }

  const bounds = data.region.km_bounds
  const allOn = data.categories.every((c) => catToggles[c.id])
  const activeCount = data.categories.filter((c) => catToggles[c.id]).length

  const mapFallback = (
    <div className="grid h-full min-h-72 place-items-center p-4">
      <div className="max-w-xs rounded-md border border-ink-700 bg-ink-900/80 p-3 text-center">
        <div className="font-mono text-[11px] font-bold text-ink-100">MAP UNAVAILABLE</div>
        <p className="mt-1 text-[11px] leading-relaxed text-ink-400">
          The topology layers are still loaded, but the map canvas could not render here.
        </p>
      </div>
    </div>
  )

  return (
    <div className={`relative overflow-hidden ${className}`}>
      <MapBoundary fallback={mapFallback}>
        <MapContainer
          center={data.region.center}
          zoom={data.region.zoom}
          className="h-full w-full"
          preferCanvas
          zoomControl
          attributionControl={tileStatus === 'available'}
        >
          {tileStatus === 'available' ? (
            <TileLayer url={TILE_URL} attribution={ATTRIBUTION} maxZoom={18} />
          ) : (
            <FrameGrid bounds={bounds} />
          )}

          <FitRegion bounds={bounds} />

          {visibleLayers.map((layer) => (
            <LayerGrouping key={layer.id} layer={layer} color={catColor.get(layer.category) ?? '#8496ae'} />
          ))}

          {showThreats &&
            threatCells.map((cell) => {
              const color = SEVERITY_COLOR[severityFromScore(cell.current_severity)]
              return (
                <Circle
                  key={cell.id}
                  center={[cell.center.lat, cell.center.lng]}
                  radius={Math.max(cell.radius_km * 1000, 1500)}
                  pathOptions={{
                    color,
                    weight: 2,
                    dashArray: '6 4',
                    fillColor: color,
                    fillOpacity: 0.12,
                  }}
                >
                  <Tooltip direction="top" opacity={1}>
                    <div className="text-[11px]">
                      <div className="font-semibold text-ink-50 capitalize">
                        {(cell.hazard_label ?? cell.hazard).replace(/_/g, ' ')} cell
                      </div>
                      <div style={{ color }}>{cell.current_severity.toFixed(0)}/100</div>
                      {cell.movement?.is_moving && cell.movement.speed_kmh != null && (
                        <div className="text-ink-400">
                          {cell.movement.speed_kmh.toFixed(1)} km/h {cell.movement.compass}
                        </div>
                      )}
                    </div>
                  </Tooltip>
                </Circle>
              )
            })}
        </MapContainer>
      </MapBoundary>

      {/* ----------------------------------------------- layer toggles -- */}
      <div className="absolute top-2 left-2 z-[500] flex max-w-[calc(100%-7rem)] flex-wrap items-center gap-1 rounded-md bg-ink-950/85 p-1.5 backdrop-blur-md">
        <button
          type="button"
          onClick={() =>
            setCatToggles(Object.fromEntries(data.categories.map((c) => [c.id, !allOn])))
          }
          className="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold tracking-wider text-ink-100 uppercase hover:bg-ink-800"
        >
          {allOn ? 'ALL' : 'NONE'}
        </button>
        {data.categories.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setCatToggles((prev) => ({ ...prev, [c.id]: !prev[c.id] }))}
            className={`flex items-center gap-1.5 rounded border px-1.5 py-0.5 font-mono text-[10px] tracking-wide uppercase transition-colors ${
              catToggles[c.id]
                ? 'border-ink-600 bg-ink-800 text-ink-100'
                : 'border-ink-700/60 bg-transparent text-ink-500 opacity-60'
            }`}
            title={c.label}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: c.color }} aria-hidden />
            {c.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setShowThreats((v) => !v)}
          className={`flex items-center gap-1.5 rounded border px-1.5 py-0.5 font-mono text-[10px] tracking-wide uppercase transition-colors ${
            showThreats
              ? 'border-critical/60 bg-critical/20 text-critical'
              : 'border-ink-700/60 bg-transparent text-ink-500 opacity-60'
          }`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-critical" aria-hidden />
          Threat cells
        </button>
      </div>

      {/* ---------------------------------------------- honesty footer -- */}
      <div className="pointer-events-none absolute right-2 bottom-1.5 left-2 z-[500] flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5">
        <span className="rounded bg-ink-950/85 px-1.5 py-0.5 font-mono text-[8px] tracking-widest text-ink-400 uppercase backdrop-blur-md">
          Indicative demo geometry · not survey-accurate
        </span>
        {activeCount < data.categories.length && (
          <span className="rounded bg-ink-950/85 px-1.5 py-0.5 font-mono text-[8px] text-ink-400 uppercase backdrop-blur-md">
            {activeCount}/{data.categories.length} categories shown
          </span>
        )}
      </div>
      {tileStatus === 'unavailable' && (
        <div className="pointer-events-none absolute top-2 right-2 z-[500] rounded bg-ink-950/85 px-1.5 py-0.5 font-mono text-[8px] text-moderate uppercase backdrop-blur-md">
          Street tiles unreachable → vector basemap
        </div>
      )}
    </div>
  )
}