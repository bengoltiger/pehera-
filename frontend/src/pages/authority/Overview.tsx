/**
 * Command-centre overview (Sections 25, 26, 27).
 *
 * Headline metrics, the ranked priority queue and live threat cells. Every
 * number is read from the backend; this screen contains no risk arithmetic.
 */
import {
  ArrowRight,
  Building2,
  Clock,
  Database,
  Gauge,
  Info,
  ListOrdered,
  Radar,
  Siren,
  TriangleAlert,
  Users,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { PriorityQueueList } from '../../components/PriorityQueue'
import { ThreatCellList } from '../../components/ThreatCells'
import { ErrorBlock, LoadingBlock, Panel, Stat, StaleNotice } from '../../components/ui'
import { api } from '../../lib/api'
import { SEVERITY_COLOR, fmtDuration, fmtNumber, fmtPeople, fmtTime } from '../../lib/format'
import { useApi } from '../../lib/hooks'

export default function Overview() {
  const { data, error, loading, stale, reload } = useApi(() => api.overview())

  if (loading && !data) {
    return (
      <div className="space-y-3 p-4">
        <LoadingBlock rows={2} />
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="panel-tight h-20" />
          ))}
        </div>
        <LoadingBlock rows={6} />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-4">
        <ErrorBlock error={error} onRetry={reload} />
      </div>
    )
  }

  const m = data.metrics
  const queue = data.priority_queue ?? []
  const topRisk = queue[0]

  return (
    <div className="space-y-3 p-3 lg:p-4">
      <StaleNotice stale={stale} />

      {/* ---------------------------------------------------- headline --- */}
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-ink-50">Command centre</h1>
          <p className="text-xs text-ink-400">
            {m.monitored_locations} monitored areas · generated {fmtTime(data.generated_at, { seconds: true })}
            {' · '}
            <span className="text-moderate">{data.data_mode.label}</span>
          </p>
        </div>
        <Link
          to="/authority/queue"
          className="inline-flex items-center gap-1.5 rounded-md border border-ink-600 px-2.5 py-1.5 text-xs text-ink-200 hover:bg-ink-800"
        >
          <ListOrdered size={13} />
          Full priority queue
          <ArrowRight size={12} />
        </Link>
      </header>

      {/* ----------------------------------------------------- metrics --- */}
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <Stat
          label="Active threats"
          icon={<Radar size={11} />}
          value={fmtNumber(m.active_threats)}
          hint="Tracked concentrations of risk"
          tone={m.active_threats > 0 ? SEVERITY_COLOR.HIGH : undefined}
        />
        <Stat
          label="Critical zones"
          icon={<TriangleAlert size={11} />}
          value={fmtNumber(m.critical_zones)}
          hint={`${fmtNumber(m.high_zones)} more at high risk`}
          tone={m.critical_zones > 0 ? SEVERITY_COLOR.CRITICAL : undefined}
        />
        <Stat
          label="People exposed"
          icon={<Users size={11} />}
          value={fmtPeople(m.people_potentially_exposed)}
          hint="In zones at high risk or above"
        />
        <Stat
          label="Alerts issued"
          icon={<Siren size={11} />}
          value={fmtNumber(m.alerts_issued)}
          hint={
            m.alerts_awaiting_approval > 0 ? (
              <Link to="/authority/alerts" className="text-moderate hover:underline">
                {m.alerts_awaiting_approval} awaiting approval
              </Link>
            ) : (
              'None awaiting approval'
            )
          }
        />
        <Stat
          label="Avg lead time"
          icon={<Clock size={11} />}
          value={fmtDuration(m.average_lead_time_seconds)}
          unavailableReason={m.average_lead_time_note}
          hint="Warning raised before projected peak"
        />
        <Stat
          label="Data health"
          icon={<Database size={11} />}
          value={`${m.data_health.toFixed(0)}%`}
          hint={m.data_health_grade}
          tone={m.data_health >= 80 ? SEVERITY_COLOR.SAFE : m.data_health >= 55 ? SEVERITY_COLOR.MODERATE : SEVERITY_COLOR.CRITICAL}
        />
      </div>

      {/* --------------------------------------------------- top banner -- */}
      {topRisk && topRisk.risk >= 61 && (
        <div
          className="flex flex-wrap items-center gap-3 rounded-lg border px-3.5 py-2.5"
          style={{
            borderColor: `${topRisk.severity.color}66`,
            backgroundColor: `${topRisk.severity.color}14`,
          }}
        >
          <Siren size={18} style={{ color: topRisk.severity.color }} aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink-50">
              Highest priority: {topRisk.location_name} — {topRisk.hazard_label} at{' '}
              <span className="font-mono">{topRisk.risk.toFixed(0)}/100</span>{' '}
              <span style={{ color: topRisk.severity.color }}>{topRisk.severity.label}</span>{' '}
              {topRisk.momentum.arrow} {topRisk.momentum.label.toLowerCase()}
            </p>
            <p className="mt-0.5 text-[11px] leading-snug text-ink-300">{topRisk.why_priority}</p>
          </div>
          <Link
            to={`/authority/queue?location=${topRisk.location_id}`}
            className="shrink-0 rounded-md border border-ink-600 bg-ink-900/60 px-2.5 py-1.5 text-xs text-ink-100 hover:bg-ink-800"
          >
            Open
          </Link>
        </div>
      )}

      {/* --------------------------------------------------------- body -- */}
      <div className="grid min-h-0 gap-3 xl:grid-cols-[1.55fr_1fr]">
        <Panel
          title="Priority queue"
          subtitle="Ranked by risk × exposure × urgency × confidence — not by hazard severity alone"
          icon={<ListOrdered size={14} className="text-ink-400" />}
          dense
          bodyClassName="overflow-y-auto max-h-[38rem]"
        >
          <PriorityQueueList entries={queue} limit={8} />
        </Panel>

        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            title="Threat cells"
            subtitle={`${data.threat_cells.length} tracked · ${fmtNumber(data.risk_field_points)} field samples`}
            icon={<Radar size={14} className="text-ink-400" />}
            dense
            bodyClassName="overflow-y-auto max-h-[26rem]"
          >
            <ThreatCellList cells={data.threat_cells} />
          </Panel>

          <Panel title="How this ranking works" icon={<Info size={14} className="text-ink-400" />}>
            <p className="text-xs leading-relaxed text-ink-300">
              A ward with a slightly lower hazard score can outrank a more severe one when far more
              people are exposed, when risk is climbing faster, or when the prediction is more
              confident. That is the point of a two-dimensional model: it answers{' '}
              <span className="text-ink-100">“where should the next truck go?”</span> rather than
              “where is the weather worst?”.
            </p>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
              {[
                ['Risk', 'Hazard severity modulated by exposure'],
                ['Exposure', 'Population, critical facilities, vulnerable share'],
                ['Urgency', 'Rate of change in risk points per hour'],
                ['Confidence', 'Data quality, model self-assessment, agreement'],
              ].map(([k, v]) => (
                <div key={k} className="panel-tight px-2 py-1.5">
                  <dt className="font-medium text-ink-200">{k}</dt>
                  <dd className="text-ink-500">{v}</dd>
                </div>
              ))}
            </dl>
          </Panel>

          <Panel title="Infrastructure at risk" icon={<Building2 size={14} className="text-ink-400" />}>
            <ExposureSummary queue={queue} />
          </Panel>
        </div>
      </div>
    </div>
  )
}

