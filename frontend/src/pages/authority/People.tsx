/**
 * Authority People screen (CD-08, CD-12).
 *
 * The control room's live view of every demo citizen persona:
 *   • a map with a marker per persona, coloured by connectivity state;
 *   • the live fix when one is fresh, otherwise the LAST KNOWN fix and how
 *     old it is — exactly what a rescue coordinator needs when the network
 *     drops;
 *   • a "RELAY VIA …" badge when a fix was forwarded over Bluetooth by a
 *     nearby PEHRA phone (SIMULATED for the prototype);
 *   • help requests with acknowledge / resolve actions.
 *
 * Honesty: every value is demo data (is_simulated: true).
 */
import 'leaflet/dist/leaflet.css'
import { BatteryLow, CheckCircle2, MapPin, Radio, Siren, Users } from 'lucide-react'
import { useMemo } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import { Button, Chip, EmptyState, ErrorBlock, LoadingBlock, Panel, StaleNotice } from '../../components/ui'
import { useTileAvailability } from '../../components/RiskMap'
import { api } from '../../lib/api'
import { relativeTime, withAlpha } from '../../lib/format'
import { useApi, useMutation } from '../../lib/hooks'
import { useAuth, useLive } from '../../lib/providers'
import type { CitizenEntry } from '../../lib/types'

const STATE_HEX: Record<string, string> = {
  online: '#22c55e',
  relay: '#38bdf8',
  stale: '#f59e0b',
  offline: '#ef4444',
  unseen: '#94a3b8',
  helped: '#f43f5e',
}

const MUMBAI_CENTER: [number, number] = [19.076, 72.8777]

