/**
 * Global chrome: the data-honesty banner, the simulation clock, connection
 * status, language switch and the role-aware navigation.
 */
import {
  Activity,
  AlertTriangle,
  BarChart3,
  ChevronsRight,
  ClipboardList,
  FlaskConical,
  Gauge,
  History,
  LayoutDashboard,
  ListOrdered,
  LogOut,
  Map as MapIcon,
  Radio,
  RotateCcw,
  ScrollText,
  Server,
  Siren,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { api } from '../lib/api'
import { clsx, fmtNumber } from '../lib/format'
import { useApi, useMutation } from '../lib/hooks'
import { useI18n } from '../lib/i18n'
import { useAuth, useLive } from '../lib/providers'
import { Button, Chip, Spinner } from './ui'
import type { Lang } from '../lib/types'

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  roles?: string[]
}

const AUTHORITY_NAV: NavItem[] = [
  { to: '/authority', label: 'nav.overview', icon: <LayoutDashboard size={15} /> },
  { to: '/authority/map', label: 'nav.map', icon: <MapIcon size={15} /> },
  { to: '/authority/queue', label: 'nav.queue', icon: <ListOrdered size={15} /> },
  { to: '/authority/alerts', label: 'nav.alerts', icon: <Siren size={15} /> },
  { to: '/authority/lab', label: 'nav.lab', icon: <FlaskConical size={15} /> },
]

/* Screens are added to the navigation only once they are actually implemented —
   PEHRA never ships a menu entry that leads to an empty or fake page. */
export const PLANNED_NAV: NavItem[] = [
  { to: '/authority/incidents', label: 'nav.incidents', icon: <ClipboardList size={15} /> },
  { to: '/authority/analytics', label: 'nav.analytics', icon: <BarChart3 size={15} /> },
  { to: '/authority/replay', label: 'nav.replay', icon: <History size={15} /> },
  { to: '/authority/system', label: 'nav.system', icon: <Server size={15} /> },
  { to: '/authority/audit', label: 'nav.audit', icon: <ScrollText size={15} /> },
]

/* -------------------------------------------------------------------------- */

export function DataHonestyBanner() {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-moderate/30 bg-moderate/12">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-center gap-2 px-3 py-1 text-[11px] font-semibold tracking-wide text-moderate uppercase hover:bg-moderate/10"
      >
        <AlertTriangle size={12} aria-hidden />
        {t('app.demoBanner')}
        <ChevronsRight size={12} className={clsx('transition-transform', open && 'rotate-90')} aria-hidden />
      </button>
      {open && (
        <p className="mx-auto max-w-4xl px-4 pb-2 text-center text-[11px] leading-relaxed text-moderate/90">
          {t('app.demoBannerDetail')}
        </p>
      )}
    </div>
  )
}

function ConnectionPill() {
  const { connected, transport } = useLive()
  if (connected && transport === 'sse') {
    return (
      <Chip tone="good" icon={<Radio size={10} />} title="Live server-sent event stream connected">
        Live
      </Chip>
    )
  }
  if (connected && transport === 'polling') {
    return (
      <Chip tone="warn" icon={<Wifi size={10} />} title="Event stream unavailable — polling every 5 seconds instead">
        Polling
      </Chip>
    )
  }
  return (
    <Chip tone="danger" icon={<WifiOff size={10} />} title="No connection to the PEHRA server">
      Disconnected
    </Chip>
  )
}

function SimulationClock() {
  const { data } = useApi(() => api.simState(), { pollMs: 15000 })
  if (!data) return <div className="skeleton h-5 w-40" />
  const pct = data.total_ticks ? Math.round(((data.tick ?? 0) / data.total_ticks) * 100) : 0
  return (
    <div className="hidden items-center gap-2 md:flex" title={data.narrative ?? undefined}>
      <Gauge size={13} className="text-ink-400" aria-hidden />
      <span className="text-xs text-ink-300">
        <span className="font-medium text-ink-100">{data.scenario_name ?? data.scenario_id}</span>
        <span className="mx-1.5 text-ink-600">·</span>
        <span className="font-mono">
          T{data.tick}/{data.total_ticks}
        </span>
        <span className="mx-1.5 text-ink-600">·</span>
        <span className="font-mono text-ink-400">
          {data.elapsed_label ?? `+${fmtNumber((data.tick ?? 0) * (data.tick_minutes ?? 15))}m`}
        </span>
      </span>
      <div className="h-1 w-16 overflow-hidden rounded-full bg-ink-800">
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
      {data.connectivity !== 'online' && (
        <Chip tone={data.connectivity === 'offline' ? 'danger' : 'warn'}>{data.connectivity}</Chip>
      )}
      {Object.keys(data.forced_failures ?? {}).length > 0 && (
        <Chip tone="danger" title={Object.keys(data.forced_failures).join(', ')}>
          {Object.keys(data.forced_failures).length} failure
        </Chip>
      )}
    </div>
  )
}