function ExposureSummary({ queue }: { queue: { risk: number; exposed_population: number; location_name: string; severity: { color: string; label: string } }[] }) {
  const atRisk = queue.filter((q) => q.risk >= 41)
  if (atRisk.length === 0) {
    return (
      <p className="text-xs text-ink-400">
        No monitored area is currently above the WATCH threshold, so no population is flagged as
        exposed.
      </p>
    )
  }
  const total = atRisk.reduce((sum, q) => sum + q.exposed_population, 0)
  return (
    <div className="space-y-2">
      <p className="text-xs text-ink-300">
        <span className="font-mono text-base font-semibold text-ink-50">{fmtPeople(total)}</span> people live in
        the {atRisk.length} area{atRisk.length === 1 ? '' : 's'} currently above the WATCH threshold.
      </p>
      <ul className="space-y-1">
        {atRisk.slice(0, 5).map((q) => (
          <li key={q.location_name} className="flex items-center gap-2 text-[11px]">
            <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: q.severity.color }} aria-hidden />
            <span className="min-w-0 flex-1 truncate text-ink-300">{q.location_name}</span>
            <span className="font-mono text-ink-400">{fmtPeople(q.exposed_population)}</span>
          </li>
        ))}
      </ul>
      <p className="flex items-start gap-1 text-[10px] leading-snug text-ink-500">
        <Gauge size={10} className="mt-0.5 shrink-0" aria-hidden />
        Population figures come from the seeded demo dataset and are estimates, not a census.
      </p>
    </div>
  )
}
