/**
 * Compact GIS viewport with HUD overlays. Used by the SITREP command screen
 * and the citizen village-defense screen. Fetches its own map layers so pages
 * stay small; `children` are absolutely-positioned HUD elements (badges,
 * chips, telemetry ribbons) exactly like the design's map overlays.
 */
import { useSearchParams } from 'react-router-dom'
import { MapLegend, RiskMap, useTileAvailability, type MapRoute, type MapToggles } from './RiskMap'
import { ErrorBlock, Spinner } from './ui'
import { api } from '../lib/api'
import { useApi } from '../lib/hooks'
import { useEngineConfig } from '../lib/providers'

const HERO_TOGGLES: MapToggles = {
  heat: false,
  zones: true,
  threats: true,
  tracks: true,
  alerts: true,
  infrastructure: true,
  rivers: true,
  labels: true,
}

export function HeroMap({
  children,
  className,
  selectedLocationId,
  onSelectLocation,
  route,
}: {
  children?: React.ReactNode
  className?: string
  selectedLocationId?: string | null
  onSelectLocation?: (id: string) => void
  route?: MapRoute | null
}) {
  const { config } = useEngineConfig()
  const tileUrl = config?.map?.tile_url ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
  const attribution = config?.map?.attribution ?? '© OpenStreetMap contributors'
  const tileStatus = useTileAvailability(tileUrl)
  const layers = useApi(() => api.mapLayers())
  const overview = useApi(() => api.overview())

  return (
    <div className={`relative w-full overflow-hidden border border-ink-600 bg-ink-950 ${className ?? ''}`}>
      {layers.loading && !layers.data ? (
        <div className="grid h-full min-h-64 place-items-center">
          <span className="flex items-center gap-2 font-mono text-xs text-ink-400">
            <Spinner size={14} /> ACQUIRING MAP LAYERS…
          </span>
        </div>
      ) : layers.error ? (
        <div className="grid h-full min-h-64 place-items-center p-4">
          <ErrorBlock error={layers.error} onRetry={layers.reload} />
        </div>
      ) : (
        <div className="h-full min-h-64">
          <RiskMap
            layers={layers.data}
            field={null}
            queue={overview.data?.priority_queue ?? []}
            toggles={HERO_TOGGLES}
            tileStatus={tileStatus}
            tileUrl={tileUrl}
            attribution={attribution}
            selectedLocationId={selectedLocationId}
            onSelectLocation={onSelectLocation}
            route={route}
          />
        </div>
      )}
      <MapLegend tileStatus={tileStatus} />
      {children}
    </div>
  )
}

/** Convenience wrapper for hero maps that track selection in URL params. */
export function HeroMapWithSelection({
  children,
  className,
  paramName = 'location',
}: {
  children?: React.ReactNode
  className?: string
  paramName?: string
}) {
  const [params, setParams] = useSearchParams()
  const selected = params.get(paramName)
  return (
    <HeroMap
      className={className}
      selectedLocationId={selected}
      onSelectLocation={(id) => setParams({ [paramName]: id })}
    >
      {children}
    </HeroMap>
  )
}
