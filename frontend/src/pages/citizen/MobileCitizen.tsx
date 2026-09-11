/**
 * PEHRA citizen mobile app — the screen wrapped by the Android APK.
 *
 * What this screen does (citizen-only, mobile-view):
 *
 *  • Bluetooth gate  — the app asks to enable Bluetooth up front (the relay
 *    capability the authority relies on when the network drops). Real OS
 *    permission on the APK; SIMULATED relay on other browsers, always labelled.
 *  • Persona switcher — Person 1 / Person 2 / Person 3 so a single demo phone
 *    can play every citizen. Fictional demo personas only.
 *  • Location beacon  — a heartbeat every few seconds to the control room with
 *    the live fix, battery and Bluetooth state.
 *  • Last-known position — if the phone loses the network the app stops
 *    sending fixes (the authority keeps the last one) and offers a Bluetooth
 *    peer relay: the nearest PEHRA phone forwards the last known position.
 *  • Help request  — "I NEED HELP" sends the citizen's location; the authority
 *    acknowledges/resolves on its People screen, which the phone sees live.
 *
 * Honesty: all personas, fixes and relays are demo data (is_simulated: true).
 */
import { AnimatePresence, motion } from 'framer-motion'
import {
  Bluetooth,
  CheckCircle2,
  Crosshair,
  MapPin,
  Radio,
  RefreshCw,
  Settings,
  Siren,
  Users,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Button, Chip } from '../../components/ui'
import { api, getApiBase, setApiBase } from '../../lib/api'
import {
  detectBt,
  getStoredBtMode,
  requestBluetoothEnable,
  simulatedPeers,
  turnBluetoothOff,
  type BtState,
} from '../../lib/bluetooth'
import { useLive } from '../../lib/providers'
import type { CitizenConnectivity, CitizenEntry, CitizenHelp, PersonasResponse } from '../../lib/types'

/* -------------------------------------------------------------------------- */
/* GPS + battery helpers                                                       */
/* -------------------------------------------------------------------------- */

interface Fix {
  lat: number
  lng: number
  accuracy: number
}

function useGpsFix(): { fix: Fix | null; error: string | null } {
  const [fix, setFix] = useState<Fix | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      setError('GPS unavailable in this browser — the control room sees your registered area instead.')
      return
    }
    const watchId = navigator.geolocation.watchPosition(
      (pos) =>
        setFix({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
      (err) => {
        if (err.code === 1) setError('Location permission denied — reporting is based on your registered area.')
      },
      { enableHighAccuracy: true, maximumAge: 60000, timeout: 15000 },
    )
    return () => navigator.geolocation.clearWatch(watchId)
  }, [])
  return { fix, error }
}

function useBattery(): number | null {
  const [battery, setBattery] = useState<number | null>(null)
  useEffect(() => {
    const nav = navigator as any
    if (typeof nav.getBattery !== 'function') return
    let cancelled = false
    nav.getBattery().then((b: any) => {
      if (cancelled) return
      setBattery(Math.round(b.level * 100))
      const onLevel = () => setBattery(Math.round(b.level * 100))
      b.addEventListener?.('levelchange', onLevel)
    })
    return () => {
      cancelled = true
    }
  }, [])
  return battery
}

/* -------------------------------------------------------------------------- */

const HELP_KEY = (id: string) => `pehra.help.${id}`
const ANNOUNCED_KEY = (id: string) => `pehra.announced.${id}`
const FIX_KEY = (id: string) => `pehra.lastfix.${id}`

