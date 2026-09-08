/**
 * Threat-cell list (Sections 17, 18).
 *
 * Movement vectors are measured by the backend from the sampled hazard field
 * across ticks. When a cell is too young or too stationary to have a reliable
 * vector, the backend says so and we show that instead of a fake arrow.
 */
import { Circle, MoveRight, Radar } from 'lucide-react'
import { SEVERITY_COLOR, clsx, relativeTime, severityFromScore, titleCase, withAlpha } from '../lib/format'
import type { SeverityKey, ThreatCell } from '../lib/types'
import { EmptyState, SeverityBadge, Unavailable } from './ui'

/** The backend hands us the band key; we never re-derive the thresholds. */
function severityKeyOf(cell: ThreatCell): SeverityKey {
  return (cell.severity_label as SeverityKey) ?? severityFromScore(cell.current_severity)
}

function severityLabelOf(cell: ThreatCell): string {
  return titleCase(String(cell.severity_label ?? severityKeyOf(cell)).toLowerCase())
}

export function ThreatCellList({
  cells,
  onSelect,
  selectedId,
}: {
  cells: ThreatCell[]
  onSelect?: (id: string) => void
  selectedId?: string | null
}) {
  if (!cells || cells.length === 0) {
    return (
      <EmptyState
        icon={<Radar size={24} />}
        title="No threat cells detected"
        detail="A cell appears when the hazard field forms a contiguous area above the detection threshold. Nothing is being tracked right now."
      />
    )
  }

  const sorted = [...cells].sort((a, b) => b.current_severity - a.current_severity)

  return (
    <ul className="divide-y divide-ink-700/40">
      {sorted.map((cell) => {
        const key = severityKeyOf(cell)
        const color = SEVERITY_COLOR[key]
        const speed = cell.movement?.speed_kmh
        const compass = cell.movement?.compass
        const moving = speed !== null && speed !== undefined && speed > 0.3 && compass
        return (
          <li key={cell.id}>
            <button
              type="button"
              onClick={() => onSelect?.(cell.id)}
              className={clsx(
                'w-full px-3 py-2.5 text-left transition-colors',
                selectedId === cell.id ? 'bg-accent/10' : onSelect && 'hover:bg-ink-850/60',
              )}
            >
              <div className="flex items-start gap-2.5">
                <span
                  className="mt-1 grid h-6 w-6 shrink-0 place-items-center rounded-full"
                  style={{ background: withAlpha(color, 0.18), border: `1px solid ${withAlpha(color, 0.5)}` }}
                >
                  <Circle size={9} fill={color} stroke="none" aria-hidden />
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-xs font-semibold text-ink-100 capitalize">
                      {titleCase((cell.hazard_label ?? cell.hazard).replace(/_/g, ' '))}
                    </span>
                    <SeverityBadge level={key} label={severityLabelOf(cell)} score={cell.current_severity} size="sm" showAscii={false} />
                    {cell.status !== 'active' && (
                      <span className="rounded border border-ink-600 px-1 py-0.5 text-[9px] text-ink-400 uppercase">
                        {cell.status}
                      </span>
                    )}
                  </div>

                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-ink-400">
                    {moving ? (
                      <span className="inline-flex items-center gap-1 text-ink-200">
                        <MoveRight
                          size={11}
                          aria-hidden
                          style={{ transform: `rotate(${(cell.movement.bearing_deg ?? 0) - 90}deg)` }}
                        />
                        <span className="font-mono">{speed!.toFixed(1)} km/h</span>
                        <span>{compass}</span>
                      </span>
                    ) : (
                      <Unavailable
                        compact
                        label="movement not measurable"
                        reason={
                          cell.movement?.note ??
                          'Too few tracked positions, or the cell has not moved far enough to measure a direction.'
                        }
                      />
                    )}
                    <span>radius {cell.radius_km.toFixed(1)} km</span>
                    <span>{cell.track?.length ?? 0} track pts</span>
                    <span>conf {cell.confidence.toFixed(0)}%</span>
                  </div>

                  {cell.predicted_severity !== null && cell.predicted_severity !== undefined && (
                    <p className="mt-0.5 text-[11px] text-ink-500">
                      projected {cell.predicted_severity.toFixed(0)}/100 · updated{' '}
                      {relativeTime(cell.last_updated_at)}
                    </p>
                  )}
                </div>
              </div>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
