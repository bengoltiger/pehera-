/**
 * Tactical radar viewport: a canvas-style SVG rendering of the LIVE threat
 * cells returned by the engine (position, radius, severity, movement vector,
 * projected track). No decoration is presented as data — the sweep and grid
 * are explicitly a display device, and every plotted object is a real
 * tracked cell from /api/threats.
 */
import { motion } from 'framer-motion'
import { useMemo } from 'react'
import { SEVERITY_COLOR } from '../lib/format'
import type { SeverityKey, ThreatCell } from '../lib/types'

const W = 400
const H = 240

function sevColor(sev: number): string {
  if (sev >= 81) return SEVERITY_COLOR.CRITICAL
  if (sev >= 61) return SEVERITY_COLOR.HIGH
  if (sev >= 41) return SEVERITY_COLOR.MODERATE
  if (sev >= 21) return SEVERITY_COLOR.LOW
  return SEVERITY_COLOR.SAFE
}

export function RadarCanvas({
  cells,
  className,
  heightClass = 'aspect-[5/3]',
}: {
  cells: ThreatCell[]
  className?: string
  heightClass?: string
}) {
  const { toXY, toXYp } = useMemo(() => {
    const lats = cells.map((c) => c.center.lat)
    const lngs = cells.map((c) => c.center.lng)
    const minLat = Math.min(...lats, 18.4) - 0.15
    const maxLat = Math.max(...lats, 18.7) + 0.15
    const minLng = Math.min(...lngs, 73.7) - 0.15
    const maxLng = Math.max(...lngs, 74.0) + 0.15
    const px = (lng: number) => ((lng - minLng) / (maxLng - minLng)) * W
    const py = (lat: number) => H - ((lat - minLat) / (maxLat - minLat)) * H
    return {
      toXY: (lat: number, lng: number) => [px(lng), py(lat)] as const,
      toXYp: (p: { lat: number; lng: number }) => [px(p.lng), py(p.lat)] as const,
    }
  }, [cells])

  const active = cells.filter((c) => c.status === 'active' || c.status === 'dissipating')

  return (
    <div className={className}>
      <svg viewBox={`0 0 ${W} ${H}`} className={`w-full ${heightClass} bg-ink-950`} role="img" aria-label="Tactical radar of live threat cells">
        {/* range rings + crosshair */}
        <g stroke="var(--color-ink-700)" strokeWidth="0.75" fill="none">
          {[40, 80, 120, 160].map((r) => (
            <circle key={r} cx={W / 2} cy={H / 2} r={r} />
          ))}
          <line x1={0} y1={H / 2} x2={W} y2={H / 2} />
          <line x1={W / 2} y1={0} x2={W / 2} y2={H} />
        </g>
        <g stroke="var(--color-ink-600)" strokeWidth="0.5" opacity="0.5">
          {Array.from({ length: 19 }).map((_, i) => (
            <line key={`v${i}`} x1={(i + 1) * 20} y1={0} x2={(i + 1) * 20} y2={H} />
          ))}
          {Array.from({ length: 11 }).map((_, i) => (
            <line key={`h${i}`} x1={0} y1={(i + 1) * 20} x2={W} y2={(i + 1) * 20} />
          ))}
        </g>

        {/* rotating sweep */}
        <motion.g
          initial={false}
          animate={{ rotate: 360 }}
          transition={{ duration: 4.5, ease: 'linear', repeat: Infinity }}
          style={{ originX: `${W / 2}px`, originY: `${H / 2}px` }}
        >
          <path
            d={`M ${W / 2} ${H / 2} L ${W / 2 + 160} ${H / 2} A 160 160 0 0 0 ${W / 2 + 160 * Math.cos(-0.5)} ${H / 2 + 160 * Math.sin(-0.5)} Z`}
            fill="var(--color-accent)"
            opacity="0.07"
          />
          <line x1={W / 2} y1={H / 2} x2={W / 2 + 160} y2={H / 2} stroke="var(--color-accent)" strokeWidth="1" opacity="0.5" />
        </motion.g>

        {/* projected tracks (dashed, ahead of the cell) */}
        {active.map((c) => (
          <g key={`t-${c.id}`}>
            {c.predicted_track.slice(0, 6).map((p, i) => {
              const [x, y] = toXYp(p)
              const [px2, py2] = i === 0 ? toXY(c.center.lat, c.center.lng) : toXYp(c.predicted_track[i - 1])
              return <line key={i} x1={px2} y1={py2} x2={x} y2={y} stroke={sevColor(p.severity ?? c.current_severity)} strokeWidth="1" strokeDasharray="3 3" opacity="0.55" />
            })}
          </g>
        ))}

        {/* threat cells */}
        {active.map((c) => {
          const [x, y] = toXY(c.center.lat, c.center.lng)
          const r = 8 + c.radius_km * 14
          const col = sevColor(c.current_severity)
          const key = c.severity_label as SeverityKey
          const moving = c.movement.is_moving && c.movement.bearing_deg !== null
          return (
            <g key={c.id}>
              <motion.circle
                cx={x}
                cy={y}
                r={r}
                fill={col}
                fillOpacity="0.16"
                stroke={col}
                strokeWidth="1.25"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5 }}
              />
              {c.movement.is_moving && (
                <motion.circle cx={x} cy={y} r={r} fill="none" stroke={col} strokeWidth="1" initial={{ opacity: 0.8 }} animate={{ opacity: [0.8, 0, 0.8], r: [r, r + 8, r] }} transition={{ duration: 2.2, repeat: Infinity, ease: 'easeOut' }} />
              )}
              <circle cx={x} cy={y} r="2.5" fill={col} />
              {/* movement vector arrow */}
              {moving && (
                <line
                  x1={x}
                  y1={y}
                  x2={x + Math.sin((c.movement.bearing_deg! * Math.PI) / 180) * 26}
                  y2={y - Math.cos((c.movement.bearing_deg! * Math.PI) / 180) * 26}
                  stroke={col}
                  strokeWidth="1.5"
                  markerEnd="none"
                />
              )}
              <text x={x + r + 4} y={y - 2} fontFamily="'JetBrains Mono', monospace" fontSize="7.5" fill={col} fontWeight="600">
                {key}
              </text>
              <text x={x + r + 4} y={y + 7} fontFamily="'JetBrains Mono', monospace" fontSize="6.5" fill="var(--color-ink-400)">
                {c.movement.speed_kmh !== null ? `${c.movement.speed_kmh.toFixed(1)} km/h ${c.movement.compass ?? ''}` : 'STATIC'}
              </text>
            </g>
          )
        })}

        {/* empty state */}
        {active.length === 0 && (
          <g>
            <text x={W / 2} y={H / 2 - 6} textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill="var(--color-ink-400)" letterSpacing="2">
              NO ACTIVE THREAT CELLS
            </text>
            <text x={W / 2} y={H / 2 + 8} textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="7" fill="var(--color-ink-500)" letterSpacing="1">
              SCAN CONTINUING · SIMULATED FEED
            </text>
          </g>
        )}

        {/* corner HUD ticks */}
        <g stroke="var(--color-accent)" strokeWidth="1.5" opacity="0.6">
          <path d={`M 6 14 V 6 H 14`} fill="none" />
          <path d={`M ${W - 14} 6 H ${W - 6} V 14`} fill="none" />
          <path d={`M ${W - 6} ${H - 14} V ${H - 6} H ${W - 14}`} fill="none" />
          <path d={`M 14 ${H - 6} H 6 V ${H - 14}`} fill="none" />
        </g>
      </svg>
    </div>
  )
}
