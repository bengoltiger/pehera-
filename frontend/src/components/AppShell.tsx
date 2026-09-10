/**
 * Global chrome: data-honesty banner, the //OPS command header (mesh status,
 * threat-level pill, simulation clock, theme + language switches), and the
 * role-aware navigation.
 */
import {
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
  Moon,
  Radar,
  RotateCcw,
  ScrollText,
  Server,
  Siren,
  Sun,
  Waypoints,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { api } from '../lib/api'
import { fmtNumber } from '../lib/format'
import { useApi, useMutation } from '../lib/hooks'
import { useI18n } from '../lib/i18n'
import { useAuth, useLive } from '../lib/providers'
import { useTheme } from '../lib/theme'
import { Button, Chip, PeHraLogo, Spinner, StatusPip } from './ui'
import type { Lang } from '../lib/types'

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  roles?: string[]
}

const AUTHORITY_NAV: NavItem[] = [
  { to: '/authority', label: 'nav.overview', icon: <LayoutDashboard size={15} /> },
  { to: '/authority/sitrep', label: 'nav.sitrep', icon: <Radar size={15} /> },
  { to: '/authority/predict', label: 'nav.predict', icon: <Waypoints size={15} /> },
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
        <ChevronsRight size={12} className={clsxRot(open)} aria-hidden />
      </button>
      {open && (
        <p className="mx-auto max-w-4xl px-4 pb-2 text-center text-[11px] leading-relaxed text-moderate/90">
          {t('app.demoBannerDetail')}
        </p>
      )}
    </div>
  )
}

function clsxRot(open: boolean) {
  return open ? 'transition-transform rotate-90' : 'transition-transform'
}

function ConnectionPill() {
  const { connected, transport } = useLive()
  if (connected && transport === 'sse') {
    return <StatusPip tone="good" label="MESH:OK" ping className="hidden sm:inline-flex" />
  }
  if (connected && transport === 'polling') {
    return (
      <StatusPip tone="warn" label="POLLING" className="hidden sm:inline-flex" />
    )
  }
  return <StatusPip tone="danger" label="OFFLINE" ping />
}

/** Highest active threat across the network — the red "CRIT-L3" pill. */
function ThreatLevelPill() {
  const { data } = useApi(() => api.overview(), { pollMs: 15000 })
  if (!data) return null
  const m = data.metrics
  if (m.critical_zones > 0) {
    return <StatusPip tone="danger" label={`CRIT ×${m.critical_zones}`} ping />
  }
  if (m.high_zones > 0) {
    return <StatusPip tone="warn" label={`HIGH ×${m.high_zones}`} />
  }
  return <StatusPip tone="good" label="ALL CLEAR" />
}

function SimulationClock() {
  const { data } = useApi(() => api.simState(), { pollMs: 15000 })
  if (!data) return <div className="skeleton h-5 w-40" />
  const pct = data.total_ticks ? Math.round(((data.tick ?? 0) / data.total_ticks) * 100) : 0
  return (
    <div className="hidden items-center gap-2 xl:flex" title={data.narrative ?? undefined}>
      <Gauge size={13} className="text-ink-400" aria-hidden />
      <span className="text-xs text-ink-300">
        <span className="font-head font-semibold text-ink-100">{data.scenario_name ?? data.scenario_id}</span>
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
          className={clsxLang(l === lang)}
        >
          {l === 'en' ? 'EN' : 'हि'}
        </button>
      ))}
    </div>
  )
}

function clsxLang(active: boolean) {
  return `px-2 py-1 font-mono text-[11px] font-semibold uppercase transition-colors ${
    active ? 'bg-accent/25 text-accent-bright' : 'text-ink-400 hover:bg-ink-800'
  }`
}

