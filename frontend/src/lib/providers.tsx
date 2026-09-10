/**
 * Application-wide providers: authentication, language, engine config and the
 * live event stream. Kept in one file so the provider tree stays readable.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api, apiUrl, PehraError, getToken, setToken } from './api'
import { I18nContext, translate } from './i18n'
import { ThemeProvider } from './theme'
import type { EngineConfig, Lang, User } from './types'

/* ========================================================================== *
 * Auth
 * ========================================================================== */
interface AuthValue {
  user: User | null
  loading: boolean
  error: string | null
  signIn: (username: string, password: string) => Promise<User>
  signOut: () => void
  can: (...roles: User['role'][]) => boolean
}

const AuthContext = createContext<AuthValue>({
  user: null,
  loading: true,
  error: null,
  signIn: async () => {
    throw new Error('not ready')
  },
  signOut: () => {},
  can: () => false,
})

export const useAuth = () => useContext(AuthContext)

/* ========================================================================== *
 * Engine config (risk bands, thresholds, hazard definitions)
 * ========================================================================== */
const ConfigContext = createContext<{ config: EngineConfig | null; error: string | null }>({
  config: null,
  error: null,
})
export const useEngineConfig = () => useContext(ConfigContext)

/* ========================================================================== *
 * Realtime event bus (SSE with an automatic polling fallback)
 * ========================================================================== */
export interface LiveEvent {
  type: string
  at: string
  is_simulated: boolean
  data: Record<string, unknown>
}

type Listener = (e: LiveEvent) => void

interface LiveValue {
  connected: boolean
  transport: 'sse' | 'polling' | 'disconnected'
  lastEvent: LiveEvent | null
  /** Monotonic counter — bump it in a dependency array to refetch. */
  revision: number
  subscribe: (fn: Listener) => () => void
  /** Force everything listening to refetch (after a local mutation). */
  invalidate: () => void
}

const LiveContext = createContext<LiveValue>({
  connected: false,
  transport: 'disconnected',
  lastEvent: null,
  revision: 0,
  subscribe: () => () => {},
  invalidate: () => {},
})

export const useLive = () => useContext(LiveContext)

/* ========================================================================== */

