import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, PehraError } from '../lib/api'

describe('api client — hostile responses', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    try {
      localStorage.clear()
    } catch {
      /* ignore */
    }
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('rejects a 200 text/html body instead of returning it as data', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response('<!doctype html><html>SPA index.html</html>', { status: 200 }),
    )
    const err = await api.demoAccounts().then(
      () => null,
      (e) => e as PehraError,
    )
    expect(err).toBeInstanceOf(PehraError)
    expect(err!.status).toBe(200)
    expect(err!.payload.error).toBe('bad_response')
  })

  it('resolves genuine 200 JSON payloads', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ note: 'seeded', accounts: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const data = await api.demoAccounts()
    expect(data.note).toBe('seeded')
    expect(data.accounts).toEqual([])
  })

  it('still surfaces non-OK JSON error bodies as PehraError', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'unauthenticated', message: 'no' }), { status: 401 }),
    )
    const err = await api.demoAccounts().then(
      () => null,
      (e) => e as PehraError,
    )
    expect(err).toBeInstanceOf(PehraError)
    expect(err!.status).toBe(401)
  })
})