/**
 * Full risk assessment view for one location.
 *
 * Renders, in the engine's own words: the two-dimensional risk, confidence
 * breakdown, uncertainty band, momentum, ranked contributions ("why this
 * risk?"), early signals, prediction timeline, decision window, lead time,
 * data freshness and the model that produced it.
 *
 * Nothing here is computed locally. If the engine could not produce a value,
 * the reason is displayed instead (Sections 6, 11, 12, 13, 14, 63).
 */
import {
  Activity,
  BrainCircuit,
  Clock,
  Database,
  Gauge,
  Radio,
  Signal,
  TrendingUp,
  TriangleAlert,
  Waves,
} from 'lucide-react'
import {
  SEVERITY_COLOR,
  clsx,
  fmtDuration,
  fmtMinutes,
  fmtNumber,
  fmtPeople,
  relativeTime,
  titleCase,
  withAlpha,
} from '../lib/format'
import type { Contributor, RiskResponse, SeverityKey, TimelineEntry } from '../lib/types'
import { Chip, EmptyState, Panel, SeverityBadge, SeverityBar, Unavailable } from './ui'

export function RiskDetail({ risk, compact }: { risk: RiskResponse; compact?: boolean }) {
  if (!risk.available) {
    return (
      <EmptyState
        icon={<TriangleAlert size={24} />}
        title="No prediction available for this area"
        detail={risk.detail ?? 'The engine could not produce a prediction. No risk number is shown because none was computed.'}
      />
    )
  }

  const sev = risk.risk.severity
  const key = sev.key as SeverityKey

  return (
    <div className="space-y-3">
      <RiskHeadline risk={risk} />

      <div className={clsx('grid gap-3', compact ? '' : 'lg:grid-cols-2')}>
        <Panel title="Why this risk?" icon={<Activity size={14} className="text-ink-400" />}>
          <WhyThisRisk risk={risk} />
        </Panel>

        <Panel title="Confidence" icon={<Gauge size={14} className="text-ink-400" />}>
          <ConfidenceBreakdownView risk={risk} />
        </Panel>
      </div>

      <Panel
        title="Prediction timeline"
        subtitle="Nowcast horizons — uncertainty widens with lead time"
        icon={<Clock size={14} className="text-ink-400" />}
      >
        <Timeline entries={risk.timeline ?? []} currentLevel={key} />
      </Panel>

      <div className={clsx('grid gap-3', compact ? '' : 'lg:grid-cols-2')}>
        <Panel title="Early signals" icon={<Signal size={14} className="text-ink-400" />}>
          <EarlySignals risk={risk} />
        </Panel>
        <Panel title="Data freshness & health" icon={<Database size={14} className="text-ink-400" />}>
          <DataHealthView risk={risk} />
        </Panel>
      </div>

      <Panel title="Inputs used" subtitle="Every value with its source, age and quality" icon={<Waves size={14} className="text-ink-400" />} dense>
        <InputsTable risk={risk} />
      </Panel>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

export function RiskHeadline({ risk }: { risk: RiskResponse }) {
  const sev = risk.risk.severity
  const key = sev.key as SeverityKey
  const color = sev.color ?? SEVERITY_COLOR[key]
  const unc = risk.risk.uncertainty
  const mom = risk.risk.momentum

  return (
    <div
      className="rounded-xl border p-4"
      style={{ borderColor: withAlpha(color, 0.45), background: withAlpha(color, 0.08) }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-bold text-ink-50">{risk.location.name}</h2>
            <Chip tone="neutral">{risk.location.district}</Chip>
            <Chip tone="sim">{risk.data_mode.label}</Chip>
            {risk.connectivity !== 'online' && <Chip tone="warn">{risk.connectivity}</Chip>}
          </div>
          <p className="mt-0.5 text-xs text-ink-400">
            {risk.hazard.label} · {fmtPeople(risk.location.population)} residents ·{' '}
            {relativeTime(risk.generated_at)}
          </p>
        </div>
        <SeverityBadge level={key} label={sev.label} size="lg" />
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono text-4xl leading-none font-bold" style={{ color }}>
              {risk.risk.overall.toFixed(0)}
            </span>
            <span className="text-sm text-ink-500">/100</span>
          </div>
          <div className="mt-1 text-[11px] text-ink-400">
            range <span className="font-mono text-ink-300">{unc.low.toFixed(0)}–{unc.high.toFixed(0)}</span>{' '}
            (±{unc.plus_minus.toFixed(0)})
          </div>
        </div>

        <div className="min-w-[10rem] flex-1">
          <div className="mb-1 flex justify-between text-[10px] tracking-wide text-ink-500 uppercase">
            <span>Hazard {risk.risk.hazard_score.toFixed(0)}</span>
            <span>Exposure {risk.risk.exposure_score.toFixed(0)}</span>
          </div>
          <SeverityBar value={risk.risk.overall} level={key} height={10} showTicks />
          <p className="mt-1 text-[10px] leading-snug text-ink-500">
            Overall risk = hazard severity modulated by how many people and assets are exposed.
          </p>
        </div>

        <div className="text-right">
          <div className="text-[10px] tracking-wide text-ink-500 uppercase">Trend</div>
          <div className="flex items-center justify-end gap-1.5 text-sm font-medium text-ink-100">
            <span aria-hidden className="text-lg">{mom.arrow}</span>
            {mom.label}
          </div>
          <div className="font-mono text-[11px] text-ink-400">
            {mom.rate_per_hour >= 0 ? '+' : ''}
            {mom.rate_per_hour.toFixed(1)} pts/h
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <MiniStat
          label="Projected peak"
          available={!!risk.peak?.available}
          reason={risk.peak?.reason_unavailable}
          value={
            risk.peak?.available
              ? `${risk.peak.risk?.toFixed(0)}/100 in ${fmtMinutes(risk.peak.in_minutes)}`
              : ''
          }
          note={risk.peak?.label}
        />
        <MiniStat
          label="Decision window"
          available={!!risk.decision_window?.available}
          reason={risk.decision_window?.reason_unavailable}
          value={
            risk.decision_window?.already_critical
              ? 'Already critical'
              : fmtMinutes(risk.decision_window?.minutes ?? null)
          }
          note={`Before crossing ${risk.decision_window?.threshold ?? 81}/100`}
        />
        <MiniStat
          label="Warning lead time"
          available={!!risk.lead_time?.available}
          reason={risk.lead_time?.explanation}
          value={risk.lead_time?.label ?? fmtDuration(risk.lead_time?.seconds ?? null)}
          note={risk.lead_time?.available ? 'Warning ahead of projected peak' : undefined}
        />
      </div>

      {risk.narrative && typeof risk.narrative.whats_happening === 'string' && (
        <p className="mt-3 border-t border-ink-700/40 pt-2.5 text-xs leading-relaxed text-ink-200">
          {risk.narrative.whats_happening as string}{' '}
          <span className="text-ink-400">{risk.narrative.whats_next as string}</span>
        </p>
      )}
    </div>
  )
}

function MiniStat({
  label,
  value,
  note,
  available,
  reason,
}: {
  label: string
  value: string
  note?: string
  available: boolean
  reason?: string | null
}) {
  return (
    <div className="panel-tight px-2.5 py-2">
      <div className="text-[10px] tracking-wide text-ink-500 uppercase">{label}</div>
      {available ? (
        <>
          <div className="font-mono text-sm text-ink-100">{value}</div>
          {note && <div className="text-[10px] text-ink-500">{note}</div>}
        </>
      ) : (
        <div className="mt-0.5">
          <Unavailable reason={reason} compact />
        </div>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */

export function WhyThisRisk({ risk }: { risk: RiskResponse }) {
  const contributors = (risk.contributors ?? []).filter((c) => c.points > 0.05)
  const explanation = risk.explanation ?? []

  if (contributors.length === 0 && explanation.length === 0) {
    return (
      <EmptyState
        title="No contributions to explain"
        detail="The engine found no feature contributing meaningfully to risk in this area right now."
      />
    )
  }

  const max = Math.max(...contributors.map((c) => c.points), 1)

  return (
    <div className="space-y-3">
      {explanation.length > 0 && (
        <ol className="space-y-1.5">
          {explanation.slice(0, 4).map((e, i) => (
            <li key={i} className="flex gap-2 text-xs leading-relaxed text-ink-200">
              <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded bg-ink-700 font-mono text-[9px] text-ink-300">
                {i + 1}
              </span>
              <span>{e.text}</span>
            </li>
          ))}
        </ol>
      )}

      <div className="space-y-1.5 border-t border-ink-700/40 pt-2.5">
        <div className="flex justify-between text-[10px] tracking-wide text-ink-500 uppercase">
          <span>Ranked contribution</span>
          <span>points of 100</span>
        </div>
        {contributors.slice(0, 8).map((c) => (
          <ContributorRow key={`${c.component}-${c.feature}`} c={c} max={max} />
        ))}
      </div>

      {risk.hazard.compound && (
        <div
          className={clsx(
            'rounded-md border px-2.5 py-2 text-[11px] leading-snug',
            risk.hazard.compound.is_compound
              ? 'border-high/40 bg-high/10 text-high'
              : 'border-ink-700/60 text-ink-500',
          )}
        >
          <span className="font-semibold">
            {risk.hazard.compound.is_compound
              ? `Compound risk +${risk.hazard.compound.bonus.toFixed(1)} pts: `
              : 'Compound check: '}
          </span>
          {risk.hazard.compound.explanation}
        </div>
      )}
    </div>
  )
}

function ContributorRow({ c, max }: { c: Contributor; max: number }) {
  const componentTone: Record<string, string> = {
    hazard: '#d1600f',
    vulnerability: '#8b5cf6',
    forecast: '#3f7fbf',
    trend: '#1f9e6e',
  }
  const color = componentTone[c.component] ?? '#5b6b83'
  return (
    <div className="flex items-center gap-2">
      <span className="w-36 shrink-0 truncate text-[11px] text-ink-300" title={c.label}>
        {c.label}
      </span>
      <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-ink-800">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.max(2, (c.points / max) * 100)}%`, background: color }}
        />
      </div>
      <span className="w-11 shrink-0 text-right font-mono text-[11px] text-ink-200">
        +{c.points.toFixed(1)}
      </span>
      <span className="hidden w-24 shrink-0 truncate text-right font-mono text-[10px] text-ink-500 sm:block">
        {c.raw_value !== null ? `${fmtNumber(c.raw_value, Math.abs(c.raw_value) < 10 ? 2 : 0)} ${c.unit}` : '—'}
      </span>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

export function ConfidenceBreakdownView({ risk }: { risk: RiskResponse }) {
  const conf = risk.risk.confidence
  const tone = conf.value >= 75 ? '#1f7a4d' : conf.value >= 50 ? '#c98a17' : '#b3161c'

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-3">
        <div>
          <span className="font-mono text-3xl leading-none font-bold" style={{ color: tone }}>
            {conf.value.toFixed(0)}
          </span>
          <span className="text-sm text-ink-500">%</span>
        </div>
        <div className="pb-0.5">
          <div className="text-xs font-medium text-ink-100">{conf.label}</div>
          {conf.is_reduced && <div className="text-[10px] text-moderate">reduced by penalties</div>}
        </div>
      </div>

      <div className="space-y-1.5">
        {Object.entries(conf.components ?? {}).map(([key, value]) => (
          <div key={key} className="flex items-center gap-2">
            <span className="w-32 shrink-0 truncate text-[11px] text-ink-300">
              {titleCase(key.replace(/_/g, ' '))}
            </span>
            <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-ink-800">
              <div className="h-full rounded-full bg-accent/70" style={{ width: `${Math.max(2, value)}%` }} />
            </div>
            <span className="w-9 shrink-0 text-right font-mono text-[11px] text-ink-400">
              {value.toFixed(0)}
            </span>
            <span className="w-10 shrink-0 text-right font-mono text-[10px] text-ink-600">
              ×{(conf.weights?.[key] ?? 0).toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      <p className="text-[11px] leading-snug text-ink-500">{conf.band_note}</p>

      {(conf.penalties ?? []).length > 0 && (
        <div className="rounded-md border border-moderate/30 bg-moderate/8 px-2.5 py-2">
          <div className="mb-1 text-[10px] tracking-wide text-moderate uppercase">Penalties applied</div>
          <ul className="space-y-0.5">
            {conf.penalties.map((p, i) => (
              <li key={i} className="flex justify-between gap-2 text-[11px] text-ink-300">
                <span>{p.detail}</span>
                <span className="font-mono shrink-0 text-moderate">−{p.points.toFixed(0)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="border-t border-ink-700/40 pt-2 text-[11px] text-ink-400">
        <div className="flex items-center gap-1.5">
          <BrainCircuit size={12} aria-hidden />
          <span className="text-ink-200">{risk.model.name}</span>
          <span className="font-mono text-ink-500">v{risk.model.version}</span>
          {risk.model.is_fallback && <Chip tone="warn">fallback</Chip>}
        </div>
        {(risk.model.notes ?? []).map((n, i) => (
          <p key={i} className="mt-0.5 leading-snug text-ink-500">
            {n}
          </p>
        ))}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

export function Timeline({ entries, currentLevel }: { entries: TimelineEntry[]; currentLevel: SeverityKey }) {
  if (!entries || entries.length === 0) {
    return <EmptyState title="No timeline produced" detail="The model did not return horizon predictions." />
  }
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${entries.length}, minmax(0, 1fr))` }}>
      {entries.map((e) => {
        if (!e.available) {
          return (
            <div key={e.horizon_minutes} className="panel-tight px-2 py-2 text-center">
              <div className="text-[10px] font-semibold tracking-wide text-ink-500">{e.label}</div>
              <div className="mt-1">
                <Unavailable reason={e.reason} compact label="—" />
              </div>
            </div>
          )
        }
        const key = (e.severity?.key ?? currentLevel) as SeverityKey
        const color = e.severity?.color ?? SEVERITY_COLOR[key]
        return (
          <div
            key={e.horizon_minutes}
            className="panel-tight px-2 py-2 text-center"
            style={{ borderColor: withAlpha(color, 0.4) }}
            title={`${e.label}: ${e.risk?.toFixed(0)}/100 (${e.severity?.label}), confidence ${e.confidence?.toFixed(0)}%, range ${e.uncertainty?.low.toFixed(0)}–${e.uncertainty?.high.toFixed(0)}`}
          >
            <div className="text-[10px] font-semibold tracking-wide text-ink-400">{e.label}</div>
            <div className="mt-0.5 font-mono text-lg leading-none font-bold" style={{ color }}>
              {e.risk?.toFixed(0)}
            </div>
            <div className="mt-0.5 font-mono text-[9px] text-ink-500">
              {e.uncertainty?.low.toFixed(0)}–{e.uncertainty?.high.toFixed(0)}
            </div>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-ink-800">
              <div className="h-full rounded-full" style={{ width: `${e.risk ?? 0}%`, background: color }} />
            </div>
            <div className="mt-1 text-[9px] text-ink-500">conf {e.confidence?.toFixed(0)}%</div>
            {e.expected_intensity && (
              <div className="mt-0.5 truncate text-[9px] text-ink-600" title={e.expected_intensity}>
                {e.expected_intensity}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function EarlySignals({ risk }: { risk: RiskResponse }) {
  const signals = risk.early_signals ?? []
  if (signals.length === 0) {
    return (
      <EmptyState
        icon={<Radio size={22} />}
        title="No early signals detected"
        detail="The precursor detectors (rainfall acceleration, river trend reversal, forecast convergence, soil saturation, pressure fall, convective deepening) found nothing above threshold."
      />
    )
  }
  return (
    <ul className="space-y-2">
      {signals.map((s, i) => (
        <li key={s.id ?? i} className="rounded-md border border-accent/30 bg-accent/8 px-2.5 py-2">
          <div className="flex items-start gap-2">
            <TrendingUp size={13} className="mt-0.5 shrink-0 text-accent-bright" aria-hidden />
            <div className="min-w-0">
              <div className="text-xs font-medium text-ink-100">{s.label}</div>
              <p className="mt-0.5 text-[11px] leading-snug text-ink-400">{s.detail}</p>
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}

function DataHealthView({ risk }: { risk: RiskResponse }) {
  const dh = risk.data_health
  const tone = dh.score >= 80 ? '#1f7a4d' : dh.score >= 55 ? '#c98a17' : '#b3161c'
  return (
    <div className="space-y-2.5">
      <div className="flex items-end gap-2">
        <span className="font-mono text-2xl leading-none font-bold" style={{ color: tone }}>
          {dh.score.toFixed(0)}
        </span>
        <span className="pb-0.5 text-xs text-ink-300">{dh.grade}</span>
      </div>

      <ul className="space-y-1">
        {dh.by_source.map((s) => (
          <li key={s.key} className="flex items-center gap-2 text-[11px]">
            <span
              className="h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: s.status === 'operational' ? '#1f7a4d' : '#b3161c' }}
              aria-hidden
            />
            <span className="min-w-0 flex-1 truncate text-ink-300" title={s.reason ?? undefined}>
              {s.source}
            </span>
            <span className="shrink-0 text-ink-500">{s.age_human}</span>
            <span className="w-8 shrink-0 text-right font-mono text-ink-400">{s.score.toFixed(0)}</span>
          </li>
        ))}
      </ul>

      {dh.failed_providers.length > 0 && (
        <div className="rounded-md border border-critical/30 bg-critical/8 px-2.5 py-1.5">
          {dh.failed_providers.map((f, i) => (
            <p key={i} className="text-[11px] text-critical">
              <span className="font-medium">{f.provider}:</span> {f.reason}
            </p>
          ))}
        </div>
      )}

      {dh.missing_features.length > 0 && (
        <p className="text-[11px] text-ink-400">
          <span className="text-moderate">Missing:</span> {dh.missing_features.join(', ')} — these were{' '}
          <span className="text-ink-200">excluded from the composite</span>, not treated as zero.
        </p>
      )}
      {dh.notes.map((n, i) => (
        <p key={i} className="text-[11px] leading-snug text-ink-500">
          {n}
        </p>
      ))}
    </div>
  )
}

function InputsTable({ risk }: { risk: RiskResponse }) {
  const rows = Object.values(risk.inputs ?? {})
  if (rows.length === 0) return <EmptyState title="No inputs recorded" />
  const freshTone: Record<string, string> = {
    live: 'text-safe',
    recent: 'text-safe',
    ageing: 'text-moderate',
    stale: 'text-high',
    expired: 'text-critical',
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead className="border-b border-ink-700/50 text-[10px] tracking-wide text-ink-500 uppercase">
          <tr>
            <th className="px-3 py-1.5 font-medium">Input</th>
            <th className="px-3 py-1.5 text-right font-medium">Value</th>
            <th className="px-3 py-1.5 font-medium">Source</th>
            <th className="px-3 py-1.5 font-medium">Age</th>
            <th className="px-3 py-1.5 font-medium">Kind</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-700/30">
          {rows.map((o) => {
            const usable = o.value !== null && !o.unavailable_reason
            return (
            <tr key={o.feature} className={clsx(!usable && 'opacity-70')}>
              <td className="px-3 py-1.5 text-ink-200">{o.label}</td>
              <td className="px-3 py-1.5 text-right font-mono text-ink-100">
                {usable && o.value !== null ? (
                  <>
                    {fmtNumber(o.value, Math.abs(o.value) < 10 ? 2 : 0)}{' '}
                    <span className="text-ink-500">{o.unit}</span>
                  </>
                ) : (
                  <Unavailable reason={o.unavailable_reason} compact label="unavailable" />
                )}
              </td>
              <td className="px-3 py-1.5 text-ink-400">
                {o.source}
                {o.is_simulated && <span className="ml-1 text-[9px] text-moderate">SIM</span>}
              </td>
              <td className={clsx('px-3 py-1.5', freshTone[o.freshness] ?? 'text-ink-400')}>
                {o.age_human} <span className="text-ink-600">({o.freshness})</span>
              </td>
              <td className="px-3 py-1.5 text-ink-500">{o.observed_or_predicted}</td>
            </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
