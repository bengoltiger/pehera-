/**
 * Simulation lab (Sections 74–78, 83, 84, 88).
 *
 * Everything on this screen is openly a simulation control surface. It exists
 * because PEHRA's honest position is that no live observation network is
 * connected: instead of faking a live feed, we let the operator drive a
 * deterministic scenario clock and watch the engine react.
 *
 * The what-if lab never writes anything: it re-runs the engine on modified
 * inputs and throws the result away. It cannot create alerts.
 */
import {
  AlertTriangle,
  BrainCircuit,
  FlaskConical,
  Gauge,
  Pause,
  Play,
  PlayCircle,
  Plug,
  Rewind,
  RotateCcw,
  SkipForward,
  TimerReset,
  Wifi,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button, Chip, EmptyState, ErrorBlock, LoadingBlock, Panel, SeverityBadge } from '../../components/ui'
import { api } from '../../lib/api'
import { LEVEL_COLOR, clsx, fmtNumber, titleCase, withAlpha } from '../../lib/format'
import { useApi, useMutation } from '../../lib/hooks'
import type { Connectivity, Severity, SeverityKey } from '../../lib/types'

const FAILURE_COMPONENTS = [
  'rainfall',
  'weather',
  'river',
  'satellite',
  'soil',
  'terrain',
  'historical',
  'forecast',
  'ml_model',
  'database',
] as const

const SLIDERS: { key: string; label: string; affects: string }[] = [
  { key: 'rainfall', label: 'Rainfall', affects: 'rain_intensity, rain_accumulation_3h' },
  { key: 'river_level', label: 'River level', affects: 'river_level_ratio, river_rate' },
  { key: 'soil_moisture', label: 'Soil moisture', affects: 'soil_moisture' },
  { key: 'wind', label: 'Wind', affects: 'wind_speed, wind_gust' },
  { key: 'forecast_intensity', label: 'Forecast intensity', affects: 'forecast_rain_3h' },
]