function PersonCard({ p, onAck, onResolve, ackPending, resolvePending }: {
  p: CitizenEntry
  onAck: () => void
  onResolve: () => void
  ackPending: boolean
  resolvePending: boolean
}) {
  const help = p.help
  return (
    <div className={`rounded-lg border p-3 ${help?.status === 'requested' ? 'border-critical/50 bg-critical/10' : 'border-ink-600 bg-ink-850'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col">
          <span className="flex items-center gap-1.5 font-head text-sm font-bold text-ink-50">{p.codename}</span>
          <span className="text-[11px] text-ink-300">{p.full_name}</span>
          <span className="font-mono text-[9px] text-ink-500 uppercase">{p.ward_label} · {p.phone}</span>
        </div>
        <span className="flex shrink-0 flex-col items-end gap-1">
          <span
            className="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase"
            style={{ color: STATE_HEX[p.state] ?? '#94a3b8', background: withAlpha(STATE_HEX[p.state] ?? '#94a3b8', 0.15) }}
          >
            {p.state_label}
          </span>
          {p.battery != null && (
            <span className="flex items-center gap-1 font-mono text-[9px] text-ink-400">
              <BatteryLow size={11} aria-hidden /> {Math.round(p.battery)}%
            </span>
          )}
        </span>
      </div>

      <div className="mt-2 space-y-1 font-mono text-[10px] text-ink-300">
        <p className="flex items-center gap-1.5">
          <MapPin size={11} className="shrink-0 text-ink-500" aria-hidden />
          {p.fix ? `${p.fix.lat.toFixed(5)}N ${p.fix.lng.toFixed(5)}E · ±${Math.round(p.fix.accuracy)} m` : '—'}
          {p.is_baseline && <span className="text-ink-500">(registered area)</span>}
        </p>
        <p>
          Last seen: <span className={p.age_s != null && p.age_s > 30 ? 'text-moderate' : ''}>{relativeTime(p.last_seen_at)}</span>
          {p.last_fix_at ? ` · last fix ${relativeTime(p.last_fix_at)}` : ''}
        </p>
      </div>

      {p.state === 'relay' && (
        <p className="mt-2 flex items-center gap-1.5 rounded bg-info/10 px-2 py-1 font-mono text-[10px] font-bold text-info">
          <Radio size={12} aria-hidden /> RELAYED VIA {p.via_relay?.toUpperCase() ?? 'PEER'} (BLUETOOTH)
          {p.relayed_at ? ` · ${relativeTime(p.relayed_at)}` : ''}
        </p>
      )}

      {help && (
        <div className="mt-2 flex flex-col gap-1.5 rounded border border-critical/30 bg-critical/5 p-2">
          <span className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase text-critical">
            <Siren size={12} aria-hidden />
            {help.status} · {relativeTime(help.requested_at)}
          </span>
          {help.message && <p className="text-[11px] leading-snug text-ink-200">{help.message}</p>}
          {help.status === 'requested' && (
            <Button size="sm" variant="danger" pending={ackPending} onClick={onAck}>
              <CheckCircle2 size={13} /> Acknowledge — responding
            </Button>
          )}
          {help.status === 'acknowledged' && (
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[10px] text-moderate">HELPING · {help.ack_by ?? 'team'}</span>
              <Button size="sm" variant="ghost" pending={resolvePending} onClick={onResolve}>
                Mark resolved
              </Button>
            </div>
          )}
        </div>
      )}

      {!help && (
        <div className="mt-2 flex items-center gap-1.5 rounded bg-ink-900 px-2 py-1 font-mono text-[9px] text-ink-500">
          <CheckCircle2 size={11} className="text-safe" aria-hidden /> NO HELP REQUEST
        </div>
      )}
    </div>
  )
}

export default function People() {
  const { user } = useAuth()
  const { revision } = useLive()
  const { data, error, loading, stale, reload } = useApi(() => api.citizens(), {
    pollMs: 5000,
    liveUpdate: true,
    deps: [revision],
  })
  const ack = useMutation((id: string) => api.ackCitizenHelp(id, user?.full_name ?? 'Authority'))
  const resolve = useMutation((id: string) => api.resolveCitizenHelp(id))

  const people = useMemo(() => {
    if (!data) return []
    const order: Record<string, number> = { helped: 0, offline: 1, relay: 2, stale: 3, online: 4, unseen: 5 }
    return [...data.citizens].sort((a, b) => (order[a.state] ?? 9) - (order[b.state] ?? 9))
  }, [data])

  const tile = useTileAvailability('https://tile.openstreetmap.org/{z}/{x}/{y}.png')

  if (loading && !data) return <LoadingBlock label="Loading people…" rows={4} />
  if (error && !data) return <ErrorBlock error={error} onRetry={reload} />

  const countBy = (s: string) => data?.citizens.filter((c) => c.state === s).length ?? 0
  const helpCount = data?.citizens.filter((c) => c.help?.status === 'requested').length ?? 0

  return (
    <div className="flex flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Users size={18} className="text-accent-bright" aria-hidden />
          <h1 className="font-head text-sm font-bold tracking-tight uppercase">People & SOS</h1>
          <Chip tone="info" title="Live demo personas">
            {data?.count ?? 0} PERSONAS
          </Chip>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Chip tone="good">{countBy('online')} ONLINE</Chip>
          <Chip tone="info">{countBy('relay')} ON RELAY</Chip>
          <Chip tone="warn">{countBy('stale')} STALE</Chip>
          <Chip tone="danger">{countBy('offline')} OFFLINE</Chip>
          {helpCount > 0 && <Chip tone="danger" icon={<Siren size={10} />}>{helpCount} HELPING</Chip>}
        </div>
      </div>

      <StaleNotice stale={stale} />

      {error && <div className="text-xs text-moderate">{error.message}</div>}

      {people.length === 0 ? (
        <Panel title="No citizens connected">
          <EmptyState
            title="No persona is reporting yet"
            detail="Open the citizen mobile app (Person 1 – Person 3) and its location beacon will appear here within seconds."
          />
        </Panel>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-ink-600">
            <MapContainer center={MUMBAI_CENTER} zoom={11} className="z-0 h-[24rem] w-full" scrollWheelZoom>
              {tile === 'available' && (
                <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
              )}
              {tile !== 'available' && (
                <div className="flex h-full w-full items-center justify-center bg-ink-900">
                  <span className="rounded bg-ink-800 px-3 py-1.5 font-mono text-[11px] text-ink-400">BASEMAP OFFLINE — VECTORS ONLY</span>
                </div>
              )}
              {people.map((p) => (
                <CircleMarker
                  key={p.id}
                  center={[p.fix.lat, p.fix.lng]}
                  radius={p.help?.status === 'requested' ? 12 : 9}
                  pathOptions={{
                    color: STATE_HEX[p.state] ?? '#94a3b8',
                    fillColor: STATE_HEX[p.state] ?? '#94a3b8',
                    fillOpacity: p.help?.status === 'requested' ? 0.95 : 0.4,
                    weight: 2,
                  }}
                >
                  <Popup>
                    <div className="space-y-0.5 font-mono text-[11px]">
                      <span className="font-bold uppercase">{p.codename}</span>
                      <div>{p.full_name}</div>
                      <div className="text-[10px] text-gray-500">{p.ward_label}</div>
                      <div className="font-bold" style={{ color: STATE_HEX[p.state] }}>{p.state_label}</div>
                      {p.state === 'relay' && <div className="text-sky-500">Relayed via {p.via_relay}</div>}
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </MapContainer>
            <div className="flex items-center justify-between gap-2 bg-ink-800 px-2.5 py-1.5">
              <span className="font-mono text-[10px] text-ink-300">LIVE PERSONA POSITIONS · LAST KNOWN SHOWN WHEN STALE/OFFLINE</span>
              <span className="flex items-center gap-2 font-mono text-[9px] text-ink-400">
                <MapPin size={10} className="text-safe" /> ONLINE <MapPin size={10} className="text-accent-bright" /> RELAY
                <MapPin size={10} className="text-moderate" /> STALE <MapPin size={10} className="text-critical" /> OFFLINE
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
            {people.map((p) => (
              <PersonCard
                key={p.id}
                p={p}
                onAck={() => void ack.run(p.id).then(() => reload())}
                onResolve={() => void resolve.run(p.id).then(() => reload())}
                ackPending={ack.pending}
                resolvePending={resolve.pending}
              />
            ))}
          </div>

          <p className="font-mono text-[9px] leading-snug text-ink-500 uppercase">
            Demo personas only. A relay state means the fix was forwarded by a nearby PEHRA phone over Bluetooth
            (SIMULATED for the prototype). None of these are live real-world positions.
          </p>
        </>
      )}
    </div>
  )
}