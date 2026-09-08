/**
 * Priority queue rendering (Sections 26, 27).
 *
 * The ranking, the priority score and the "why priority?" sentence are all
 * produced by the backend. This component only lays them out.
 */
import { ChevronDown, ChevronRight, Clock, TrendingUp, Users } from 'lucide-react'
import { useState } from 'react'
import { SEVERITY_COLOR, clsx, fmtMinutes, fmtPeople, withAlpha } from '../lib/format'
import type { PriorityEntry } from '../lib/types'
import { EmptyState, SeverityBadge, SeverityBar, Unavailable } from './ui'

export function PriorityQueueList({
  entries,
  limit,
  selectedId,
  onSelect,
}: {
  entries: PriorityEntry[]
  limit?: number
  selectedId?: string | null
  onSelect?: (id: string) => void
}) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const rows = limit ? entries.slice(0, limit) : entries

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No areas ranked yet"
        detail="The queue fills once the engine has produced a prediction for at least one monitored area. Advance the simulation clock to generate one."
      />
    )
  }

  return (
    <ul className="divide-y divide-ink-700/40">
      {rows.map((entry) => {
        const open = expanded === entry.location_id
        const isSelected = selectedId === entry.location_id
        const color = entry.severity?.color ?? SEVERITY_COLOR[entry.severity?.key ?? 'LOW']
        return (
          <li
            key={entry.location_id}
            className={clsx('transition-colors', isSelected ? 'bg-accent/8' : 'hover:bg-ink-850/60')}
          >
            <div className="flex items-start gap-2.5 px-3 py-2.5">
              {/* rank */}
              <div
                className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md font-mono text-xs font-bold"
                style={{ background: withAlpha(color, 0.18), color, border: `1px solid ${withAlpha(color, 0.45)}` }}
                aria-label={`Rank ${entry.rank}`}
              >
                {entry.rank}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <button
                    type="button"
                    onClick={() => onSelect?.(entry.location_id)}
                    className={clsx(
                      'truncate text-sm font-semibold text-ink-50',
                      onSelect && 'hover:text-accent-bright hover:underline',
                    )}
                  >
                    {entry.location_name}
                  </button>
                  <SeverityBadge
                    level={entry.severity.key}
                    label={entry.severity.label}
                    score={entry.risk}
                    size="sm"
                  />
                  <span
                    className="inline-flex items-center gap-1 rounded border border-ink-600 px-1.5 py-0.5 text-[10px] text-ink-300"
                    title={entry.momentum.note}
                  >
                    <span aria-hidden>{entry.momentum.arrow}</span>
                    {entry.momentum.label}
                    <span className="font-mono text-ink-500">
                      {entry.momentum.rate_per_hour >= 0 ? '+' : ''}
                      {entry.momentum.rate_per_hour.toFixed(0)}/h
                    </span>
                  </span>
                </div>

                <div className="mt-1.5">
                  <SeverityBar value={entry.risk} level={entry.severity.key} height={6} showTicks />
                </div>

                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-400">
                  <span className="inline-flex items-center gap-1">
                    <Users size={10} aria-hidden />
                    {fmtPeople(entry.exposed_population)} exposed
                  </span>
                  <span className="inline-flex items-center gap-1" title="Priority score">
                    <TrendingUp size={10} aria-hidden />
                    priority <span className="font-mono text-ink-300">{entry.priority.toFixed(1)}</span>
                  </span>
                  <span title="Engine confidence in this prediction">
                    confidence <span className="font-mono text-ink-300">{entry.confidence.toFixed(0)}%</span>
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Clock size={10} aria-hidden />
                    {entry.decision_window?.available ? (
                      entry.decision_window.already_critical ? (
                        <span className="text-critical">already critical</span>
                      ) : (
                        <>window {fmtMinutes(entry.decision_window.minutes)}</>
                      )
                    ) : (
                      <span className="text-ink-500">no critical crossing forecast</span>
                    )}
                  </span>
                  <span className="text-ink-500">{entry.hazard_label}</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setExpanded(open ? null : entry.location_id)}
                aria-expanded={open}
                className="mt-0.5 shrink-0 rounded p-1 text-ink-500 hover:bg-ink-800 hover:text-ink-200"
                title="Why this priority?"
              >
                {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              </button>
            </div>

            {open && <PriorityExplanation entry={entry} />}
          </li>
        )
      })}
    </ul>
  )
}

function PriorityExplanation({ entry }: { entry: PriorityEntry }) {
  const factors = entry.priority_factors ?? { risk: 0, exposure: 0, urgency: 0, confidence: 0 }
  const rows: [string, number, string][] = [
    ['Risk', factors.risk, `${entry.risk.toFixed(0)}/100 overall risk`],
    ['Exposure', factors.exposure, `${fmtPeople(entry.exposed_population)} people, exposure score ${entry.exposure_score.toFixed(0)}`],
    ['Urgency', factors.urgency, `${entry.momentum.rate_per_hour >= 0 ? '+' : ''}${entry.momentum.rate_per_hour.toFixed(1)} points/hour`],
    ['Confidence', factors.confidence, `${entry.confidence.toFixed(0)}% engine confidence`],
  ]

  return (
    <div className="border-t border-ink-700/40 bg-ink-950/50 px-3 py-3 pl-12">
      <p className="text-xs leading-relaxed text-ink-200">{entry.why_priority}</p>

      <div className="mt-2.5 space-y-1.5">
        {rows.map(([label, value, detail]) => (
          <div key={label} className="flex items-center gap-2">
            <span className="w-20 shrink-0 text-[11px] text-ink-400">{label}</span>
            <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-ink-800">
              <div
                className="h-full rounded-full bg-accent/70"
                style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-right font-mono text-[11px] text-ink-300">
              ×{value.toFixed(2)}
            </span>
            <span className="hidden w-56 shrink-0 truncate text-[10px] text-ink-500 lg:block" title={detail}>
              {detail}
            </span>
          </div>
        ))}
      </div>

      <p className="mt-2 font-mono text-[10px] text-ink-500">
        priority = risk × exposure × urgency × confidence × 100 ={' '}
        <span className="text-ink-300">{entry.priority.toFixed(1)}</span>
      </p>

      <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
        <div className="panel-tight px-2.5 py-1.5">
          <div className="text-[10px] tracking-wide text-ink-500 uppercase">Projected peak</div>
          {entry.peak?.available ? (
            <div className="text-xs text-ink-200">
              <span className="font-mono">{entry.peak.risk?.toFixed(0)}</span>/100 in{' '}
              {fmtMinutes(entry.peak.in_minutes)}
              <span className="ml-1.5 text-[10px] text-ink-500">{entry.peak.label}</span>
            </div>
          ) : (
            <Unavailable reason={entry.peak?.reason_unavailable} compact />
          )}
        </div>
        <div className="panel-tight px-2.5 py-1.5">
          <div className="text-[10px] tracking-wide text-ink-500 uppercase">Hazard vs exposure</div>
          <div className="text-xs text-ink-200">
            hazard <span className="font-mono">{entry.hazard_score.toFixed(0)}</span> · exposure{' '}
            <span className="font-mono">{entry.exposure_score.toFixed(0)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