export default function SimLab() {
  const scenarios = useApi(() => api.scenarios())
  const state = useApi(() => api.simState())
  const models = useApi(() => api.models())
  const providers = useApi(() => api.providers())

  const run = useMutation((id: string, tick?: number) =>
    api.runScenario(id, { reset_tick: true, auto_advance_to: tick ?? null }),
  )
  const step = useMutation((n: number) => api.step(n, true))
  const refresh = useMutation(() => api.refresh())
  const reset = useMutation(() => api.resetDemo())
  const start = useMutation(() => api.simulationStart())
  const pause = useMutation(() => api.simulationPause())
  const speed = useMutation((v: number) => api.simulationSpeed(v))
  const jumpTick = useMutation((t: number) => api.simulationJump(t, true))
  const setConn = useMutation((mode: Connectivity) => api.setConnectivity(mode))
  const setFail = useMutation((component: string, enabled: boolean) => api.setFailure(component, enabled))
  const setModel = useMutation((key: string) => api.setModel(key))

  const clock = state.data
  const busy =
    run.pending || step.pending || refresh.pending || reset.pending || start.pending || pause.pending ||
    speed.pending || jumpTick.pending || setConn.pending || setFail.pending
  const [speedVal, setSpeedVal] = useState(1)
  const [jumpVal, setJumpVal] = useState('0')

  useEffect(() => {
    if (clock?.speed != null) setSpeedVal(clock.speed)
  }, [clock?.speed])

  const commitJump = (raw: string) => {
    const n = Math.max(0, Math.min(clock?.total_ticks ?? 240, Number.parseInt(raw || '0', 10) || 0))
    jumpTick.run(n).then(() => state.reload())
  }

  return (
    <div className="space-y-3 p-3 lg:p-4">
      <div className="rounded-lg border border-moderate/40 bg-moderate/8 px-3 py-2 text-[11px] leading-snug text-moderate">
        <strong>This is the simulation control room.</strong> PEHRA has no live observation feed
        connected. Every value in the product is produced by these deterministic scenarios, and every
        control here is labelled with exactly what it changes.
      </div>

      {/* ------------------------------------------------------- clock -- */}
      <Panel
        title="Scenario clock"
        subtitle={clock?.narrative ?? undefined}
        icon={<PlayCircle size={14} className="text-ink-400" />}
      >
        {!clock ? (
          <LoadingBlock rows={3} />
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <div>
                <div className="text-[10px] tracking-wide text-ink-500 uppercase">Scenario</div>
                <div className="text-sm font-semibold text-ink-50">{clock.scenario_name}</div>
              </div>
              <div>
                <div className="text-[10px] tracking-wide text-ink-500 uppercase">Tick</div>
                <div className="font-mono text-sm text-ink-100">
                  {clock.tick} / {clock.total_ticks}
                </div>
              </div>
              <div>
                <div className="text-[10px] tracking-wide text-ink-500 uppercase">Simulated elapsed</div>
                <div className="font-mono text-sm text-ink-100">
                  {clock.elapsed_label ?? `+${(clock.tick ?? 0) * (clock.tick_minutes ?? 15)}m`}
                </div>
              </div>
              <div>
                <div className="text-[10px] tracking-wide text-ink-500 uppercase">Active model</div>
                <div className="font-mono text-sm text-ink-100">{clock.active_model}</div>
              </div>
              {clock.expected_peak_tick !== null && clock.expected_peak_tick !== undefined && (
                <div>
                  <div className="text-[10px] tracking-wide text-ink-500 uppercase">Expected peak</div>
                  <div className="font-mono text-sm text-ink-100">tick {clock.expected_peak_tick}</div>
                </div>
              )}
            </div>

            <div className="h-1.5 overflow-hidden rounded-full bg-ink-800">
              <div
                className="h-full rounded-full bg-accent transition-[width] duration-500"
                style={{ width: `${((clock.tick ?? 0) / (clock.total_ticks || 1)) * 100}%` }}
              />
            </div>

            {/* play/pause + speed + jump (Sections 78–79) */}
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-ink-700/60 bg-ink-850/40 px-2.5 py-2">
              <Button
                size="sm"
                variant={clock.running ? 'primary' : 'ghost'}
                icon={clock.running ? <Pause size={12} /> : <Play size={12} />}
                pending={start.pending || pause.pending}
                disabled={busy}
                onClick={() =>
                  clock.running ? pause.run().then(() => state.reload()) : start.run().then(() => state.reload())
                }
              >
                {clock.running ? 'Pause clock' : 'Play clock'}
              </Button>

              <label className="flex min-w-[12rem] flex-1 items-center gap-2">
                <Gauge size={12} className="shrink-0 text-ink-400" />
                <span className="shrink-0 text-[10px] tracking-wide text-ink-500 uppercase">Speed</span>
                <input
                  type="range"
                  min={0.5}
                  max={10}
                  step={0.5}
                  value={speedVal}
                  onChange={(e) => setSpeedVal(Number(e.target.value))}
                  onPointerUp={() => speed.run(speedVal).then(() => state.reload())}
                  onKeyUp={() => speed.run(speedVal).then(() => state.reload())}
                  className="w-full accent-[var(--color-accent)]"
                />
                <span className="w-14 shrink-0 text-right font-mono text-[11px] text-ink-200">
                  ×{speedVal.toFixed(1)}
                </span>
              </label>

              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={0}
                  max={clock.total_ticks}
                  value={jumpVal}
                  onChange={(e) => setJumpVal(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitJump(jumpVal)
                  }}
                  className="w-20 rounded-md border border-ink-600 bg-ink-850 px-2 py-1 font-mono text-xs text-ink-100"
                  aria-label="Jump to tick"
                />
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<TimerReset size={12} />}
                  pending={jumpTick.pending}
                  disabled={busy}
                  onClick={() => commitJump(jumpVal)}
                >
                  Jump
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Rewind size={12} />}
                  disabled={busy || clock.tick === 0}
                  onClick={() => jumpTick.run(0).then(() => state.reload())}
                  title="Rewind to tick 0 without changing the scenario"
                >
                  t0
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap gap-1.5">
              <Button
                size="sm"
                icon={<SkipForward size={12} />}
                pending={step.pending}
                disabled={busy || clock.at_end}
                onClick={() => step.run(1).then(() => state.reload())}
              >
                Step +1 tick ({clock.tick_minutes}m)
              </Button>
              <Button
                size="sm"
                disabled={busy || clock.at_end}
                onClick={() => step.run(4).then(() => state.reload())}
              >
                Step +4
              </Button>
              <Button
                size="sm"
                variant="ghost"
                pending={refresh.pending}
                disabled={busy}
                onClick={() => refresh.run().then(() => state.reload())}
              >
                Re-evaluate now
              </Button>
              <Button
                size="sm"
                variant="ghost"
                icon={<RotateCcw size={12} />}
                pending={reset.pending}
                disabled={busy}
                onClick={() => reset.run().then(() => state.reload())}
              >
                Reset demo
              </Button>
              {clock.at_end && <Chip tone="warn">scenario finished — reset or pick another</Chip>}
            </div>

            <ErrorBlock
              error={step.error ?? refresh.error ?? reset.error ?? run.error ?? speed.error ?? jumpTick.error}
              compact
            />
          </div>
        )}
      </Panel>

      {/* --------------------------------------------------- scenarios -- */}
      <Panel title="Scenario library" subtitle="Deterministic, replayable, seeded">
        {!scenarios.data ? (
          <LoadingBlock rows={4} />
        ) : (
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {scenarios.data.scenarios.map((sc) => {
              const active = clock?.scenario_id === sc.id
              return (
                <div
                  key={sc.id}
                  className={clsx(
                    'rounded-lg border p-3 transition-colors',
                    active ? 'border-accent/60 bg-accent/8' : 'border-ink-700 bg-ink-850/40',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-xs font-semibold text-ink-50">{sc.name}</h3>
                    {active && <Chip tone="info">running</Chip>}
                  </div>
                  <p className="mt-1 text-[11px] leading-snug text-ink-400">{sc.description}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {sc.hazard_focus.map((h) => (
                      <Chip key={h} tone="neutral">
                        {titleCase(h.replace(/_/g, ' '))}
                      </Chip>
                    ))}
                    {sc.has_outages && <Chip tone="warn">includes outage</Chip>}
                    {sc.expected_peak_tick !== null && (
                      <Chip tone="neutral">peak ~t{sc.expected_peak_tick}</Chip>
                    )}
                  </div>
                  <div className="mt-2 flex gap-1.5">
                    <Button
                      size="sm"
                      variant={active ? 'ghost' : 'primary'}
                      disabled={busy}
                      onClick={() => run.run(sc.id, 0).then(() => state.reload())}
                    >
                      Load at t0
                    </Button>
                    {sc.expected_peak_tick !== null && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() =>
                          run.run(sc.id, sc.expected_peak_tick as number).then(() => state.reload())
                        }
                      >
                        Jump to peak
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* ------------------------------------------------ degradation -- */}
        <Panel
          title="Degradation & failure injection"
          subtitle="Prove the failure states are real, not decoration"
          icon={<Plug size={14} className="text-ink-400" />}
        >
          <div className="space-y-3">
            <div>
              <div className="mb-1 flex items-center gap-1.5 text-[10px] tracking-wide text-ink-500 uppercase">
                <Wifi size={11} /> Connectivity
              </div>
              <div className="flex gap-1.5">
                {(['online', 'degraded', 'offline'] as Connectivity[]).map((mode) => (
                  <Button
                    key={mode}
                    size="sm"
                    variant={clock?.connectivity === mode ? 'primary' : 'ghost'}
                    disabled={busy}
                    onClick={() => setConn.run(mode).then(() => state.reload())}
                  >
                    {titleCase(mode)}
                  </Button>
                ))}
              </div>
              <p className="mt-1 text-[10px] leading-snug text-ink-500">
                Degraded applies a −5 confidence penalty and marks data ageing; offline serves the last
                cached assessment with a −25 penalty and blocks new alerts.
              </p>
            </div>

            <div>
              <div className="mb-1 flex items-center gap-1.5 text-[10px] tracking-wide text-ink-500 uppercase">
                <AlertTriangle size={11} /> Force a component to fail
              </div>
              <div className="flex flex-wrap gap-1.5">
                {FAILURE_COMPONENTS.map((c) => {
                  const on = !!clock?.forced_failures?.[c]
                  return (
                    <button
                      key={c}
                      type="button"
                      disabled={busy}
                      onClick={() => setFail.run(c, !on).then(() => state.reload())}
                      className={clsx(
                        'rounded-md border px-2 py-1 text-[11px] transition-colors disabled:opacity-50',
                        on
                          ? 'border-critical/60 bg-critical/15 text-critical'
                          : 'border-ink-600 text-ink-400 hover:bg-ink-800',
                      )}
                    >
                      {titleCase(c.replace(/_/g, ' '))}
                      {on && ' — failing'}
                    </button>
                  )
                })}
              </div>
              <p className="mt-1 text-[10px] leading-snug text-ink-500">
                A failed provider removes its features from the composite (they are renormalised, not
                zeroed), lowers the data-health score and is named on every affected assessment.
              </p>
            </div>

            {providers.data && (
              <ul className="space-y-0.5 border-t border-ink-700/40 pt-2">
                {providers.data.providers.map((p) => (
                  <li key={p.key} className="flex items-center gap-2 text-[11px]">
                    <span
                      className={clsx(
                        'h-1.5 w-1.5 shrink-0 rounded-full',
                        p.status === 'operational' ? 'bg-safe' : 'bg-critical',
                      )}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1 truncate text-ink-300">{p.name}</span>
                    <span className="shrink-0 text-ink-500">{p.features.length} features</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>

        {/* ----------------------------------------------------- models -- */}
        <Panel
          title="Risk model"
          subtitle="Swappable implementations behind one interface"
          icon={<BrainCircuit size={14} className="text-ink-400" />}
        >
          {!models.data ? (
            <LoadingBlock rows={3} />
          ) : (
            <div className="space-y-2">
              {models.data.models.map((m) => {
                const active = models.data!.active === m.kind
                return (
                  <div
                    key={m.kind}
                    className={clsx(
                      'rounded-lg border p-2.5',
                      active ? 'border-accent/60 bg-accent/8' : 'border-ink-700',
                      !m.available && 'opacity-60',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="text-xs font-semibold text-ink-50">{m.name}</span>
                        <span className="ml-1.5 font-mono text-[10px] text-ink-500">v{m.version}</span>
                      </div>
                      {active ? (
                        <Chip tone="info">active</Chip>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={!m.available || setModel.pending}
                          onClick={() => setModel.run(m.kind).then(() => { models.reload(); state.reload() })}
                        >
                          Use
                        </Button>
                      )}
                    </div>
                    <p className="mt-1 text-[11px] leading-snug text-ink-400">{m.description}</p>
                    <p className="mt-1 text-[10px] text-ink-500">
                      {m.trained_on
                        ? `Trained on: ${m.trained_on}`
                        : 'Rule-based — no training data involved.'}
                    </p>
                    {!m.available && m.unavailable_reason && (
                      <p className="mt-1 text-[10px] text-critical">{m.unavailable_reason}</p>
                    )}
                  </div>
                )
              })}
              <p className="text-[10px] leading-snug text-ink-500">
                Fallback chain: {models.data.fallback_chain.join(' → ')}. If the active model raises,
                PEHRA falls back and labels the prediction as a fallback with reduced confidence.
              </p>
              <ErrorBlock error={setModel.error} compact />
            </div>
          )}
        </Panel>
      </div>

      <WhatIfLab />
    </div>
  )
}

/* -------------------------------------------------------------------------- */

interface WhatIfSide {
  risk: number
  hazard: number
  exposure: number
  confidence: number
  severity: Severity
}

interface WhatIfResult {
  available: boolean
  reason?: string
  baseline: WhatIfSide
  modified: WhatIfSide
  delta: { risk: number; hazard: number; exposure: number; confidence: number }
  attribution: { factor: string; value: number; risk: number; delta: number; abs_delta: number }[]
  most_influential: { factor: string; delta: number } | null
  expected_alert_level: string | null
  expected_alert_reason: string[]
  note: string
}

function WhatIfLab() {
  const locations = useApi(() => api.locations(), { liveUpdate: false })
  const [locationId, setLocationId] = useState('')
  const [values, setValues] = useState<Record<string, number>>(
    Object.fromEntries(SLIDERS.map((s) => [s.key, 1])),
  )
  const [result, setResult] = useState<WhatIfResult | null>(null)

  useEffect(() => {
    if (!locationId && locations.data?.locations?.length) setLocationId(locations.data.locations[0].id)
  }, [locations.data, locationId])

  const whatIf = useMutation((body: Record<string, unknown>) => api.whatIf(body))

  const runWhatIf = async (next = values, id = locationId) => {
    if (!id) return
    const res = (await whatIf.run({ location_id: id, ...next })) as unknown as WhatIfResult | null
    if (res) setResult(res)
  }

  useEffect(() => {
    if (locationId) void runWhatIf(values, locationId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationId])

  const dirty = SLIDERS.some((s) => values[s.key] !== 1)

  return (
    <Panel
      title="What-if lab"
      subtitle="Re-runs the engine on modified inputs — nothing is stored and no alert can be created"
      icon={<FlaskConical size={14} className="text-ink-400" />}
    >
      <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-[10px] font-semibold tracking-wide text-ink-500 uppercase">
              Area
            </span>
            {locations.data ? (
              <select
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
                className="w-full rounded-md border border-ink-600 bg-ink-850 px-2 py-1.5 text-xs text-ink-100"
              >
                {locations.data.locations.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            ) : (
              <LoadingBlock rows={1} />
            )}
          </label>

          {SLIDERS.map((s) => (
            <label key={s.key} className="block">
              <span className="mb-1 flex items-baseline justify-between text-[10px] tracking-wide text-ink-500 uppercase">
                {s.label}
                <span className="font-mono text-ink-200">×{values[s.key].toFixed(2)}</span>
              </span>
              <input
                type="range"
                min={0}
                max={3}
                step={0.05}
                value={values[s.key]}
                onChange={(e) => setValues({ ...values, [s.key]: Number(e.target.value) })}
                onMouseUp={() => runWhatIf()}
                onTouchEnd={() => runWhatIf()}
                onKeyUp={() => runWhatIf()}
                className="w-full accent-[var(--color-accent)]"
              />
              <span className="text-[9px] text-ink-600">multiplies {s.affects}</span>
            </label>
          ))}

          <div className="flex gap-1.5">
            <Button size="sm" pending={whatIf.pending} onClick={() => runWhatIf()}>
              Recalculate
            </Button>
            {dirty && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  const reset = Object.fromEntries(SLIDERS.map((s) => [s.key, 1]))
                  setValues(reset)
                  void runWhatIf(reset)
                }}
              >
                Reset sliders
              </Button>
            )}
          </div>
          <ErrorBlock error={whatIf.error} compact />
        </div>

        <div>
          {!result ? (
            <EmptyState title="Move a slider to compare" detail="The baseline is the current live assessment for the selected area." />
          ) : !result.available ? (
            <EmptyState title="Cannot evaluate this area" detail={result.reason} />
          ) : (
            <div className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-3">
                <CompareCard title="Baseline" side={result.baseline} />
                <CompareCard title="What-if" side={result.modified} />
                <div className="panel-tight px-3 py-2">
                  <div className="text-[10px] tracking-wide text-ink-500 uppercase">Difference</div>
                  <div
                    className={clsx(
                      'font-mono text-2xl leading-none font-bold',
                      result.delta.risk > 0 ? 'text-critical' : result.delta.risk < 0 ? 'text-safe' : 'text-ink-300',
                    )}
                  >
                    {result.delta.risk > 0 ? '+' : ''}
                    {result.delta.risk.toFixed(1)}
                  </div>
                  <div className="mt-1 space-y-0.5 text-[10px] text-ink-500">
                    <div>hazard {result.delta.hazard >= 0 ? '+' : ''}{result.delta.hazard.toFixed(1)}</div>
                    <div>confidence {result.delta.confidence >= 0 ? '+' : ''}{result.delta.confidence.toFixed(1)}</div>
                  </div>
                </div>
              </div>

              {result.expected_alert_level && (
                <div
                  className="rounded-md border px-2.5 py-2"
                  style={{
                    borderColor: withAlpha(LEVEL_COLOR[result.expected_alert_level] ?? '#5b6b83', 0.45),
                    background: withAlpha(LEVEL_COLOR[result.expected_alert_level] ?? '#5b6b83', 0.08),
                  }}
                >
                  <div className="text-[11px] font-semibold" style={{ color: LEVEL_COLOR[result.expected_alert_level] }}>
                    Under these conditions the decision engine would propose: {result.expected_alert_level}
                  </div>
                  <ul className="mt-1 space-y-0.5">
                    {result.expected_alert_reason.map((r, i) => (
                      <li key={i} className="text-[11px] text-ink-300">
                        · {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <div className="mb-1 text-[10px] tracking-wide text-ink-500 uppercase">
                  Single-factor attribution — effect of each slider on its own
                </div>
                <div className="space-y-1">
                  {result.attribution.map((a) => {
                    const max = Math.max(...result.attribution.map((x) => x.abs_delta), 1)
                    const positive = a.delta >= 0
                    return (
                      <div key={a.factor} className="flex items-center gap-2">
                        <span className="w-28 shrink-0 truncate text-[11px] text-ink-300">
                          {titleCase(a.factor.replace(/_/g, ' '))}
                        </span>
                        <span className="w-10 shrink-0 font-mono text-[10px] text-ink-500">
                          ×{a.value.toFixed(2)}
                        </span>
                        <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-ink-800">
                          <div
                            className={clsx('h-full rounded-full', positive ? 'bg-critical/70' : 'bg-safe/70')}
                            style={{ width: `${Math.max(1, (a.abs_delta / max) * 100)}%` }}
                          />
                        </div>
                        <span className="w-12 shrink-0 text-right font-mono text-[11px] text-ink-200">
                          {a.delta >= 0 ? '+' : ''}
                          {fmtNumber(a.delta, 1)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>

              <p className="text-[10px] leading-snug text-ink-500">{result.note}</p>
            </div>
          )}
        </div>
      </div>
    </Panel>
  )
}

function CompareCard({ title, side }: { title: string; side: WhatIfSide }) {
  return (
    <div className="panel-tight px-3 py-2">
      <div className="text-[10px] tracking-wide text-ink-500 uppercase">{title}</div>
      <div className="mt-0.5 flex items-baseline gap-2">
        <span className="font-mono text-2xl leading-none font-bold" style={{ color: side.severity.color }}>
          {side.risk.toFixed(0)}
        </span>
        <SeverityBadge level={side.severity.key as SeverityKey} label={side.severity.label} size="sm" />
      </div>
      <div className="mt-1 space-y-0.5 text-[10px] text-ink-500">
        <div>hazard {side.hazard.toFixed(0)} · exposure {side.exposure.toFixed(0)}</div>
        <div>confidence {side.confidence.toFixed(0)}%</div>
      </div>
    </div>
  )
}
