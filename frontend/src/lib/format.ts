/** Small presentation helpers. None of these compute risk — they format it. */
import type { SeverityKey } from './types'

export const SEVERITY_COLOR: Record<SeverityKey, string> = {
  SAFE: '#1f7a4d',
  LOW: '#3f7fbf',
  MODERATE: '#c98a17',
  HIGH: '#d1600f',
  CRITICAL: '#b3161c',
}

export const LEVEL_COLOR: Record<string, string> = {
  WATCH: '#c98a17',
  WARNING: '#d1600f',
  CRITICAL: '#b3161c',
}

export const SEVERITY_PATTERN: Record<SeverityKey, string> = {
  SAFE: 'solid',
  LOW: 'dots',
  MODERATE: 'diagonal',
  HIGH: 'cross',
  CRITICAL: 'hatch',
}

export function severityFromScore(score: number): SeverityKey {
  if (score <= 20) return 'SAFE'
  if (score <= 40) return 'LOW'
  if (score <= 60) return 'MODERATE'
  if (score <= 80) return 'HIGH'
  return 'CRITICAL'
}

export function fmtNumber(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function fmtPeople(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  if (n >= 10_000_000) return `${(n / 10_000_000).toFixed(1)} cr`
  if (n >= 100_000) return `${(n / 100_000).toFixed(1)} L`
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`
  return String(n)
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem ? `${h}h ${rem}m` : `${h}h`
}

export function fmtMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '—'
  return fmtDuration(minutes * 60)
}

/** Renders a UTC timestamp. PEHRA stores UTC; we always say which zone. */
export function fmtTime(iso: string | null | undefined, opts: { seconds?: boolean; utc?: boolean } = {}): string {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    ...(opts.seconds ? { second: '2-digit' } : {}),
    ...(opts.utc ? { timeZone: 'UTC' } : {}),
  })
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`)
  const secs = (Date.now() - d.getTime()) / 1000
  if (secs < 45) return 'just now'
  if (secs < 3600) return `${Math.round(secs / 60)} min ago`
  if (secs < 86400) return `${Math.round(secs / 3600)} h ago`
  return `${Math.round(secs / 86400)} d ago`
}

export function clsx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

/** Hex + alpha → rgba(), used for map fills. */
export function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

export function titleCase(s: string): string {
  return s.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