function ThemeToggle() {
  const { theme, toggle } = useTheme()
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
      className="grid h-7 w-7 place-items-center rounded-md border border-ink-600 text-ink-300 transition-colors hover:bg-ink-800 hover:text-accent-bright"
    >
      {theme === 'dark' ? <Sun size={14} aria-hidden /> : <Moon size={14} aria-hidden />}
    </button>
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

const SECTION_TITLES: Record<string, string> = {
  '/authority': 'Command Overview',
  '/authority/sitrep': 'Sitrep // Command & Map',
  '/authority/predict': 'Predict // Telemetry Feed',
  '/authority/map': 'Command & Map',
  '/authority/queue': 'Priority Queue',
  '/authority/alerts': 'Alerts Console',
  '/authority/lab': 'Simulation Lab',
  '/citizen': 'Village Defense',
  '/citizen/evacuate': 'Evacuate',
}

export function AppShell({ children, nav = 'authority' }: { children: ReactNode; nav?: 'authority' | 'none' }) {
  const { user, signOut } = useAuth()
  const { t } = useI18n()
  const location = useLocation()
  const items = nav === 'authority' ? AUTHORITY_NAV.filter((i) => !i.roles || (user && i.roles.includes(user.role))) : []
  const sectionTitle = SECTION_TITLES[location.pathname] ?? 'Command & Map'

  return (
    <div className="flex h-full min-h-0 flex-col bg-ink-950">
      <DataHonestyBanner />

      <header className="flex shrink-0 items-center gap-3 border-b border-ink-700/60 bg-ink-900/95 px-3 py-2 backdrop-blur">
        <NavLink to="/" className="flex min-w-0 items-center gap-2.5">
          <PeHraLogo size={34} />
          <span className="hidden min-w-0 leading-none sm:block">
            <span className="flex items-baseline gap-1.5">
              <span className="font-head text-sm font-extrabold tracking-[0.12em] text-ink-50 uppercase">PEHRA</span>
              <span className="font-mono text-[11px] font-semibold tracking-[0.2em] text-accent-bright">//OPS</span>
            </span>
            <span className="mt-0.5 block truncate font-mono text-[10px] tracking-[0.08em] text-ink-400 uppercase">
              {sectionTitle}
            </span>
          </span>
        </NavLink>

        <div className="mx-1 hidden h-6 w-px bg-ink-700 md:block" />
        <SimulationClock />

        <div className="ml-auto flex items-center gap-2">
          <ConnectionPill />
          <ThreatLevelPill />
          <LangSwitch />
          <ThemeToggle />
          <ResetDemoButton />
          {user ? (
            <div className="flex items-center gap-2 border-l border-ink-700 pl-2">
              <div className="hidden text-right sm:block">
                <div className="text-xs leading-tight font-medium text-ink-100">{user.full_name}</div>
                <div className="font-mono text-[10px] text-ink-500 uppercase">{user.role}</div>
              </div>
              <Button size="sm" variant="ghost" icon={<LogOut size={13} />} onClick={signOut} title={t('action.signOut')} />
            </div>
          ) : (
            <NavLink to="/login" className="rounded-md border border-ink-600 px-2 py-1 text-xs text-ink-200 hover:bg-ink-800">
              {t('action.signIn')}
            </NavLink>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {items.length > 0 && (
          <nav className="hidden w-52 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-ink-700/60 bg-ink-900/60 p-2 lg:flex">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/authority'}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-accent/15 text-accent-bright'
                      : 'text-ink-300 hover:bg-ink-800 hover:text-ink-100'
                  }`
                }
              >
                {item.icon}
                {t(item.label)}
              </NavLink>
            ))}
          </nav>
        )}

        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">{children}</main>
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
                `flex shrink-0 flex-col items-center gap-0.5 rounded-md px-2.5 py-1 text-[10px] ${
                  isActive ? 'bg-accent/15 text-accent-bright' : 'text-ink-400'
                }`
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
        <PeHraLogo size={44} />
        <Spinner size={22} />
        <p className="font-mono text-xs">{label}</p>
      </div>
    </div>
  )
}