function loadJSON<T>(raw: string | null, fallback: T): T {
  try {
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

export function MobileCitizen(_props: { user?: { home_location_id?: string | null; full_name?: string } }) {
  const { subscribe, revision } = useLive()
  const { fix, error: gpsError } = useGpsFix()
  const battery = useBattery()

  const [personas, setPersonas] = useState<PersonasResponse | null>(null)
  const [personasError, setPersonasError] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string>(() => {
    try {
      return localStorage.getItem('pehra.active_persona') ?? 'persona_1'
    } catch {
      return 'persona_1'
    }
  })
  const [announced, setAnnounced] = useState<Record<string, CitizenConnectivity>>({})
  const [lastFixByPersona, setLastFixByPersona] = useState<Record<string, Fix>>({})
  const [helpByPersona, setHelpByPersona] = useState<Record<string, CitizenHelp>>({})
  const [bt, setBt] = useState<BtState>({ mode: 'off', enabled: false, permission: 'n/a', label: 'Bluetooth OFF', note: '' })
  const [showSettings, setShowSettings] = useState(false)
  const [serverUrl, setServerUrl] = useState('')
  const [sending, setSending] = useState(false)
  const [lastBeatAt, setLastBeatAt] = useState<string | null>(null)
  const [lastBeatPersona, setLastBeatPersona] = useState<CitizenEntry | null>(null)
  const [liveBanner, setLiveBanner] = useState<string | null>(null)

  const active = personas?.personas.find((p) => p.id === activeId) ?? null
  const activeAnnounced: CitizenConnectivity = announced[activeId] ?? 'online'
  const offlinePersonas = personas?.personas.filter((p) => announced[p.id] === 'offline') ?? []

  /* ---------------- boot: personas, bluetooth, settings ---------------- */
  useEffect(() => {
    let cancelled = false
    api
      .personas()
      .then((p) => {
        if (cancelled) return
        setPersonas(p)
        const ann: Record<string, CitizenConnectivity> = {}
        const fixes: Record<string, Fix> = {}
        const help: Record<string, CitizenHelp> = {}
        for (const persona of p.personas) {
          ann[persona.id] = loadJSON<CitizenConnectivity>(
            localStorage.getItem(ANNOUNCED_KEY(persona.id)),
            'online',
          )
          fixes[persona.id] = loadJSON<Fix>(localStorage.getItem(FIX_KEY(persona.id)), persona.baseline_fix)
          help[persona.id] = loadJSON<CitizenHelp>(localStorage.getItem(HELP_KEY(persona.id)), null)
        }
        setAnnounced(ann)
        setLastFixByPersona(fixes)
        setHelpByPersona(help)
      })
      .catch((e) => setPersonasError(e instanceof Error ? e.message : 'Could not load personas.'))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const det = detectBt()
    setBt((prev) =>
      prev.mode === 'off'
        ? { mode: getStoredBtMode(), enabled: getStoredBtMode() !== 'off', permission: 'n/a', label: det.label, note: '' }
        : prev,
    )
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem('pehra.active_persona', activeId)
    } catch {
      /* ignore */
    }
  }, [activeId])

  /* ---------------- live stream: citizen.* events ---------------------- */
  useEffect(() => {
    return subscribe((e) => {
      if (e.type === 'citizen.help') {
        const data = e.data as { persona_id?: string; status?: string; ack_by?: string; message_out?: string }
        const pid = data.persona_id
        const pstatus = data.status
        if (pid && pstatus) {
          setHelpByPersona((prev) => {
            const existing = prev[pid] ?? null
            if (existing && existing.status === pstatus) return prev
            const next = {
              ...(existing ?? { status: 'requested' as const, requested_at: e.at, message: '', fix: { lat: 0, lng: 0, accuracy: 0 }, is_baseline: true, ack_by: null, ack_at: null, resolved_by: null, resolved_at: null }),
              status: pstatus as NonNullable<CitizenHelp>['status'],
              ...(pstatus === 'acknowledged' ? { ack_by: data.ack_by ?? 'Authority' } : {}),
            } as CitizenHelp
            try {
              localStorage.setItem(HELP_KEY(pid), JSON.stringify(next))
            } catch {
              /* ignore */
            }
            return { ...prev, [pid]: next }
          })
        }
        if (data.message_out) setLiveBanner(data.message_out)
      }
      if (e.type === 'citizen.connection') {
        const data = e.data as { persona_id?: string; message?: string }
        if (data.message) setLiveBanner(data.message)
      }
    })
  }, [subscribe, revision])

  const saveFix = useCallback((id: string, f: Fix) => {
    setLastFixByPersona((prev) => {
      const next = { ...prev, [id]: f }
      try {
        localStorage.setItem(FIX_KEY(id), JSON.stringify(f))
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  /* ---------------- heartbeat beacon ------------------------------------ */
  const beat = useCallback(
    async (ann?: CitizenConnectivity) => {
      if (!active) return
      setSending(true)
      const annOverride = ann ?? (navigator.onLine === false ? 'offline' : (announced[activeId] ?? 'online'))
      const fixNow = fix
      const body: Record<string, unknown> = {
        persona_id: activeId,
        announced: annOverride,
        ble_enabled: bt.enabled,
        bt_mode: bt.mode,
        battery,
        note: gpsError ?? undefined,
      }
      if (annOverride !== 'offline' && fixNow) body.fix = fixNow
      try {
        const res = await api.citizenHeartbeat(body)
        setLastBeatAt(res.persona.last_seen_at ?? new Date().toISOString())
        setLastBeatPersona(res.persona)
        if (fixNow && annOverride !== 'offline') saveFix(activeId, fixNow)
        if (res.persona.help) {
          setHelpByPersona((prev) => ({ ...prev, [activeId]: res.persona.help }))
        }
      } catch (err) {
        setLiveBanner(err instanceof Error ? err.message : 'Heartbeat failed — is the server reachable?')
      } finally {
        setSending(false)
      }
    },
    [active, activeId, announced, battery, bt, fix, gpsError, saveFix],
  )

  useEffect(() => {
    if (!active) return
    void beat()
    const id = window.setInterval(() => void beat(), 8000)
    return () => window.clearInterval(id)
  }, [active, activeId, beat])

  const onNetworkOffline = useCallback(() => {
    setAnnounced((prev) => {
      const next = { ...prev, [activeId]: 'offline' as CitizenConnectivity }
      try {
        localStorage.setItem(ANNOUNCED_KEY(activeId), JSON.stringify('offline'))
      } catch {
        /* ignore */
      }
      return next
    })
    void beat('offline')
  }, [activeId, beat])

  const onNetworkOnline = useCallback(() => {
    setAnnounced((prev) => {
      const next = { ...prev, [activeId]: 'online' as CitizenConnectivity }
      try {
        localStorage.setItem(ANNOUNCED_KEY(activeId), JSON.stringify('online'))
      } catch {
        /* ignore */
      }
      return next
    })
    void beat('online')
  }, [activeId, beat])

  const relayPersona = useCallback(
    async (offlineId: string) => {
      if (!active) return
      const offline = personas?.personas.find((p) => p.id === offlineId)
      if (!offline) return
      await api.citizenHeartbeat({
        persona_id: offlineId,
        announced: 'relay',
        via_relay: activeId,
        fix: lastFixByPersona[offlineId] ?? offline.baseline_fix,
        ble_enabled: bt.enabled,
        bt_mode: bt.mode,
        note: `Relayed over Bluetooth via ${active.codename}`,
      })
      setHelpByPersona((prev) => ({ ...prev, [offlineId]: null }))
      setLiveBanner(`${offline.codename} is now relayed via ${active.codename} (Bluetooth, SIMULATED).`)
    },
    [active, lastFixByPersona, personas?.personas, bt, activeId],
  )

  const askHelp = useCallback(
    async (message: string) => {
      if (!active) return
      try {
        const res = await api.citizenHelp(activeId, message)
        if (res.help) {
          setHelpByPersona((prev) => ({ ...prev, [activeId]: res.help }))
          try {
            localStorage.setItem(HELP_KEY(activeId), JSON.stringify(res.help))
          } catch {
            /* ignore */
          }
        }
        setLiveBanner(`${active.codename} — help request sent to the control room.`)
      } catch (err) {
        setLiveBanner(err instanceof Error ? err.message : 'Could not send the help request.')
      }
    },
    [active, activeId],
  )

  const clearHelp = useCallback(
    async (personaId: string) => {
      try {
        await api.resolveCitizenHelp(personaId)
        setHelpByPersona((prev) => ({ ...prev, [personaId]: null }))
        try {
          localStorage.removeItem(HELP_KEY(personaId))
        } catch {
          /* ignore */
        }
      } catch {
        /* ignore */
      }
    },
    [],
  )

  const enableBt = async () => {
    const state = await requestBluetoothEnable()
    setBt(state)
  }

  const peers = active ? simulatedPeers(active.codename, personas?.personas.filter((p) => p.id !== activeId).map((p) => p.codename) ?? []) : []

  if (personasError && !personas) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <p className="text-xs text-ink-300">Could not reach the PEHRA server.</p>
        <Button onClick={() => window.location.reload()}>Retry</Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 p-3 pb-8">
      <div className="flex flex-col gap-1.5 rounded-lg border border-ink-600 bg-ink-850 p-3 shadow-md">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 font-head text-sm font-bold tracking-[0.08em] text-ink-50 uppercase">
            <Users size={16} className="text-accent-bright" aria-hidden />
            PEHRA //People
          </span>
          <div className="flex items-center gap-1.5">
            <Chip tone={bt.enabled ? 'good' : 'warn'}>{bt.enabled ? bt.label : 'BLUETOOTH OFF'}</Chip>
            <button
              type="button"
              onClick={() => {
                setServerUrl(getApiBase())
                setShowSettings((s) => !s)
              }}
              aria-label="Server settings"
              className="grid h-7 w-7 place-items-center rounded-md border border-ink-600 text-ink-300 hover:bg-ink-800 hover:text-accent-bright"
            >
              <Settings size={14} />
            </button>
          </div>
        </div>
        {showSettings && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="flex flex-col gap-2 overflow-hidden">
            <input
              type="text"
              value={serverUrl}
              onChange={(e) => setServerUrl(e.target.value)}
              placeholder="https://your-pehra-server.example"
              className="rounded-md border border-ink-600 bg-ink-900 px-2 py-1.5 font-mono text-[11px] text-ink-100"
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => setApiBase(serverUrl)}>
                Save server URL
              </Button>
              <Button size="sm" variant="ghost" onClick={async () => {
                try {
                  const h = await api.health()
                  setLiveBanner(`Server reachable — ${h.app} ${h.version}, ${h.status}.`)
                } catch (e) {
                  setLiveBanner(e instanceof Error ? e.message : 'Server unreachable.')
                }
              }}>
                Test connection
              </Button>
            </div>
            <p className="text-[10px] leading-snug text-ink-400">
              The APK talks to any live PEHRA server. Save the URL once and the whole app (streams included) reconnects
              there.
            </p>
          </motion.div>
        )}
        <p className="text-[11px] leading-snug text-ink-400">
          The control room sees exactly who <strong className="text-ink-200">you are</strong> showing as — pick a
          persona and it becomes your phone's identity for this demo.
        </p>
      </div>

      {/* persona switcher */}
      {personas && (
        <div className="grid grid-cols-3 gap-2">
          {personas.personas.map((p) => {
            const state = announced[p.id] ?? 'online'
            const activePersona = p.id === activeId
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => setActiveId(p.id)}
                className={`flex flex-col items-center gap-1 rounded-lg border p-2.5 text-center transition-colors ${
                  activePersona ? 'border-accent/60 bg-accent/15' : 'border-ink-600 bg-ink-850 hover:bg-ink-800'
                }`}
              >
                <span className="font-head text-xs font-bold text-ink-50">{p.codename.replace('PERSON', 'P')}</span>
                <span className="font-mono text-[9px] text-ink-400">{p.full_name.split(' ')[0]}</span>
                <span
                  className={`font-mono text-[9px] font-bold ${
                    state === 'online' ? 'text-safe' : state === 'offline' ? 'text-critical' : state === 'relay' ? 'text-accent-bright' : 'text-moderate'
                  }`}
                >
                  {state.toUpperCase()}
                </span>
              </button>
            )
          })}
        </div>
      )}

      {/* Bluetooth gate */}
      {!bt.enabled && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col gap-2 rounded-lg border border-accent/50 bg-accent/10 p-3"
        >
          <div className="flex items-center gap-2">
            <Bluetooth size={20} className="text-accent-bright" aria-hidden />
            <span className="font-head text-xs font-bold tracking-[0.08em] text-ink-50 uppercase">
              Enable Bluetooth so PEHRA can relay your position
            </span>
          </div>
          <ul className="list-inside list-disc text-[11px] leading-snug text-ink-300">
            <li>When your network drops, a nearby PEHRA phone forwards your last known location.</li>
            <li>Your phone also relays for someone next to you running the same app.</li>
            <li>You can switch it off any time — it only relays location, nothing else.</li>
          </ul>
          <div className="flex gap-2">
            <Button icon={<Bluetooth size={14} />} onClick={enableBt} className="flex-1">
              Enable Bluetooth
            </Button>
            <Button variant="ghost" onClick={() => setBt(turnBluetoothOff())}>
              Skip
            </Button>
          </div>
          <p className="font-mono text-[9px] text-ink-400">REAL OS PERMISSION ON THE APK · SIMULATED ELSEWHERE</p>
        </motion.div>
      )}

      {/* Bluetooth status + relay peers */}
      {bt.enabled && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-ink-600 bg-ink-850 p-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-ink-100">
              <Bluetooth size={14} className="text-accent-bright" aria-hidden />
              {bt.label}
            </span>
            <button
              type="button"
              onClick={() => setBt(turnBluetoothOff())}
              className="font-mono text-[9px] text-ink-400 underline hover:text-critical"
            >
              switch off
            </button>
          </div>
          <p className="text-[10px] leading-snug text-ink-400">{bt.note}</p>
          {bt.mode === 'simulated' && (
            <p className="rounded bg-ink-900 px-2 py-1 font-mono text-[9px] text-ink-400">
              NEARBY PEHRA PHONES: {peers.length ? peers.map((p) => `${p.id} · ${-1 * p.rssi_dbm * -1} dBm`).join(' , ') : 'none'} (SIMULATED DEMO)
            </p>
          )}
        </div>
      )}

      <AnimatePresence>
        {liveBanner && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-md border border-accent/50 bg-accent/10 px-2.5 py-1.5 font-mono text-[10px] text-accent-bright"
          >
            {liveBanner}
          </motion.div>
        )}
      </AnimatePresence>

      {/* location beacon */}
      <div className="flex flex-col gap-2 rounded-lg border border-ink-600 bg-ink-850 p-3 shadow-md">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 font-mono text-[11px] font-bold tracking-[0.1em] text-ink-100 uppercase">
            <Crosshair size={15} className="text-accent-bright" aria-hidden />
            {activeAnnounced === 'offline' ? 'NETWORK LOST' : 'SENDING MY LOCATION'}
          </span>
          <Chip tone={sending ? 'neutral' : activeAnnounced === 'offline' ? 'danger' : 'good'}>
            {sending ? '…' : activeAnnounced === 'offline' ? 'OFFLINE' : lastBeatAt ? 'BEACONING' : 'ARMING'}
          </Chip>
        </div>

        <div className="flex items-center gap-2">
          {activeAnnounced === 'offline' ? (
            <WifiOff size={18} className="text-critical" aria-hidden />
          ) : (
            <Wifi size={18} className="text-safe" aria-hidden />
          )}
          <p className="min-w-0 flex-1 text-[11px] leading-snug text-ink-300">
            {activeAnnounced === 'offline'
              ? 'Your phone lost its network. The control room keeps your LAST KNOWN location and the time it was seen.'
              : fix
                ? `Beacon: ${fix.lat.toFixed(5)}N ${fix.lng.toFixed(5)}E · ±${Math.round(fix.accuracy)} m`
                : `Registered area: ${active?.ward_label ?? 'Mumbai'} (waiting for GPS) — ${gpsError ?? ''}`.trim()}
          </p>
        </div>
        {(lastBeatPersona?.last_fix_at || lastBeatAt) && (
          <p className="font-mono text-[9px] text-ink-400">
            Last seen by control room:{' '}
            {lastBeatPersona?.last_seen_at ?? lastBeatAt} · announced {announced[activeId] ?? 'online'}
          </p>
        )}
        <div className="flex gap-2">
          <Button size="sm" variant={activeAnnounced === 'offline' ? 'danger' : 'ghost'} onClick={onNetworkOffline}>
            Simulate network drop
          </Button>
          {activeAnnounced === 'offline' && (
            <Button size="sm" onClick={onNetworkOnline}>
              <RefreshCw size={13} /> Reconnect
            </Button>
          )}
        </div>
      </div>

      {/* BLE relay for offline personas */}
      {offlinePersonas.length > 0 && bt.enabled && (
        <div className="flex flex-col gap-2 rounded-lg border border-accent/50 bg-accent/8 p-3">
          <span className="flex items-center gap-1.5 font-mono text-[11px] font-bold tracking-[0.1em] text-accent-bright uppercase">
            <Radio size={15} aria-hidden />
            Bluetooth relay available
          </span>
          {offlinePersonas.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => void relayPersona(p.id)}
              className="flex items-center justify-between rounded-md border border-ink-600 bg-ink-850 px-2.5 py-2 text-left transition-colors hover:bg-ink-800"
            >
              <span className="flex flex-col">
                <span className="text-xs font-semibold text-ink-100">
                  Relay {p.codename}'s last position
                </span>
                <span className="font-mono text-[9px] text-ink-400">
                  via {active?.codename ?? 'your phone'} · Bluetooth · SIMULATED
                </span>
              </span>
              <Bluetooth size={16} className="text-accent-bright" aria-hidden />
            </button>
          ))}
        </div>
      )}

      {/* HELP / SOS */}
      <SosCard
        help={helpByPersona[activeId] ?? null}
        onRequest={() => void askHelp(`I need help. Position: ${fix ? `${fix.lat.toFixed(5)}, ${fix.lng.toFixed(5)}` : active?.ward_label ?? 'registered area'}.`)}
        onClear={() => void clearHelp(activeId)}
        disabled={!active}
        offline={activeAnnounced === 'offline'}
      />

      {/* demo honesty footer */}
      <div className="flex items-start gap-2 rounded-lg border border-ink-800 bg-ink-900 p-2.5">
        <MapPin size={14} className="mt-0.5 shrink-0 text-ink-500" aria-hidden />
        <p className="font-mono text-[9px] leading-relaxed text-ink-500">
          DEMO: Personas, fixes below and BLE relays are fictional demo data (is_simulated: true). Nothing is a live
          real-world position. Heartbeats go to /api/citizens/heartbeat on your selected server.
        </p>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function SosCard({
  help,
  onRequest,
  onClear,
  disabled,
  offline,
}: {
  help: CitizenHelp
  onRequest: () => void
  onClear: () => void
  disabled: boolean
  offline: boolean
}) {
  const status = help?.status ?? null
  return (
    <div
      className={`flex flex-col gap-2 rounded-lg border p-3 shadow-md ${
        status ? 'glow-critical border-critical/50 bg-critical/12' : 'border-ink-600 bg-ink-850'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Siren size={16} className="text-critical" aria-hidden />
          <span className="hud-label tracking-wider text-critical">I NEED HELP</span>
        </span>
        {status && (
          <Chip tone={status === 'resolved' ? 'good' : status === 'acknowledged' ? 'warn' : 'danger'}>
            {status.toUpperCase()}
          </Chip>
        )}
      </div>

      {status ? (
        <div className="flex flex-col gap-1.5 text-[11px] leading-snug text-ink-200">
          {status === 'requested' && <p>Request sent — the control room is responding.</p>}
          {status === 'acknowledged' && (
            <p className="flex items-center gap-1.5 rounded bg-moderate/10 px-2 py-1 font-mono text-[10px] text-moderate">
              <CheckCircle2 size={12} aria-hidden />
              ACKNOWLEDGED BY {help?.ack_by ?? 'AUTHORITY'} · HELP IS ON THE WAY
            </p>
          )}
          {status === 'resolved' && <p>Resolved by the control room. You are marked safe.</p>}
          <div className="flex gap-2 pt-0.5">
            {status === 'requested' && (
              <Button size="sm" variant="danger" onClick={onClear}>
                Mark resolved (demo)
              </Button>
            )}
          </div>
        </div>
      ) : (
        <>
          <p className="text-[11px] leading-snug text-ink-400">
            Trapped, injured or cannot walk out? This sends your location to the control room — they can see exactly
            where you are, even from your last known position if your network is down.
          </p>
          <motion.button
            type="button"
            whileTap={{ scale: 0.97 }}
            disabled={disabled}
            onClick={onRequest}
            className="flex h-14 w-full items-center justify-center gap-2 rounded-lg bg-critical text-ink-50 font-mono text-xs font-bold tracking-[0.15em] uppercase shadow-lg transition-colors hover:bg-critical/90 disabled:opacity-40"
          >
            <Siren size={18} className="animate-pulse" aria-hidden />
            Send my location for help
          </motion.button>
          {offline && (
            <p className="font-mono text-[9px] text-ink-400 uppercase">
              Note: this phone is offline — relay your position via a nearby phone first.
            </p>
          )}
        </>
      )}
    </div>
  )
}