export function AppProviders({ children }: { children: ReactNode }) {
  /* ---- language ------------------------------------------------------- */
  const [lang, setLangState] = useState<Lang>(() => {
    try {
      const saved = localStorage.getItem('pehra.lang') as Lang | null
      if (saved === 'en' || saved === 'hi') return saved
    } catch {
      /* ignore */
    }
    return 'en'
  })
  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try {
      localStorage.setItem('pehra.lang', l)
    } catch {
      /* ignore */
    }
    document.documentElement.lang = l
  }, [])
  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])
  const i18n = useMemo(
    () => ({ lang, setLang, t: (k: string, fb?: string) => translate(lang, k, fb) }),
    [lang, setLang],
  )

  /* ---- auth ----------------------------------------------------------- */
  const [user, setUser] = useState<User | null>(null)
  const [loadingAuth, setLoadingAuth] = useState(true)
  const [authError, setAuthError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const token = getToken()
    if (!token) {
      setLoadingAuth(false)
      return
    }
    api
      .me()
      .then((u) => {
        if (cancelled) return
        setUser(u)
        if (u.language === 'hi' || u.language === 'en') setLang(u.language)
      })
      .catch(() => setToken(null))
      .finally(() => !cancelled && setLoadingAuth(false))
    return () => {
      cancelled = true
    }
  }, [setLang])

  const signIn = useCallback(
    async (username: string, password: string) => {
      setAuthError(null)
      try {
        const res = await api.login(username, password)
        setToken(res.access_token)
        setUser(res.user)
        if (res.user.language === 'hi' || res.user.language === 'en') setLang(res.user.language)
        return res.user
      } catch (err) {
        const message = err instanceof PehraError ? err.message : 'Sign-in failed.'
        setAuthError(message)
        throw err
      }
    },
    [setLang],
  )

  const signOut = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  const can = useCallback(
    (...roles: User['role'][]) => !!user && roles.includes(user.role),
    [user],
  )

  const auth = useMemo<AuthValue>(
    () => ({ user, loading: loadingAuth, error: authError, signIn, signOut, can }),
    [user, loadingAuth, authError, signIn, signOut, can],
  )

  /* ---- engine config -------------------------------------------------- */
  const [config, setConfig] = useState<EngineConfig | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    api
      .config()
      .then((c) => !cancelled && setConfig(c))
      .catch((e: PehraError) => !cancelled && setConfigError(e.message))
    return () => {
      cancelled = true
    }
  }, [])
  const configValue = useMemo(() => ({ config, error: configError }), [config, configError])

  /* ---- realtime ------------------------------------------------------- */
  const [connected, setConnected] = useState(false)
  const [transport, setTransport] = useState<LiveValue['transport']>('disconnected')
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null)
  const [revision, setRevision] = useState(0)
  const listeners = useRef(new Set<Listener>())

  const emit = useCallback((event: LiveEvent) => {
    setLastEvent(event)
    setRevision((r) => r + 1)
    listeners.current.forEach((fn) => {
      try {
        fn(event)
      } catch {
        /* a broken listener must not take down the stream */
      }
    })
  }, [])

  useEffect(() => {
    let source: EventSource | null = null
    let pollTimer: number | undefined
    let retry: number | undefined
    let closed = false
    let seen = new Set<string>()

    const startPolling = () => {
      setTransport('polling')
      const tick = async () => {
        try {
          const res = await api.recentEvents(10)
          setConnected(true)
          for (const raw of res.events.slice().reverse()) {
            const e = raw as unknown as LiveEvent
            const id = `${e.type}:${e.at}`
            if (seen.has(id)) continue
            seen.add(id)
            emit(e)
          }
          if (seen.size > 200) seen = new Set(Array.from(seen).slice(-100))
        } catch {
          setConnected(false)
        }
      }
      void tick()
      pollTimer = window.setInterval(tick, 5000)
    }

    const connect = () => {
      if (closed) return
      if (typeof EventSource === 'undefined') {
        startPolling()
        return
      }
      source = new EventSource(apiUrl('/api/events'))
      source.onopen = () => {
        setConnected(true)
        setTransport('sse')
      }
      source.onmessage = (ev) => {
        try {
          emit(JSON.parse(ev.data))
        } catch {
          /* ignore malformed frame */
        }
      }
      // named events
      for (const name of [
        'risk_update',
        'simulation_step',
        'alert_created',
        'alert_updated',
        'threat_update',
        'connectivity',
        'scenario_changed',
        'system',
      ]) {
        source.addEventListener(name, (ev) => {
          try {
            emit(JSON.parse((ev as MessageEvent).data))
          } catch {
            /* ignore */
          }
        })
      }
      source.onerror = () => {
        setConnected(false)
        source?.close()
        source = null
        if (closed) return
        // one retry, then fall back to polling so the UI never goes stale
        retry = window.setTimeout(() => {
          if (closed) return
          if (transportRef.current === 'sse') startPolling()
          else connect()
        }, 3000)
      }
    }

    const transportRef = { current: 'sse' as LiveValue['transport'] }
    connect()

    return () => {
      closed = true
      source?.close()
      if (pollTimer) window.clearInterval(pollTimer)
      if (retry) window.clearTimeout(retry)
    }
  }, [emit])

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn)
    return () => {
      listeners.current.delete(fn)
    }
  }, [])

  const invalidate = useCallback(() => setRevision((r) => r + 1), [])

  const live = useMemo<LiveValue>(
    () => ({ connected, transport, lastEvent, revision, subscribe, invalidate }),
    [connected, transport, lastEvent, revision, subscribe, invalidate],
  )

  return (
    <I18nContext.Provider value={i18n}>
      <AuthContext.Provider value={auth}>
        <ConfigContext.Provider value={configValue}>
          <LiveContext.Provider value={live}>
            <ThemeProvider>{children}</ThemeProvider>
          </LiveContext.Provider>
        </ConfigContext.Provider>
      </AuthContext.Provider>
    </I18nContext.Provider>
  )
}
