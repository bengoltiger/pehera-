import { KeyRound, LogIn, Moon, ShieldCheck, Sun, User as UserIcon } from 'lucide-react'
import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { DataHonestyBanner } from '../components/AppShell'
import { Button, Chip, ErrorBlock, Panel, PeHraLogo } from '../components/ui'
import { api } from '../lib/api'
import { useApi } from '../lib/hooks'
import { useAuth } from '../lib/providers'
import { useTheme } from '../lib/theme'

export default function Login() {
  const { signIn, user } = useAuth()
  const { theme, toggle } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('authority')
  const [password, setPassword] = useState('authority123')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<{ message: string } | null>(null)
  const accounts = useApi(() => api.demoAccounts(), { liveUpdate: false })

  const from = (location.state as { from?: string } | null)?.from

  // Backend of any shape → friendly empty state instead of `.accounts.map` crash.
  const demoAccounts: { username: string; password: string; role: string; description: string }[] =
    accounts.data?.accounts ?? []

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

  return (
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
        </motion.div>
      </div>
    </div>
  )
}
