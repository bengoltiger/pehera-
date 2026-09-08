/**
 * Alert operations (Sections 19–24, 28–32, 48–51).
 *
 * AI-assisted recommendations are shown as PROPOSALS. Only an authorised
 * officer pressing "Approve & issue" turns one into an official warning, and
 * every transition is recorded in the lifecycle audit trail below.
 */
import {
  BadgeCheck,
  Ban,
  Bell,
  CheckCircle2,
  Eye,
  FileSignature,
  Plus,
  Send,
  ShieldQuestion,
  Users,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { AlertComposer } from '../../components/AlertComposer'
import {
  Button,
  Chip,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  Panel,
  StaleNotice,
} from '../../components/ui'
import { api } from '../../lib/api'
import { LEVEL_COLOR, clsx, fmtDateTime, fmtPeople, relativeTime, titleCase, withAlpha } from '../../lib/format'
import { useApi, useMutation } from '../../lib/hooks'
import type { Alert } from '../../lib/types'

const FILTERS = [
  { key: 'active', label: 'Active' },
  { key: 'recommended', label: 'Awaiting approval' },
  { key: 'issued', label: 'Issued' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'all', label: 'All' },
] as const

export default function AlertsPage() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['key']>('active')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [composerOpen, setComposerOpen] = useState(false)

  const list = useApi(() => api.alerts({ status: filter, limit: 100 }), { deps: [filter] })
  const alerts = list.data?.alerts ?? []
  const selected = useMemo(
    () => alerts.find((a) => a.id === selectedId) ?? alerts[0] ?? null,
    [alerts, selectedId],
  )
  const pendingCount = alerts.filter((a) => a.status === 'recommended').length

  return (
    <div className="grid min-h-0 gap-3 p-3 lg:h-full lg:grid-cols-[24rem_1fr] lg:p-4">
      {/* ------------------------------------------------------- list ---- */}
      <div className="flex min-h-0 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={clsx(
                'rounded-md border px-2 py-1 text-[11px] font-medium transition-colors',
                filter === f.key
                  ? 'border-accent/60 bg-accent/20 text-accent-bright'
                  : 'border-ink-600 text-ink-400 hover:bg-ink-800',
              )}
            >
              {f.label}
              {f.key === 'recommended' && pendingCount > 0 && (
                <span className="ml-1 rounded bg-moderate/30 px-1 font-mono text-[9px] text-moderate">
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
          <Button
            size="sm"
            variant="primary"
            icon={<Plus size={12} />}
            onClick={() => setComposerOpen(true)}
            className="ml-auto"
          >
            Compose
          </Button>
        </div>

        <StaleNotice stale={list.stale} />

        <Panel dense className="min-h-0 flex-1" bodyClassName="overflow-y-auto">
          {list.loading && !list.data ? (
            <div className="p-3">
              <LoadingBlock rows={6} />
            </div>
          ) : alerts.length === 0 ? (
            <EmptyState
              icon={<Bell size={22} />}
              title="No alerts in this view"
              detail="The decision engine raises a recommendation when a trigger fires and confidence is sufficient. Advance the simulation to generate one."
            />
          ) : (
            <ul className="divide-y divide-ink-700/40">
              {alerts.map((a) => (
                <AlertRow
                  key={a.id}
                  alert={a}
                  selected={selected?.id === a.id}
                  onClick={() => setSelectedId(a.id)}
                />
              ))}
            </ul>
          )}
        </Panel>

        <p className="px-1 text-[10px] leading-snug text-ink-500">
          {list.data?.note ??
            'Recommended alerts are AI-assisted proposals awaiting authority approval.'}
        </p>
      </div>

      {/* ----------------------------------------------------- detail ---- */}
      <div className="min-h-0 overflow-y-auto">
        {selected ? (
          <AlertDetail alert={selected} onChanged={list.reload} />
        ) : (
          <Panel>
            <p className="text-sm text-ink-400">Select an alert to review it.</p>
          </Panel>
        )}
      </div>

      {composerOpen && (
        <AlertComposer
          onClose={() => setComposerOpen(false)}
          onCreated={() => {
            setComposerOpen(false)
            list.reload()
          }}
        />
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function AlertRow({ alert, selected, onClick }: { alert: Alert; selected: boolean; onClick: () => void }) {
  const color = LEVEL_COLOR[alert.level] ?? '#5b6b83'
  const isProposal = alert.status === 'recommended'
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={clsx(
          'w-full px-3 py-2.5 text-left transition-colors',
          selected ? 'bg-accent/10' : 'hover:bg-ink-850/60',
        )}
      >
        <div className="flex items-center gap-2">
          <span
            className="rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wide"
            style={{ color, background: withAlpha(color, 0.16), border: `1px solid ${withAlpha(color, 0.45)}` }}
          >
            {alert.level}
          </span>
          <span className="min-w-0 flex-1 truncate text-xs font-medium text-ink-100">
            {alert.location.name}
          </span>
          <span className="shrink-0 font-mono text-[10px] text-ink-500">{alert.risk_score.toFixed(0)}</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {isProposal ? (
            <Chip tone="warn" icon={<ShieldQuestion size={9} />}>
              awaiting approval
            </Chip>
          ) : (
            <Chip tone={alert.is_active ? 'good' : 'neutral'}>{titleCase(alert.status)}</Chip>
          )}
          {alert.is_ai_generated && <Chip tone="info">AI-assisted</Chip>}
          <span className="text-[10px] text-ink-500">{relativeTime(alert.created_at)}</span>
        </div>
        <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-ink-400">{alert.title}</p>
      </button>
    </li>
  )
}

/* -------------------------------------------------------------------------- */

function AlertDetail({ alert, onChanged }: { alert: Alert; onChanged: () => void }) {
  const full = useApi(() => api.alert(alert.id), { deps: [alert.id] })
  const a = full.data ?? alert
  const color = LEVEL_COLOR[a.level] ?? '#5b6b83'

  const issue = useMutation(() => api.issueAlert(a.id, 'Approved in the command centre.'))
  const resolve = useMutation(() => api.patchAlert(a.id, { status: 'resolved', reason: 'Resolved by authority.' }))
  const cancelAlert = useMutation(() =>
    api.patchAlert(a.id, { status: 'cancelled', reason: 'Cancelled by authority.' }),
  )
  const redeliver = useMutation(() => api.deliverAlert(a.id))

  const canIssue = ['recommended', 'pending_approval'].includes(a.status)
  const canResolve = !['resolved', 'cancelled', 'expired'].includes(a.status)

  const after = async (fn: () => Promise<unknown>) => {
    await fn()
    full.reload()
    onChanged()
  }

  return (
    <div className="space-y-3">
      <div
        className="rounded-xl border p-4"
        style={{ borderColor: withAlpha(color, 0.45), background: withAlpha(color, 0.08) }}
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="rounded px-2 py-0.5 text-xs font-bold tracking-wide"
                style={{ color, background: withAlpha(color, 0.18), border: `1px solid ${withAlpha(color, 0.5)}` }}
              >
                {a.level}
              </span>
              <h2 className="text-sm font-bold text-ink-50">{a.title}</h2>
            </div>
            <p className="mt-1 text-[11px] text-ink-400">
              {a.where} · created {fmtDateTime(a.created_at)} · risk{' '}
              <span className="font-mono">{a.risk_score.toFixed(0)}/100</span> · confidence{' '}
              <span className="font-mono">{a.confidence.toFixed(0)}%</span>
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-1.5">
            {canIssue && (
              <Button
                variant="success"
                size="sm"
                icon={<BadgeCheck size={13} />}
                pending={issue.pending}
                onClick={() => after(issue.run)}
              >
                Approve &amp; issue
              </Button>
            )}
            {!canIssue && a.status !== 'resolved' && (
              <Button size="sm" icon={<Send size={12} />} pending={redeliver.pending} onClick={() => after(redeliver.run)}>
                Re-send
              </Button>
            )}
            {canResolve && (
              <Button size="sm" icon={<CheckCircle2 size={12} />} pending={resolve.pending} onClick={() => after(resolve.run)}>
                Resolve
              </Button>
            )}
            {canIssue && (
              <Button
                size="sm"
                variant="ghost"
                icon={<Ban size={12} />}
                pending={cancelAlert.pending}
                onClick={() => after(cancelAlert.run)}
              >
                Reject
              </Button>
            )}
          </div>
        </div>

        <ErrorBlock error={issue.error ?? resolve.error ?? cancelAlert.error ?? redeliver.error} compact />

        {a.status === 'recommended' && (
          <p className="mt-2 rounded-md border border-moderate/40 bg-moderate/10 px-2.5 py-1.5 text-[11px] text-moderate">
            This is an <strong>AI-assisted recommendation</strong>, not an official warning. It has not
            been sent to anyone. A human decision is required.
          </p>
        )}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Citizen-facing message" icon={<Eye size={14} className="text-ink-400" />}>
          <CitizenCard alert={a} />
        </Panel>

        <div className="space-y-3">
          <Panel title="Why this alert fired" icon={<FileSignature size={14} className="text-ink-400" />}>
            <p className="text-xs leading-relaxed text-ink-200">{a.trigger_reason}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(a.trigger_kinds ?? []).map((k) => (
                <Chip key={k} tone="info">
                  {k.replace(/_/g, ' ')}
                </Chip>
              ))}
            </div>
            <dl className="mt-3 space-y-1 text-[11px]">
              <div className="flex justify-between gap-2">
                <dt className="text-ink-500">Geofence</dt>
                <dd className="text-ink-200">
                  {String(a.geofence?.kind ?? 'radius')}
                  {a.geofence?.radius_km ? ` · ${Number(a.geofence.radius_km).toFixed(1)} km` : ''}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-ink-500">Estimated people in zone</dt>
                <dd className="text-ink-200">
                  <Users size={10} className="mr-1 inline" aria-hidden />
                  {fmtPeople(a.estimated_exposed_population)}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-ink-500">Audience</dt>
                <dd className="text-ink-200">{(a.target_audience ?? []).join(', ')}</dd>
              </div>
              {a.approved_by && (
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-500">Approved by</dt>
                  <dd className="text-ink-200">
                    {a.approved_by} · {fmtDateTime(a.approved_at)}
                  </dd>
                </div>
              )}
            </dl>
          </Panel>

          <Panel title="Simulated delivery" icon={<Send size={14} className="text-ink-400" />}>
            <Deliveries alert={a} />
          </Panel>
        </div>
      </div>

      <Panel title="Lifecycle audit trail" subtitle="Every state change, who made it and why">
        <LifecycleTimeline alert={a} />
      </Panel>
    </div>
  )
}

function CitizenCard({ alert }: { alert: Alert }) {
  const color = LEVEL_COLOR[alert.level] ?? '#5b6b83'
  const rows: [string, string][] = [
    ['WHAT', alert.what],
    ['WHERE', alert.where],
    ['WHEN', alert.when],
    ['WHY', alert.why],
    ['WHAT TO DO', alert.what_to_do],
  ]
  return (
    <div className="space-y-2.5">
      <div
        className="rounded-lg border px-3 py-2.5"
        style={{ borderColor: withAlpha(color, 0.4), background: withAlpha(color, 0.07) }}
      >
        <p className="text-xs leading-relaxed text-ink-100">{alert.message}</p>
        {alert.message_hi && (
          <p className="mt-2 border-t border-ink-700/40 pt-2 text-xs leading-relaxed text-ink-300">
            {alert.message_hi}
          </p>
        )}
      </div>

      <dl className="space-y-1.5">
        {rows
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className="grid grid-cols-[5.5rem_1fr] gap-2">
              <dt className="text-[10px] font-semibold tracking-wide text-ink-500">{k}</dt>
              <dd className="text-[11px] leading-snug text-ink-200">{v}</dd>
            </div>
          ))}
      </dl>

      {(alert.recommended_actions ?? []).length > 0 && (
        <div>
          <div className="mb-1 text-[10px] font-semibold tracking-wide text-ink-500">
            RECOMMENDED ACTIONS
          </div>
          <ul className="space-y-0.5">
            {alert.recommended_actions.map((act, i) => (
              <li key={i} className="flex gap-1.5 text-[11px] text-ink-200">
                <span className="text-accent-bright">›</span>
                {act}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Deliveries({ alert }: { alert: Alert }) {
  const rows = alert.deliveries ?? []
  if (rows.length === 0) {
    return (
      <p className="text-xs text-ink-400">
        Nothing has been dispatched yet. Delivery runs when the alert is issued.
      </p>
    )
  }
  const acks = alert.acknowledgements ?? []
  return (
    <div className="space-y-2">
      <ul className="space-y-1">
        {rows.map((d, i) => (
          <li key={i} className="flex items-center gap-2 text-[11px]">
            <span
              className={clsx(
                'h-1.5 w-1.5 shrink-0 rounded-full',
                d.status === 'sent' || d.status === 'delivered' ? 'bg-safe' : 'bg-critical',
              )}
              aria-hidden
            />
            <span className="w-16 shrink-0 text-ink-200">{d.channel_label ?? d.channel}</span>
            <span className="min-w-0 flex-1 truncate text-ink-500" title={d.detail}>
              {d.detail}
            </span>
            <span className="shrink-0 font-mono text-ink-400">{fmtPeople(d.recipient_count)}</span>
          </li>
        ))}
      </ul>
      <div className="rounded-md border border-moderate/40 bg-moderate/10 px-2.5 py-1.5 text-[10px] leading-snug text-moderate">
        SIMULATED DELIVERY — no push notification, SMS or email left this machine. Recipient counts
        are modelled, not measured.
      </div>
      {alert.funnel && (
        <div>
          <div className="mb-1 text-[10px] font-semibold tracking-wide text-ink-500 uppercase">
            Acknowledgement funnel
          </div>
          <div className="space-y-1">
            {(
              [
                ['Issued to', alert.funnel.issued],
                ['Delivered', alert.funnel.delivered],
                ['Opened', alert.funnel.opened],
                ['Acknowledged', alert.funnel.acknowledged],
              ] as [string, number][]
            ).map(([label, n]) => (
              <div key={label} className="flex items-center gap-2 text-[11px]">
                <span className="w-24 shrink-0 text-ink-400">{label}</span>
                <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-ink-800">
                  <div
                    className="h-full rounded-full bg-accent/70"
                    style={{
                      width: `${Math.max(1, (n / Math.max(1, alert.funnel!.issued)) * 100)}%`,
                    }}
                  />
                </div>
                <span className="w-16 shrink-0 text-right font-mono text-ink-200">{fmtPeople(n)}</span>
              </div>
            ))}
          </div>
          <p className="mt-1 text-[10px] text-ink-500">{alert.funnel.note}</p>
        </div>
      )}
      <p className="text-[11px] text-ink-400">
        Individual acknowledgements recorded:{' '}
        <span className="font-mono text-ink-200">{acks.length}</span>
        {acks.length > 0 && ` · latest ${relativeTime(acks[acks.length - 1].at)}`}
      </p>
    </div>
  )
}

function LifecycleTimeline({ alert }: { alert: Alert }) {
  const rows = alert.timeline ?? []
  if (rows.length === 0) return <EmptyState title="No transitions recorded yet" />
  return (
    <ol className="relative space-y-3 border-l border-ink-700 pl-4">
      {rows.map((t, i) => (
        <li key={i} className="relative">
          <span
            className="absolute top-1 -left-[21px] h-2.5 w-2.5 rounded-full border-2 border-ink-900"
            style={{ background: LEVEL_COLOR[t.to_level ?? ''] ?? '#5b6b83' }}
            aria-hidden
          />
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="text-xs font-medium text-ink-100">
              {t.from_status ? `${t.from_status} → ${t.to_status}` : t.to_status}
            </span>
            {t.to_level && t.to_level !== t.from_level && (
              <Chip tone="warn">
                {t.from_level ? `${t.from_level} → ` : ''}
                {t.to_level}
              </Chip>
            )}
            <span className="text-[10px] text-ink-500">{fmtDateTime(t.at)}</span>
          </div>
          <p className="mt-0.5 text-[11px] leading-snug text-ink-400">
            <span className="text-ink-300">
              {t.actor} ({t.actor_role})
            </span>{' '}
            — {t.reason}
          </p>
        </li>
      ))}
    </ol>
  )
}