function LangSwitch() {
  const { lang, setLang } = useI18n()
  return (
    <div className="flex overflow-hidden rounded-md border border-ink-600" role="group" aria-label="Language">
      {(['en', 'hi'] as Lang[]).map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => setLang(l)}
          aria-pressed={lang === l}
          className={clsx(
            'px-2 py-1 text-[11px] font-medium uppercase transition-colors',
            lang === l ? 'bg-accent/25 text-accent-bright' : 'text-ink-400 hover:bg-ink-800',
          )}
        >
          {l === 'en' ? 'EN' : 'हि'}
        </button>
      ))}
    </div>
  )
}

export function ResetDemoButton() {
  const { can } = useAuth()
  const { t } = useI18n()
  const reset = useMutation((scenarioId?: string) => api.resetDemo(scenarioId))
  const [confirming, setConfirming] = useState(false)
  if (!can('authority', 'administrator')) return null

  if (confirming) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="hidden text-[11px] text-ink-400 lg:inline">Clear all demo state?</span>
        <Button
          size="sm"
          variant="danger"
          pending={reset.pending}
          onClick={async () => {
            await reset.run(undefined)
            setConfirming(false)
          }}
        >
          Confirm
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
          Cancel
        </Button>
      </div>
    )
  }
  return (
    <Button
      size="sm"
      variant="ghost"
      icon={<RotateCcw size={13} />}
      onClick={() => setConfirming(true)}
      title="Restore a known demo state: clears predictions, alerts, threat cells and overrides."
    >
      <span className="hidden lg:inline">{t('action.resetDemo')}</span>
    </Button>
  )
}

/* -------------------------------------------------------------------------- */

export function AppShell({ children, nav = 'authority' }: { children: ReactNode; nav?: 'authority' | 'none' }) {
  const { user, signOut } = useAuth()
  const { t } = useI18n()
  const location = useLocation()
  const items = nav === 'authority' ? AUTHORITY_NAV.filter((i) => !i.roles || (user && i.roles.includes(user.role))) : []

  return (
    <div className="flex h-full min-h-0 flex-col bg-ink-950">
      <DataHonestyBanner />

      <header className="flex shrink-0 items-center gap-3 border-b border-ink-700/60 bg-ink-900 px-3 py-2">
        <NavLink to="/" className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-accent/20 text-accent-bright">
            <Activity size={16} aria-hidden />
          </span>
          <span className="leading-none">
            <span className="block text-sm font-bold tracking-tight text-ink-50">PEHRA</span>
            <span className="hidden text-[10px] text-ink-500 sm:block">Hyperlocal early warning</span>
          </span>
        </NavLink>

        <div className="mx-2 hidden h-6 w-px bg-ink-700 md:block" />
        <SimulationClock />

        <div className="ml-auto flex items-center gap-2">
          <ConnectionPill />
          <LangSwitch />
          <ResetDemoButton />
          {user ? (
            <div className="flex items-center gap-2 border-l border-ink-700 pl-2">
              <div className="hidden text-right sm:block">
                <div className="text-xs leading-tight font-medium text-ink-100">{user.full_name}</div>
                <div className="text-[10px] text-ink-500 capitalize">{user.role}</div>
              </div>
              <Button size="sm" variant="ghost" icon={<LogOut size={13} />} onClick={signOut} title={t('action.signOut')} />
            </div>
          ) : (
            <NavLink
              to="/login"
              className="rounded-md border border-ink-600 px-2 py-1 text-xs text-ink-200 hover:bg-ink-800"
            >
              {t('action.signIn')}
            </NavLink>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {items.length > 0 && (
          <nav className="hidden w-48 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-ink-700/60 bg-ink-900/60 p-2 lg:flex">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/authority'}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium transition-colors',
                    isActive ? 'bg-accent/15 text-accent-bright' : 'text-ink-300 hover:bg-ink-800 hover:text-ink-100',
                  )
                }
              >
                {item.icon}
                {t(item.label)}
              </NavLink>
            ))}
          </nav>
        )}

        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto" key={location.pathname}>
          {children}
        </main>
      </div>

      {/* compact nav for narrow screens */}
      {items.length > 0 && (
        <nav className="flex shrink-0 gap-1 overflow-x-auto border-t border-ink-700/60 bg-ink-900 px-2 py-1.5 lg:hidden">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/authority'}
              className={({ isActive }) =>
                clsx(
                  'flex shrink-0 flex-col items-center gap-0.5 rounded-md px-2.5 py-1 text-[10px]',
                  isActive ? 'bg-accent/15 text-accent-bright' : 'text-ink-400',
                )
              }
            >
              {item.icon}
              {t(item.label)}
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  )
}

export function FullPageLoader({ label = 'Starting PEHRA…' }: { label?: string }) {
  return (
    <div className="grid h-full place-items-center bg-ink-950">
      <div className="flex flex-col items-center gap-3 text-ink-400">
        <Spinner size={22} />
        <p className="text-xs">{label}</p>
      </div>
    </div>
  )
}
