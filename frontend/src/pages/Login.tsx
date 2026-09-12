import { KeyRound, LogIn, MapPin, Moon, Server, ShieldCheck, Sun, User as UserIcon, Users } from 'lucide-react'
import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { DataHonestyBanner } from '../components/AppShell'
import { Button, Chip, ErrorBlock, Panel, PeHraLogo } from '../components/ui'
import { api, getApiBase, setApiBase } from '../lib/api'
import { useApi } from '../lib/hooks'
import { isCitizenKiosk } from '../lib/platform'
import { useAuth } from '../lib/providers'
import { useTheme } from '../lib/theme'

const QUICK_PERSONAS = [
  { id: 'persona_1', code: 'PERSON 1', ward: 'Kurla Ward' },
  { id: 'persona_2', code: 'PERSON 2', ward: 'Colaba Ward' },
  { id: 'persona_3', code: 'PERSON 3', ward: 'Mahim Ward' },
]

export default function Login() {
  const { signIn, user } = useAuth()
  const { theme, toggle } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('authority')
  const [password, setPassword] = useState('authority123')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<{ message: string } | null>(null)
  const [showBackend, setShowBackend] = useState(false)
  const [serverUrl, setServerUrl] = useState<string>(() => getApiBase())
  const accounts = useApi(() => api.demoAccounts(), { liveUpdate: false })

  const from = (location.state as { from?: string } | null)?.from

  // One tap = signed in as that persona's own citizen account, straight to /citizen.
  // Each persona maps to a distinct seeded account (persona_1=meera, etc.) so P1/P2/P3
  // are genuinely different people; fall back to the first citizen for older servers.
  const citizenAccount = (personaId: string) =>
    accounts.data?.accounts.find((a) => a.role === 'citizen' && a.persona_id === personaId) ??
    accounts.data?.accounts.find((a) => a.role === 'citizen')
  const connectPersona = async (persona: (typeof QUICK_PERSONAS)[number]) => {
    const account = citizenAccount(persona.id)
    if (!account) {
      setError({ message: 'Demo accounts not loaded yet — check the API URL (server icon).' })
      return
    }
    setPending(true)
    setError(null)
    try {
      try {
        localStorage.setItem('pehra.active_persona', persona.id)
      } catch {
        /* ignore */
      }
      await signIn(account.username, account.password)
      navigate('/citizen', { replace: true })
    } catch (err) {
      setError({ message: err instanceof Error ? err.message : 'Could not connect as this persona.' })
    } finally {
      setPending(false)
    }
  }

  // Backend of any shape → friendly empty state instead of `.accounts.map` crash.
  const demoAccounts: {
    username: string
    password: string
    role: string
    description: string
    persona_id?: string
  }[] = accounts.data?.accounts ?? []

  useEffect(() => {
    if (!user) return
    navigate(from ?? (user.role === 'citizen' ? '/citizen' : '/authority'), { replace: true })
  }, [user, navigate, from])

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setPending(true)
    setError(null)
    try {
      const u = await signIn(username, password)
      navigate(from ?? (u.role === 'citizen' ? '/citizen' : '/authority'), { replace: true })
    } catch (err) {
      setError({ message: (err as Error).message })
    } finally {
      setPending(false)
    }
  }

  return isCitizenKiosk() ? (
    <div className="flex h-[100dvh] min-h-0 flex-col bg-ink-950">
      <DataHonestyBanner />
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto p-4">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="w-full max-w-md"
        >
          {/* ------------------------------------ citizen-only (APK) ---- */}
          <Panel className="border-accent/40">
            <div className="mb-3 flex items-center gap-3">
              <PeHraLogo size={36} />
              <div className="min-w-0">
                <h1 className="flex items-baseline gap-1.5 font-head text-base font-extrabold tracking-[0.12em] text-ink-50 uppercase">
                  PEHRA
                  <span className="font-mono text-[11px] font-semibold tracking-[0.2em] text-accent-bright">
                    //PEOPLE
                  </span>
                </h1>
                <p className="mt-0.5 font-mono text-[9px] tracking-[0.06em] text-ink-400">
                  CITIZEN APP · DEMO BUILD · LOGIN IS PERSONA-ONLY
                </p>
              </div>
            </div>

            <p className="mb-3 text-[11px] leading-snug text-ink-400">
              Tap a persona to sign in as that citizen and connect to your PEHRA server. The server URL is saved on
              this device — set it once.
            </p>

            <div className="mb-3 rounded-md border border-ink-700 bg-ink-850 p-2">
              <div className="mb-1 flex items-center gap-1.5">
                <Server size={12} className="text-ink-400" aria-hidden />
                <span className="hud-label font-mono text-[9px] tracking-wider text-ink-400 uppercase">
                  Backend server
                </span>
              </div>
              <div className="flex gap-1.5">
                <input
                  value={serverUrl}
                  onChange={(e) => setServerUrl(e.target.value)}
                  placeholder="https://your-backend.onrender.com"
                  autoComplete="url"
                  className="min-w-0 flex-1 rounded border border-ink-600 bg-ink-900 px-2 py-1.5 text-sm text-ink-100 outline-none focus:border-accent"
                />
                <Button
                  size="sm"
                  onClick={() => {
                    if (serverUrl.trim()) setApiBase(serverUrl)
                  }}
                >
                  Save
                </Button>
              </div>
              <p className="mt-1.5 font-mono text-[9px] text-ink-400">
                {getApiBase()
                  ? `Current: ${getApiBase()} · saved on this device`
                  : 'Not set — type your live PEHRA URL above and tap Save (the app reloads).'}
              </p>
            </div>

            <ErrorBlock error={error} compact />

            <div className="grid grid-cols-3 gap-2">
              {QUICK_PERSONAS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  disabled={pending}
                  onClick={() => void connectPersona(p)}
                  className="flex flex-col items-center gap-1 rounded-md border border-ink-700 bg-ink-850 px-2 py-3 text-center transition-colors hover:border-accent/50 hover:bg-ink-800 disabled:opacity-40"
                >
                  <span className="font-head text-sm font-bold text-ink-50">{p.code.replace('PERSON ', 'P')}</span>
                  <span className="flex items-center gap-0.5 font-mono text-[9px] text-ink-400">
                    <MapPin size={9} aria-hidden /> {p.ward.replace(' Ward', '')}
                  </span>
                  <span className="mt-1 font-mono text-[9px] tracking-wider text-accent-bright uppercase">
                    {pending ? 'Connecting…' : 'Connect'}
                  </span>
                </button>
              ))}
            </div>

            <p className="mt-3 flex items-start gap-1.5 text-[10px] leading-relaxed text-ink-500">
              <ShieldCheck size={11} className="mt-0.5 shrink-0" aria-hidden />
              Personas are simulated citizens. This build enables citizen access only — no authority login.
            </p>
          </Panel>
        </motion.div>
      </div>
    </div>
  ) : (
    <div className="flex h-full min-h-0 flex-col bg-ink-950">
      <DataHonestyBanner />
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto p-4">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="relative w-full max-w-4xl"
        >
          <button
            type="button"
            onClick={toggle}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            className="absolute -top-1 right-0 z-10 grid h-8 w-8 place-items-center rounded-md border border-ink-600 bg-ink-900 text-ink-300 transition-colors hover:bg-ink-800 hover:text-accent-bright"
          >
            {theme === 'dark' ? <Sun size={14} aria-hidden /> : <Moon size={14} aria-hidden />}
          </button>

          {/* backend URL: point the deployed SPA at any PEHRA API, no redeploy needed */}
          <button
            type="button"
            onClick={() => setShowBackend((v) => !v)}
            aria-label="Backend API URL"
            title={getApiBase() ? `API: ${getApiBase()}` : 'Backend API not configured'}
            className="absolute top-8 right-0 z-10 grid h-8 w-8 place-items-center rounded-md border border-ink-600 bg-ink-900 text-ink-300 transition-colors hover:bg-ink-800 hover:text-accent-bright"
          >
            <Server size={14} aria-hidden />
          </button>

          {showBackend && (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                setApiBase(serverUrl)
              }}
              className="absolute top-[4.5rem] right-0 z-20 w-80 rounded-md border border-ink-600 bg-ink-900 p-3 shadow-xl"
            >
              <p className="mb-1 hud-label text-[10px] tracking-wider text-ink-400 uppercase">
                PEHRA backend API
              </p>
              <input
                value={serverUrl}
                onChange={(e) => setServerUrl(e.target.value)}
                placeholder="https://your-backend.onrender.com"
                autoComplete="url"
                className="w-full rounded border border-ink-600 bg-ink-850 px-2 py-1.5 text-xs text-ink-100 outline-none focus:border-accent"
              />
              <div className="mt-2 flex items-center gap-2">
                <Button size="sm" type="submit" icon={<Server size={12} />}>
                  Apply &amp; reload
                </Button>
                <button
                  type="button"
                  onClick={() => {
                    setServerUrl('')
                    setApiBase('')
                  }}
                  className="text-[11px] text-ink-500 transition-colors hover:text-ink-300"
                >
                  Use same origin
                </button>
              </div>
              <p className="mt-2 text-[10px] leading-relaxed text-ink-500">
                {getApiBase()
                  ? `Current: ${getApiBase()}`
                  : 'Not set — the app is calling its own origin (/api), which is why requests fail here.'}
              </p>
            </form>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            {/* ------------------------------------------------ sign-in ---- */}
            <Panel className="self-start">
              <div className="mb-4 flex items-center gap-3">
                <PeHraLogo size={40} />
                <div className="min-w-0">
                  <h1 className="flex items-baseline gap-1.5 font-head text-base leading-tight font-extrabold tracking-[0.12em] text-ink-50 uppercase">
                    PEHRA
                    <span className="font-mono text-[11px] font-semibold tracking-[0.2em] text-accent-bright">//OPS</span>
                  </h1>
                  <p className="mt-0.5 font-mono text-[10px] tracking-[0.06em] text-ink-400">
                    PREDICTIVE EARLY-WARNING · HYPERLOCAL RISK
                  </p>
                </div>
              </div>

              <form onSubmit={submit} className="space-y-3">
                <label className="block">
                  <span className="mb-1 block hud-label text-ink-400">Username</span>
                  <div className="flex items-center gap-2 rounded border border-ink-600 bg-ink-850 px-2.5 py-2 transition-colors focus-within:border-accent">
                    <UserIcon size={14} className="text-ink-500" aria-hidden />
                    <input
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      autoComplete="username"
                      className="w-full bg-transparent text-sm text-ink-100 outline-none"
                    />
                  </div>
                </label>

                <label className="block">
                  <span className="mb-1 block hud-label text-ink-400">Password</span>
                  <div className="flex items-center gap-2 rounded border border-ink-600 bg-ink-850 px-2.5 py-2 transition-colors focus-within:border-accent">
                    <KeyRound size={14} className="text-ink-500" aria-hidden />
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete="current-password"
                      className="w-full bg-transparent text-sm text-ink-100 outline-none"
                    />
                  </div>
                </label>

                <ErrorBlock error={error} compact />

                <Button type="submit" variant="primary" pending={pending} icon={<LogIn size={14} />} className="w-full">
                  Sign in
                </Button>
              </form>

              <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-ink-500">
                <ShieldCheck size={12} className="mt-0.5 shrink-0" aria-hidden />
                Passwords are bcrypt-hashed and sessions use signed JWTs. Role-based access is enforced on
                the server, not in this browser.
              </p>
            </Panel>

            {/* ------------------------------------------- instant personas ---- */}
            <div className="flex flex-col gap-4 self-start">
              <Panel className="self-start border-accent/40">
                <div className="mb-1.5 flex items-center gap-1.5">
                  <Users size={14} className="text-accent-bright" aria-hidden />
                  <h2 className="hud-label tracking-wider text-ink-300 uppercase">Instant persona login</h2>
                </div>
                <p className="mb-2 text-[11px] leading-snug text-ink-400">
                  One tap signs you in as the demo citizen with that persona's identity — straight to the live server.
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {QUICK_PERSONAS.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      disabled={pending || !demoAccounts.some((a) => a.role === 'citizen')}
                      onClick={() => void connectPersona(p)}
                      className="flex flex-col items-center gap-1 rounded-md border border-ink-700 bg-ink-850 px-2 py-2 text-center transition-colors hover:border-accent/50 hover:bg-ink-800 disabled:opacity-40"
                    >
                      <span className="font-head text-xs font-bold text-ink-50">{p.code.replace('PERSON ', 'P')}</span>
                      <span className="flex items-center gap-0.5 font-mono text-[9px] text-ink-400">
                        <MapPin size={9} aria-hidden /> {p.ward.replace(' Ward', '')}
                      </span>
                    </button>
                  ))}
                </div>
                {!demoAccounts.some((a) => a.role === 'citizen') && !accounts.loading && (
                  <p className="mt-2 font-mono text-[9px] text-ink-400">
                    Demo accounts not loaded — check the API URL (server icon), then Retry.
                  </p>
                )}
              </Panel>

              {/* ------------------------------------------- demo accounts ---- */}
              <Panel
                title="Demo accounts"
                subtitle="Seeded prototype users — click to fill the form"
                className="self-start"
              >
              {accounts.data && demoAccounts.length > 0 ? (
                <ul className="space-y-2">
                  {demoAccounts.map((a, i) => (
                    <motion.li
                      key={a.username}
                      initial={{ opacity: 0, x: 8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.05 * i, duration: 0.2 }}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setUsername(a.username)
                          setPassword(a.password)
                        }}
                        className="w-full rounded-md border border-ink-700 bg-ink-850 px-3 py-2 text-left transition-colors hover:border-accent/50 hover:bg-ink-800"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-xs text-ink-100">{a.username}</span>
                          <Chip tone={a.role === 'citizen' ? 'info' : a.role === 'authority' ? 'warn' : 'danger'}>
                            {a.role}
                          </Chip>
                        </div>
                        <p className="mt-0.5 text-[11px] text-ink-400">{a.description}</p>
                        <p className="mt-0.5 font-mono text-[10px] text-ink-500">{a.password}</p>
                      </button>
                    </motion.li>
                  ))}
                </ul>
              ) : (
                <ErrorBlock error={accounts.error} onRetry={accounts.reload} compact />
              )}
              <p className="mt-3 text-[11px] leading-relaxed text-ink-500">
                {accounts.data?.note ??
                  'Seeded prototype accounts only. Real deployments create users through the admin API.'}
              </p>
            </Panel>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
