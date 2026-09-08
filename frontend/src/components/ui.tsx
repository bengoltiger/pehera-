/**
 * Shared presentational primitives.
 *
 * Two rules enforced here:
 *  - Severity is never colour-only: every badge carries label + icon + ASCII
 *    marker + texture (Section 34).
 *  - Absent data is stated, never zero-filled (Sections 62, 63).
 */
import {
  AlertCircle,
  AlertTriangle,
  CircleHelp,
  Info,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Siren,
  TriangleAlert,
  WifiOff,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { SEVERITY_COLOR, SEVERITY_PATTERN, clsx, withAlpha } from '../lib/format'
import type { SeverityKey } from '../lib/types'

/* -------------------------------------------------------------------------- */
/* Severity                                                                    */
/* -------------------------------------------------------------------------- */
const SEVERITY_ICON: Record<SeverityKey, typeof ShieldCheck> = {
  SAFE: ShieldCheck,
  LOW: Info,
  MODERATE: AlertCircle,
  HIGH: TriangleAlert,
  CRITICAL: Siren,
}

const SEVERITY_ASCII: Record<SeverityKey, string> = {
  SAFE: 'OK',
  LOW: '·',
  MODERATE: '▲',
  HIGH: '▲▲',
  CRITICAL: '■■■',
}

export function SeverityBadge({
  level,
  label,
  score,
  size = 'md',
  showAscii = true,
  className,
}: {
  level: SeverityKey
  label?: string
  score?: number
  size?: 'sm' | 'md' | 'lg'
  showAscii?: boolean
  className?: string
}) {
  const color = SEVERITY_COLOR[level] ?? SEVERITY_COLOR.LOW
  const Icon = SEVERITY_ICON[level] ?? Info
  const sizes = {
    sm: 'text-[10px] px-1.5 py-0.5 gap-1',
    md: 'text-xs px-2 py-1 gap-1.5',
    lg: 'text-sm px-2.5 py-1.5 gap-2',
  }[size]
  const iconSize = size === 'sm' ? 11 : size === 'lg' ? 16 : 13
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-md font-semibold tracking-wide uppercase',
        sizes,
        className,
      )}
      style={{
        color,
        backgroundColor: withAlpha(color, 0.14),
        border: `1px solid ${withAlpha(color, 0.5)}`,
      }}
      title={`${label ?? level}${score !== undefined ? ` — ${score.toFixed(0)}/100` : ''}`}
    >
      <Icon size={iconSize} aria-hidden />
      <span>{label ?? level}</span>
      {showAscii && (
        <span aria-hidden className="opacity-70 font-mono not-italic">
          {SEVERITY_ASCII[level]}
        </span>
      )}
      {score !== undefined && <span className="font-mono opacity-90">{score.toFixed(0)}</span>}
    </span>
  )
}

