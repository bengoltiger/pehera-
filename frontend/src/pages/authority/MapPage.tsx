import { Layers, Map as MapIcon, PanelRightClose, PanelRightOpen } from 'lucide-react'
import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Popup, useMapEvents } from 'react-leaflet'
import { RiskDetail } from '../../components/RiskDetail'
import { DEFAULT_TOGGLES, MapLegend, RiskMap, useTileAvailability, type MapToggles } from '../../components/RiskMap'
import { ThreatCellList } from '../../components/ThreatCells'
import { Button, Chip, ErrorBlock, LoadingBlock, Panel, Spinner, StaleNotice, Toggle } from '../../components/ui'
import { api, PehraError } from '../../lib/api'
import { clsx, SEVERITY_COLOR, severityFromScore, titleCase } from '../../lib/format'
import { useApi, useLocalState } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'
import { useEngineConfig } from '../../lib/providers'
import type { RiskCell } from '../../lib/types'

const TOGGLE_LABELS: { key: keyof MapToggles; label: string; hint: string }[] = [
  { key: 'heat', label: 'Risk field', hint: 'Interpolated severity surface between wards' },
  { key: 'terrain', label: 'Terrain / DEM', hint: 'Elevation & flood-susceptibility grid' },
  { key: 'zones', label: 'Ward risk', hint: 'Ward polygons shaded by current risk' },
  { key: 'threats', label: 'Threat cells', hint: 'Detected storm / flood cells' },
  { key: 'tracks', label: 'Movement tracks', hint: 'Past path and projected path of each cell' },
  { key: 'storm', label: 'Storm system', hint: 'Forcing system position + track' },
  { key: 'traffic', label: 'Traffic state', hint: 'Corridors derived from the risk field' },
  { key: 'assets', label: 'Response assets', hint: 'Shelter readiness + hospital status' },
  { key: 'alerts', label: 'Alert geofences', hint: 'Radius of active alerts' },
  { key: 'infrastructure', label: 'Infrastructure', hint: 'Hospitals, schools, shelters, utilities' },
  { key: 'rivers', label: 'Rivers', hint: 'Seeded river chains' },
  { key: 'labels', label: 'Labels', hint: 'Ward names and scores' },
]

