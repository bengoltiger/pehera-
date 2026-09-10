/**
 * Data-fetching hooks.
 *
 * `useApi` gives every screen the same four honest states: loading, error
 * (with the backend's reason), empty and loaded — plus `stale`, which marks
 * data that is still displayed but is known to be out of date. Nothing here
 * ever fabricates a value to fill a gap.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { PehraError } from './api'
import { useLive } from './providers'

export interface ApiState<T> {
  data: T | null
  error: PehraError | null
  loading: boolean
  /** Data is shown but a newer fetch failed, or the stream is disconnected. */
  stale: boolean
  lastUpdated: number | null
  reload: () => void
}

export interface UseApiOptions {
  /** Refetch whenever the realtime bus emits (default true). */
  liveUpdate?: boolean
  /** Poll every N ms in addition to the event stream. */
  pollMs?: number
  /** Skip fetching entirely (e.g. missing id). */
  enabled?: boolean
  /** Extra dependencies that should trigger a refetch. */
  deps?: unknown[]
}

export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: UseApiOptions = {},
): ApiState<T> {
  const { liveUpdate = true, pollMs, enabled = true, deps = [] } = options
  const { revision } = useLive()

  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<PehraError | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [stale, setStale] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<number | null>(null)
  const [manual, setManual] = useState(0)

  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const hasData = useRef(false)

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    const controller = new AbortController()
    let cancelled = false
    let retryTimer: number | undefined
    if (!hasData.current) setLoading(true)

    const run = (is429Retry: boolean) => {
      fetcherRef
        .current(controller.signal)
        .then((result) => {
          if (cancelled) return
          setData(result)
          hasData.current = true
          setError(null)
          setStale(false)
          setLastUpdated(Date.now())
        })
        .catch((err) => {
          if (cancelled || (err as Error)?.name === 'AbortError') return
          const pehraError = err instanceof PehraError ? err : new PehraError(0, {
            error: 'unknown',
            message: (err as Error)?.message || 'Unexpected error.',
          })
          // 429 = the server asked us to slow down: back off once, then retry.
          if (pehraError.status === 429 && !is429Retry) {
            retryTimer = window.setTimeout(() => {
              if (!cancelled) run(true)
            }, 1500)
            return
          }
          // Keep showing what we have, but mark it clearly as stale.
          if (hasData.current) setStale(true)
          else setData(null)
          setError(pehraError)
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }
    run(false)

    return () => {
      cancelled = true
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, manual, liveUpdate ? revision : 0, ...deps])

  useEffect(() => {
    if (!pollMs || !enabled) return
    const id = window.setInterval(() => setManual((m) => m + 1), pollMs)
    return () => window.clearInterval(id)
  }, [pollMs, enabled])

  const reload = useCallback(() => setManual((m) => m + 1), [])

  return { data, error, loading, stale, lastUpdated, reload }
}

/** Run a mutation with loading/error state and automatic stream invalidation. */
export function useMutation<Args extends unknown[], R>(
  fn: (...args: Args) => Promise<R>,
): {
  run: (...args: Args) => Promise<R | null>
  pending: boolean
  error: PehraError | null
  reset: () => void
} {
  const { invalidate } = useLive()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<PehraError | null>(null)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const run = useCallback(
    async (...args: Args) => {
      setPending(true)
      setError(null)
      try {
        const result = await fnRef.current(...args)
        invalidate()
        return result
      } catch (err) {
        setError(
          err instanceof PehraError
            ? err
            : new PehraError(0, { error: 'unknown', message: (err as Error)?.message || 'Failed.' }),
        )
        return null
      } finally {
        setPending(false)
      }
    },
    [invalidate],
  )

  return { run, pending, error, reset: () => setError(null) }
}

/** Persisted boolean/string/object preference. */
export function useLocalState<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw ? (JSON.parse(raw) as T) : initial
    } catch {
      return initial
    }
  })
  const set = useCallback(
    (v: T | ((p: T) => T)) => {
      setValue((prev) => {
        const next = typeof v === 'function' ? (v as (p: T) => T)(prev) : v
        try {
          localStorage.setItem(key, JSON.stringify(next))
        } catch {
          /* ignore */
        }
        return next
      })
    },
    [key],
  )
  return [value, set]
}

/** True when the browser itself reports no network. */
export function useBrowserOnline(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}