/** Bar whose fill also carries a colour-blind-safe texture. */
export function SeverityBar({
  value,
  level,
  height = 8,
  className,
  showTicks = false,
}: {
  value: number
  level: SeverityKey
  height?: number
  className?: string
  showTicks?: boolean
}) {
  const color = SEVERITY_COLOR[level] ?? SEVERITY_COLOR.LOW
  const pattern = SEVERITY_PATTERN[level] ?? 'solid'
  return (
    <div className={clsx('relative w-full', className)}>
      <div
        className="w-full overflow-hidden rounded-full bg-ink-800"
        style={{ height }}
        role="meter"
        aria-valuenow={Math.round(value)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Risk ${Math.round(value)} of 100, ${level}`}
      >
        <div
          className={clsx('h-full rounded-full transition-[width] duration-500', `sev-pattern-${pattern}`)}
          style={{
            width: `${Math.max(0, Math.min(100, value))}%`,
            backgroundColor: color,
            color: withAlpha('#000000', 0.35),
          }}
        />
      </div>
      {showTicks && (
        <div className="pointer-events-none absolute inset-0 flex">
          {[20, 40, 60, 80].map((t) => (
            <span
              key={t}
              className="absolute top-0 h-full w-px bg-ink-950/70"
              style={{ left: `${t}%` }}
              aria-hidden
            />
          ))}
        </div>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Panels                                                                      */
/* -------------------------------------------------------------------------- */
export function Panel({
  title,
  subtitle,
  icon,
  actions,
  children,
  className,
  bodyClassName,
  dense,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  icon?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
  dense?: boolean
}) {
  return (
    <section className={clsx('panel flex min-h-0 flex-col', className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-ink-700/50 px-4 py-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink-100">
              {icon}
              <span className="truncate">{title}</span>
            </h2>
            {subtitle && <p className="mt-0.5 text-xs text-ink-400">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx('min-h-0 flex-1', dense ? 'p-0' : 'p-4', bodyClassName)}>{children}</div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* States: loading / error / empty / unavailable                               */
/* -------------------------------------------------------------------------- */
export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('skeleton', className)} aria-hidden />
}

export function LoadingBlock({ label = 'Loading…', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-4 w-full" />
      ))}
    </div>
  )
}

export function Spinner({ size = 14, className }: { size?: number; className?: string }) {
  return <Loader2 size={size} className={clsx('animate-spin', className)} aria-hidden />
}

export function ErrorBlock({
  error,
  onRetry,
  compact,
}: {
  error: { message: string; payload?: { error?: string; problems?: { field: string; message: string }[] } } | null
  onRetry?: () => void
  compact?: boolean
}) {
  if (!error) return null
  const problems = error.payload?.problems
  return (
    <div
      className={clsx(
        'rounded-lg border border-critical/40 bg-critical/10 text-ink-100',
        compact ? 'px-3 py-2 text-xs' : 'p-4 text-sm',
      )}
      role="alert"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle size={compact ? 14 : 16} className="mt-0.5 shrink-0 text-critical" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{error.message}</p>
          {problems && problems.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-ink-300">
              {problems.map((p) => (
                <li key={p.field}>
                  <span className="font-mono">{p.field}</span>: {p.message}
                </li>
              ))}
            </ul>
          )}
          {error.payload?.error && (
            <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-ink-500">
              {error.payload.error}
            </p>
          )}
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="shrink-0 rounded-md border border-ink-600 px-2 py-1 text-xs text-ink-200 hover:bg-ink-800"
          >
            <RefreshCw size={11} className="mr-1 inline" aria-hidden />
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

export function EmptyState({
  title,
  detail,
  icon,
  action,
}: {
  title: string
  detail?: string
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      <div className="text-ink-600">{icon ?? <CircleHelp size={26} aria-hidden />}</div>
      <p className="text-sm font-medium text-ink-200">{title}</p>
      {detail && <p className="max-w-sm text-xs leading-relaxed text-ink-400">{detail}</p>}
      {action}
    </div>
  )
}

/**
 * The single most important component for data honesty: when the engine cannot
 * produce a value it returns a REASON, and this renders it instead of a zero.
 */
export function Unavailable({
  reason,
  label,
  compact,
}: {
  reason?: string | null
  label?: string
  compact?: boolean
}) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-md border border-dashed border-ink-600 bg-ink-850/60 text-ink-400',
        compact ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs',
      )}
      title={reason ?? undefined}
    >
      <CircleHelp size={compact ? 10 : 12} aria-hidden />
      <span>{label ?? 'Not available'}</span>
      {reason && !compact && <span className="max-w-[22rem] truncate text-ink-500">— {reason}</span>}
    </span>
  )
}

/* -------------------------------------------------------------------------- */
/* Small atoms                                                                 */
/* -------------------------------------------------------------------------- */
export function Chip({
  children,
  tone = 'neutral',
  icon,
  title,
  className,
}: {
  children: ReactNode
  tone?: 'neutral' | 'info' | 'warn' | 'danger' | 'good' | 'sim'
  icon?: ReactNode
  title?: string
  className?: string
}) {
  const tones = {
    neutral: 'border-ink-600 bg-ink-800/70 text-ink-300',
    info: 'border-accent/40 bg-accent/10 text-accent-bright',
    warn: 'border-moderate/40 bg-moderate/10 text-moderate',
    danger: 'border-critical/40 bg-critical/10 text-critical',
    good: 'border-safe/40 bg-safe/10 text-safe',
    sim: 'border-moderate/50 bg-moderate/15 text-moderate',
  }[tone]
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
        tones,
        className,
      )}
      title={title}
    >
      {icon}
      {children}
    </span>
  )
}

export function Stat({
  label,
  value,
  hint,
  tone,
  icon,
  unavailableReason,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: string
  icon?: ReactNode
  unavailableReason?: string | null
}) {
  return (
    <div className="panel-tight px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-ink-400">
        {icon}
        {label}
      </div>
      {unavailableReason ? (
        <div className="mt-1">
          <Unavailable reason={unavailableReason} compact />
        </div>
      ) : (
        <div className="mt-0.5 font-mono text-xl leading-tight font-semibold" style={tone ? { color: tone } : undefined}>
          {value}
        </div>
      )}
      {hint && <div className="mt-0.5 text-[11px] leading-snug text-ink-500">{hint}</div>}
    </div>
  )
}

export function Button({
  children,
  onClick,
  variant = 'default',
  size = 'md',
  disabled,
  pending,
  icon,
  title,
  type = 'button',
  className,
}: {
  children?: ReactNode
  onClick?: () => void
  variant?: 'default' | 'primary' | 'danger' | 'ghost' | 'success'
  size?: 'sm' | 'md'
  disabled?: boolean
  pending?: boolean
  icon?: ReactNode
  title?: string
  type?: 'button' | 'submit'
  className?: string
}) {
  const variants = {
    default: 'border-ink-600 bg-ink-800 text-ink-100 hover:bg-ink-700',
    primary: 'border-accent/60 bg-accent/20 text-accent-bright hover:bg-accent/30',
    danger: 'border-critical/60 bg-critical/20 text-critical hover:bg-critical/30',
    success: 'border-safe/60 bg-safe/20 text-safe hover:bg-safe/30',
    ghost: 'border-transparent bg-transparent text-ink-300 hover:bg-ink-800',
  }[variant]
  const sizes = { sm: 'px-2 py-1 text-xs gap-1', md: 'px-3 py-1.5 text-sm gap-1.5' }[size]
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || pending}
      title={title}
      className={clsx(
        'inline-flex items-center justify-center rounded-md border font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-45',
        variants,
        sizes,
        className,
      )}
    >
      {pending ? <Spinner size={13} /> : icon}
      {children}
    </button>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
}) {
  return (
    <label
      className={clsx(
        'flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 hover:bg-ink-800/60',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={clsx(
          'mt-0.5 h-4 w-7 shrink-0 rounded-full border transition-colors',
          checked ? 'border-accent bg-accent/70' : 'border-ink-600 bg-ink-800',
        )}
      >
        <span
          className={clsx(
            'block h-3 w-3 rounded-full bg-ink-100 transition-transform',
            checked ? 'translate-x-3.5' : 'translate-x-0.5',
          )}
        />
      </button>
      <span className="min-w-0">
        <span className="block text-xs text-ink-200">{label}</span>
        {description && <span className="block text-[11px] leading-snug text-ink-500">{description}</span>}
      </span>
    </label>
  )
}

/** The stale/offline strip shown above data that is no longer live. */
export function StaleNotice({ stale, offline, message }: { stale?: boolean; offline?: boolean; message?: string }) {
  if (!stale && !offline) return null
  return (
    <div className="mb-2 flex items-center gap-2 rounded-md border border-moderate/40 bg-moderate/10 px-2.5 py-1.5 text-[11px] text-moderate">
      <WifiOff size={12} aria-hidden />
      <span>
        {message ??
          (offline
            ? 'Offline — these are the last values received, not live readings.'
            : 'Could not refresh — showing the last successful reading.')}
      </span>
    </div>
  )
}

export function Tooltip({ children, content }: { children: ReactNode; content: string }) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 hidden w-max max-w-xs -translate-x-1/2 rounded-md border border-ink-600 bg-ink-900 px-2 py-1 text-[11px] leading-snug text-ink-200 shadow-xl group-hover:block">
        {content}
      </span>
    </span>
  )
}