export default function MapPage() {
  const { lang } = useI18n()
  const { config } = useEngineConfig()
  const [params, setParams] = useSearchParams()
  const selected = params.get('location')
  const [selectedCell, setSelectedCell] = useState<string | null>(null)
  const [toggles, setToggles] = useLocalState<MapToggles>('pehra.map.toggles', DEFAULT_TOGGLES)
  const [sidebar, setSidebar] = useState(true)
  const [layersOpen, setLayersOpen] = useState(false)

  const tileUrl = config?.map?.tile_url ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
  const attribution = config?.map?.attribution ?? '© OpenStreetMap contributors'
  const tileStatus = useTileAvailability(tileUrl)

  const layers = useApi(() => api.mapLayers())
  const field = useApi(() => api.mapField({ step_deg: 0.02, min_severity: 8 }), { enabled: toggles.heat })
  const terrain = useApi(() => api.terrain({ step_deg: 0.012 }), { enabled: toggles.terrain })
  const storm = useApi(() => api.storm({ lead_ticks: 8 }), { enabled: toggles.storm })
  const stormTrack = useApi(() => api.stormTrack(), { enabled: toggles.storm })
  const traffic = useApi(() => api.traffic(), { enabled: toggles.traffic })
  const shelters = useApi(() => api.shelters(), { enabled: toggles.assets })
  const hospitals = useApi(() => api.hospitals(), { enabled: toggles.assets })
  const overview = useApi(() => api.overview())
  const risk = useApi((s) => api.risk(selected!, { detail: true, lang }, s), {
    enabled: !!selected,
    deps: [selected, lang],
  })

  const set = (k: keyof MapToggles) => (v: boolean) => setToggles({ ...toggles, [k]: v })

  return (
    <div className="relative flex h-full min-h-[32rem] flex-col lg:flex-row">
      {/* ---------------------------------------------------------- map -- */}
      <div className="relative min-h-[24rem] flex-1">
        {layers.loading && !layers.data ? (
          <div className="grid h-full place-items-center bg-ink-900">
            <span className="flex items-center gap-2 text-xs text-ink-400">
              <Spinner size={14} /> Loading map layers…
            </span>
          </div>
        ) : layers.error ? (
          <div className="grid h-full place-items-center p-6">
            <ErrorBlock error={layers.error} onRetry={layers.reload} />
          </div>
        ) : (
          <RiskMap
            layers={layers.data}
            field={toggles.heat ? field.data : null}
            queue={overview.data?.priority_queue ?? []}
            toggles={toggles}
            tileStatus={tileStatus}
            tileUrl={tileUrl}
            attribution={attribution}
            selectedLocationId={selected}
            onSelectLocation={(id) => setParams({ location: id })}
            selectedCellId={selectedCell}
            onSelectCell={setSelectedCell}
            terrain={toggles.terrain ? terrain.data : null}
            storm={toggles.storm ? storm.data : null}
            stormTrack={toggles.storm ? stormTrack.data : null}
            traffic={toggles.traffic ? traffic.data : null}
            responseShelters={toggles.assets ? shelters.data?.shelters ?? null : null}
            responseHospitals={toggles.assets ? hospitals.data?.hospitals ?? null : null}
          >
            <CellProbe />
          </RiskMap>
        )}

        <MapLegend tileStatus={tileStatus} />

        {/* layer control */}
        <div className="absolute top-3 right-3 z-[500] w-56">
          <button
            type="button"
            onClick={() => setLayersOpen((o) => !o)}
            className="flex w-full items-center gap-1.5 rounded-lg border border-ink-600 bg-ink-950/90 px-2.5 py-1.5 text-[11px] font-medium text-ink-200 backdrop-blur hover:bg-ink-850"
            aria-expanded={layersOpen}
          >
            <Layers size={13} /> Layers
            <span className="ml-auto font-mono text-[10px] text-ink-500">
              {Object.values(toggles).filter(Boolean).length}/{TOGGLE_LABELS.length}
            </span>
          </button>
          {layersOpen && (
            <div className="mt-1 space-y-1.5 rounded-lg border border-ink-600 bg-ink-950/95 p-2.5 backdrop-blur">
              {TOGGLE_LABELS.map((t) => (
                <Toggle
                  key={t.key}
                  checked={toggles[t.key]}
                  onChange={set(t.key)}
                  label={t.label}
                  description={t.hint}
                />
              ))}
              <p className="border-t border-ink-700 pt-1.5 text-[9px] leading-snug text-ink-500">
                Basemap:{' '}
                {tileStatus === 'probing'
                  ? 'checking tile server…'
                  : tileStatus === 'available'
                    ? 'OpenStreetMap raster tiles'
                    : 'local vector fallback (tiles unreachable)'}
              </p>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={() => setSidebar((s) => !s)}
          className="absolute top-3 right-[15.5rem] z-[500] hidden rounded-lg border border-ink-600 bg-ink-950/90 p-1.5 text-ink-300 backdrop-blur hover:bg-ink-850 lg:block"
          title={sidebar ? 'Hide detail panel' : 'Show detail panel'}
        >
          {sidebar ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
        </button>
      </div>

      {/* ------------------------------------------------------ sidebar -- */}
      <aside
        className={clsx(
          'min-h-0 shrink-0 overflow-y-auto border-ink-700/60 bg-ink-900/60 lg:border-l',
          sidebar ? 'lg:w-[28rem]' : 'lg:w-0 lg:overflow-hidden lg:border-l-0',
        )}
      >
        <div className="space-y-3 p-3">
          <StaleNotice stale={layers.stale || overview.stale} />

          {!selected ? (
            <Panel title="Hyperlocal map" icon={<MapIcon size={14} className="text-ink-400" />}>
              <p className="text-xs leading-relaxed text-ink-300">
                Click any ward to open its full assessment: two-dimensional risk, ranked
                contributions, confidence breakdown and the prediction timeline. Click empty
                map space to probe the DEM hazard field at that exact cell.
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Chip tone="sim">{layers.data?.data_origin ?? 'simulated'}</Chip>
                {field.data && <Chip tone="neutral">{field.data.count} field points</Chip>}
                {terrain.data && <Chip tone="neutral">{terrain.data.count} terrain nodes</Chip>}
                {storm.data?.system.active && <Chip tone="warn">{storm.data.system.type}</Chip>}
                {tileStatus === 'unavailable' && <Chip tone="warn">vector basemap</Chip>}
              </div>
              {field.data?.note && (
                <p className="mt-2 text-[10px] leading-snug text-ink-500">{field.data.note}</p>
              )}
            </Panel>
          ) : risk.loading && !risk.data ? (
            <LoadingBlock rows={6} />
          ) : risk.data ? (
            <>
              <Button size="sm" variant="ghost" onClick={() => setParams({})}>
                ← Back to overview
              </Button>
              <RiskDetail risk={risk.data} compact />
            </>
          ) : (
            <ErrorBlock error={risk.error} onRetry={risk.reload} />
          )}

          <Panel title="Threat cells" subtitle="Tracked, moving hazard objects" dense>
            <ThreatCellList
              cells={layers.data?.threat_cells ?? []}
              selectedId={selectedCell}
              onSelect={setSelectedCell}
            />
          </Panel>
        </div>
      </aside>
    </div>
  )
}

/**
 * Click-to-probe the DEM hazard field at any cell (GET /api/risk/cell).
 * Clicking empty map space shows the hazard breakdown for that exact point;
 * clicking a ward keeps selecting the ward (vector layers stop the event).
 */
function CellProbe() {
  const [cell, setCell] = useState<RiskCell | null>(null)
  const [pos, setPos] = useState<[number, number] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [probing, setProbing] = useState<string | null>(null)
  const pending = useRef(false)

  useMapEvents({
    click: (e) => {
      if (pending.current) return
      pending.current = true
      const { lat, lng } = e.latlng
      setProbing('…')
      api
        .riskCell(lat, lng)
        .then((c) => {
          setCell(c)
          setPos([c.lat, c.lng])
          setError(null)
        })
        .catch((err) => {
          setError(err instanceof PehraError ? err.payload?.message ?? err.message : 'Cannot probe this cell.')
          setCell(null)
          setPos([lat, lng])
        })
        .finally(() => {
          pending.current = false
          setProbing(null)
        })
    },
  })

  return (
    <>
      {pos && (
        <Popup
          position={pos}
          eventHandlers={{
            popupclose: () => {
              setCell(null)
              setPos(null)
              setError(null)
            },
          }}
        >
          {error ? (
            <div className="text-[11px] text-critical">{error}</div>
          ) : !cell ? (
            <div className="flex items-center gap-2 text-[11px] text-ink-400">
              {probing && <Spinner size={12} />} Probing this cell…
            </div>
          ) : (
            <div className="w-56 space-y-1.5 text-[11px]">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold capitalize text-ink-50">
                  {titleCase(cell.dominant_hazard.replace(/_/g, ' '))} cell
                </span>
                <span
                  className="rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wide"
                  style={{
                    color: '#0b1220',
                    background: cell.severity_band.color,
                  }}
                >
                  {cell.severity_band.label}
                </span>
              </div>
              <div className="text-ink-400">{cell.severity.toFixed(0)}/100 hazard severity</div>
              <div className="space-y-1">
                {cell.hazard_breakdown.slice(0, 5).map((h) => {
                  const color = SEVERITY_COLOR[severityFromScore(h.severity)]
                  return (
                    <div key={h.hazard} className="flex items-center gap-2">
                      <span className="w-24 shrink-0 truncate text-ink-300">{h.label}</span>
                      <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-ink-800">
                        <div className="h-full rounded-full" style={{ width: `${h.severity}%`, background: color }} />
                      </div>
                      <span className="w-8 shrink-0 text-right font-mono text-[10px] text-ink-300">
                        {h.severity.toFixed(0)}
                      </span>
                    </div>
                  )
                })}
              </div>
              {cell.nearest_location && (
                <div className="text-[10px] text-ink-500">
                  nearest ward: {cell.nearest_location.name}
                  {cell.nearest_location.distance_km != null ? ` (${cell.nearest_location.distance_km} km)` : ''}
                </div>
              )}
              {cell.interpolated && (
                <div className="text-[10px] text-ink-500">static terrain inputs interpolated (IDW)</div>
              )}
              <div className="border-t border-ink-700 pt-1 text-[9px] text-ink-500">
                Hazard-only estimate — exposure not applied.
              </div>
            </div>
          )}
        </Popup>
      )}
    </>
  )
}
