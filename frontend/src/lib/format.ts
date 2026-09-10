/** Small presentation helpers. None of these compute risk — they format it. */
import type { SeverityKey } from './types'

/** Fixed hex values for canvas/SVG drawing (Leaflet fills) — the map canvas
 *  stays dark in both themes, so these never change. */
export const SEVERITY_COLOR: Record<SeverityKey, string> = {
  SAFE: '#22c55e',
  LOW: '#3b82f6',
  MODERATE: '#f5b942',
  HIGH: '#f97316',
  CRITICAL: '#ef4444',
}

export const LEVEL_COLOR: Record<string, string> = {
  WATCH: '#f5b942',
  WARNING: '#f97316',
  CRITICAL: '#ef4444',
}

/** Theme-aware severity colours for inline UI styles (badges, bars). They
 *  resolve through CSS variables so light/dark both stay legible. */
export const SEVERITY_VAR: Record<SeverityKey, string> = {
  SAFE: 'var(--sev-safe)',
  LOW: 'var(--sev-low)',
  MODERATE: 'var(--sev-moderate)',
  HIGH: 'var(--sev-high)',
  CRITICAL: 'var(--sev-critical)',
}

export const LEVEL_VAR: Record<string, string> = {
  WATCH: 'var(--sev-moderate)',
  WARNING: 'var(--sev-high)',
  CRITICAL: 'var(--sev-critical)',
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

/** Great-circle distance in km. Display maths only (shelter walk estimates)
 *  — never used inside the risk engine. */
export function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLng = ((lng2 - lng1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

/** Seconds → "HH:MM:SS" for T-minus countdowns. */
export function fmtClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(h)}:${p(m)}:${p(sec)}`
}

/** Approx. walking minutes at 4.5 km/h. Display estimate only. */
export function walkMinutes(km: number): number {
  return Math.max(1, Math.round((km / 4.5) * 60))
}
