import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  Moon,
  Sun,
  MessageSquarePlus,
  Terminal,
  Puzzle,
  Pencil,
  CheckCircle,
  Settings,
} from 'lucide-react'
import HeroMetrics from '@/screens/dashboard/components/hero-metrics'
import ActiveModelKpi from '@/screens/dashboard/components/active-model-kpi'
import { WidgetShell } from '@/screens/dashboard/components/widget-shell'
import { cn } from '@/lib/utils'

// ── Types ────────────────────────────────────────────────────────

interface DashboardOverview {
  status?: unknown
  platforms?: Array<unknown>
  cron?: unknown
  achievements?: unknown
  modelInfo?: {
    model: string
    provider?: string
    effectiveContextLength?: number
  } | null
  analytics?: {
    source?: string
    daily: Array<{
      inputTokens: number
      outputTokens: number
      sessions: number
      apiCalls: number
    }>
    totalTokens: number
    totalSessions: number
    totalApiCalls: number
    cacheReadTokens: number
    windowDays: number
    topModels: Array<{ id: string; calls: number; sessions: number }>
  } | null
  skillsUsage?: {
    distinctSkills: number
    topSkills: Array<{ skill: string; count: number }>
  } | null
  incidents?: Array<unknown>
  logs?: unknown
  insights?: Array<unknown>
}

interface ClaudeSession {
  id: string
  started_at?: number
  message_count?: number
  tool_call_count?: number
  input_tokens?: number
  output_tokens?: number
  title?: string
  model?: string
}

interface SessionRowData {
  key: string
  title: string
  kind: string
  status: string
  source: string | null
  model: string | null
  messageCount: number
  toolCallCount: number
  tokenCount: number
  startedAt: number | null
  updatedAt: number | null
}

interface DashboardLayout {
  editMode: boolean
  isVisible: (id: string) => boolean
  hide: (id: string) => void
  toggleEdit: () => void
}

interface DashboardScreenProps {
  navigate?: (path: string) => void
  sessionsAvailable?: boolean
  skillsAvailable?: boolean
}

// ── Placeholder imports for sibling components ───────────────────
// These components live alongside this screen in the original codebase.
// In the agent-os migration they are imported from their own files.

// Stub types for components imported from sibling files
// (Actual implementations remain in their respective files)

// ── Helpers ──────────────────────────────────────────────────────

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function themeColor(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim()
  return value || fallback
}

function alpha(color: string, amount: number): string {
  const pct = Math.max(0, Math.min(100, Math.round(amount * 100)))
  return `color-mix(in srgb, ${color} ${pct}%, transparent)`
}

function readDashboardPalette() {
  return {
    accent: themeColor('--theme-accent', '#6366f1'),
    accentSecondary: themeColor('--theme-accent-secondary', '#8b5cf6'),
    success: themeColor('--theme-success', '#22c55e'),
    warning: themeColor('--theme-warning', '#f59e0b'),
    danger: themeColor('--theme-danger', '#ef4444'),
    muted: themeColor('--theme-muted', '#6b7280'),
    border: themeColor('--theme-border', '#333333'),
    card: themeColor('--theme-card', '#1a1a2e'),
    text: themeColor('--theme-text', '#e5e7eb'),
  }
}

function useDashboardPalette() {
  const [palette, setPalette] = useState(readDashboardPalette)

  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const refresh = () => setPalette(readDashboardPalette())
    refresh()
    const observer = new MutationObserver(refresh)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme', 'style', 'class'],
    })
    return () => observer.disconnect()
  }, [])

  return palette
}

// ── Data fetching helper (replaces useQuery) ─────────────────────

function useFetchData<T>(
  url: string,
  options: {
    enabled?: boolean
    staleTime?: number
    refetchInterval?: number
    transform?: (data: unknown) => T
  } = {},
) {
  const {
    enabled = true,
    staleTime = 0,
    refetchInterval,
    transform,
  } = options

  const [data, setData] = useState<T | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const lastFetchedRef = useState<number>(0)[0]

  const fetchData = async () => {
    if (!enabled) return
    const now = Date.now()
    if (now - lastFetchedRef < staleTime && data !== null) return

    setIsFetching(true)
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`fetch ${res.status}`)
      const raw = await res.json()
      setData(transform ? transform(raw) : (raw as T))
    } catch {
      // graceful fallback
    } finally {
      setIsFetching(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [url, enabled])

  useEffect(() => {
    if (!refetchInterval || !enabled) return
    const id = setInterval(fetchData, refetchInterval)
    return () => clearInterval(id)
  }, [url, enabled, refetchInterval])

  return { data, isFetching, refetch: fetchData }
}

// ── Glass Card ───────────────────────────────────────────────────

interface GlassCardProps {
  title?: string
  titleRight?: ReactNode
  accentColor?: string
  noPadding?: boolean
  className?: string
  children: ReactNode
}

function GlassCard({
  title,
  titleRight,
  accentColor,
  noPadding,
  className,
  children,
}: GlassCardProps) {
  return (
    <div
      className={cn(
        'relative flex flex-col overflow-hidden rounded-xl border transition-colors',
        className,
      )}
      style={{
        background: 'var(--theme-card)',
        borderColor: 'var(--theme-border)',
      }}
    >
      {accentColor && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-[2px]"
          style={{
            background: `linear-gradient(90deg, ${accentColor}, ${accentColor}50, transparent)`,
          }}
        />
      )}
      {title && (
        <div className="flex items-center justify-between px-5 pt-4 pb-0">
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted">
            {title}
          </h3>
          {titleRight}
        </div>
      )}
      <div className={cn('flex-1', noPadding ? '' : 'px-5 pb-4 pt-3')}>
        {children}
      </div>
    </div>
  )
}

function EnhancedBadge({ label = 'Enhanced API' }: { label?: string }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]"
      style={{
        border: `1px solid ${themeColor('--theme-accent-border', 'rgba(245, 158, 11, 0.28)')}`,
        background: themeColor('--theme-accent-subtle', 'rgba(245, 158, 11, 0.12)'),
        color: themeColor('--theme-accent', '#f59e0b'),
      }}
    >
      {label}
    </span>
  )
}

interface UnavailableWidgetProps {
  title: string
  description: string
}

function UnavailableWidget({
  title,
  description,
}: UnavailableWidgetProps) {
  return (
    <GlassCard
      title={title}
      titleRight={<EnhancedBadge />}
      accentColor={themeColor('--theme-warning', '#f59e0b')}
      className="h-full"
    >
      <div className="flex h-full min-h-[180px] items-center justify-center rounded-lg border border-dashed border-[var(--theme-border)] bg-[var(--theme-card2)] px-4 text-center">
        <p className="text-sm text-muted">{description}</p>
      </div>
    </GlassCard>
  )
}

// ── Metric Tile ──────────────────────────────────────────────────

interface MetricTileProps {
  label: string
  value: string
  sub?: string
  icon: string
  accentColor: string
}

function MetricTile({
  label,
  value,
  sub,
  icon,
  accentColor,
}: MetricTileProps) {
  return (
    <GlassCard accentColor={accentColor}>
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-0.5">
          <div className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted">
            {label}
          </div>
          <div className="text-2xl font-bold tabular-nums text-ink">
            {value}
          </div>
          {sub && <div className="text-[11px] text-muted">{sub}</div>}
        </div>
        <div
          className="flex size-8 items-center justify-center rounded-lg text-base"
          style={{ background: `${accentColor}15` }}
        >
          {icon}
        </div>
      </div>
    </GlassCard>
  )
}

// ── Activity Chart ───────────────────────────────────────────────

interface ActivityChartProps {
  sessions: Array<ClaudeSession>
  palette: ReturnType<typeof readDashboardPalette>
}

function ActivityChart({
  sessions,
  palette,
}: ActivityChartProps) {
  const chartData = useMemo(() => {
    const dayMap = new Map<string, { sessions: number; messages: number }>()
    const now = Date.now() / 1000
    for (let i = 13; i >= 0; i--) {
      const d = new Date((now - i * 86400) * 1000)
      const key = d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      })
      dayMap.set(key, { sessions: 0, messages: 0 })
    }
    for (const s of sessions) {
      if (!s.started_at) continue
      const d = new Date(s.started_at * 1000)
      const key = d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      })
      const entry = dayMap.get(key)
      if (entry) {
        entry.sessions += 1
        entry.messages += s.message_count ?? 0
      }
    }
    const all = Array.from(dayMap.entries()).map(([date, data]) => ({
      date,
      ...data,
    }))
    let firstActive = all.findIndex((d) => d.sessions > 0 || d.messages > 0)
    if (firstActive > 0) firstActive = Math.max(0, firstActive - 1)
    return firstActive > 0 ? all.slice(firstActive) : all
  }, [sessions])

  return (
    <GlassCard
      title="Activity"
      titleRight={<span className="text-[10px] text-muted">14 days</span>}
      accentColor={palette.accent}
      className="h-full"
    >
      <div className="h-[200px] w-full -ml-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            margin={{ top: 8, right: 32, left: -16, bottom: 0 }}
          >
            <defs>
              <linearGradient id="g-sessions" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={palette.accent} stopOpacity={0.3} />
                <stop offset="100%" stopColor={palette.accent} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="g-messages" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={palette.success} stopOpacity={0.2} />
                <stop offset="100%" stopColor={palette.success} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={palette.border} opacity={0.45} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: palette.muted }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 10, fill: palette.success }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
              width={28}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 10, fill: palette.accent }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
              width={28}
            />
            <Tooltip
              contentStyle={{
                background: palette.card,
                border: `1px solid ${palette.border}`,
                borderRadius: '8px',
                fontSize: '11px',
              }}
              labelStyle={{ color: palette.muted, fontSize: '10px' }}
            />
            <Area
              yAxisId="left"
              type="monotone"
              dataKey="messages"
              stroke={palette.success}
              fill="url(#g-messages)"
              strokeWidth={1.5}
              dot={false}
            />
            <Area
              yAxisId="right"
              type="monotone"
              dataKey="sessions"
              stroke={palette.accent}
              fill="url(#g-sessions)"
              strokeWidth={2}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex items-center gap-5 text-[10px] text-muted">
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full" style={{ background: palette.accent }} />
          Sessions
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full" style={{ background: palette.success }} />
          Messages
        </span>
      </div>
    </GlassCard>
  )
}

// ── Skills Widget ────────────────────────────────────────────────

interface SkillsWidgetProps {
  palette: ReturnType<typeof readDashboardPalette>
  onOpen: () => void
  usage: DashboardOverview['skillsUsage']
}

function SkillsWidget({
  palette,
  onOpen,
  usage,
}: SkillsWidgetProps) {
  const [skills, setSkills] = useState<Array<Record<string, unknown>>>([])

  useEffect(() => {
    const fetchSkills = async () => {
      try {
        const res = await fetch('/api/skills?tab=installed&limit=200&summary=search')
        if (!res.ok) return
        const data = await res.json()
        setSkills(data?.skills ?? [])
      } catch {
        // silent
      }
    }
    fetchSkills()
  }, [])

  // Summary view per Hermes Agent feedback: 'don't enumerate, summarise.'
  // Prefer real usage signal from /api/analytics/usage when present
  // (counts what the agent *actually used*, not just what's installed).
  const installed = skills.length
  const enabled = skills.filter((s) => s.enabled !== false).length
  const usedThisWindow = usage?.distinctSkills ?? null
  const topUsed = usage?.topSkills?.[0]
  const topInstalled =
    skills.find((s) => s.enabled !== false) ?? skills[0]
  const topName = topUsed?.skill
    ? topUsed.skill
    : topInstalled
      ? String(topInstalled.name ?? '—')
      : '—'

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative flex w-full flex-col gap-1.5 overflow-hidden rounded-xl border px-4 py-3 text-left transition-colors hover:bg-[var(--theme-card)]/80"
      style={{
        background: 'var(--theme-card)',
        borderColor: 'var(--theme-border)',
      }}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[2px]"
        style={{
          background: `linear-gradient(90deg, ${palette.warning}, ${palette.warning}50, transparent)`,
        }}
      />
      <div className="flex items-center justify-between">
        <h3
          className="text-[10px] font-semibold uppercase tracking-[0.18em]"
          style={{ color: 'var(--theme-muted)' }}
        >
          Skills
        </h3>
        <span
          className="font-mono text-[9px] uppercase tracking-[0.15em]"
          style={{ color: 'var(--theme-muted)' }}
        >
          manage →
        </span>
      </div>
      <div
        className="font-mono text-2xl font-bold tabular-nums leading-none"
        style={{ color: 'var(--theme-text)' }}
      >
        {installed}
      </div>
      <div
        className="font-mono text-[10px] uppercase tracking-[0.1em]"
        style={{ color: 'var(--theme-muted)' }}
      >
        {installed === 0
          ? 'no skills installed'
          : usedThisWindow !== null && usedThisWindow > 0
            ? `${enabled} enabled · ${usedThisWindow} used · top: ${topName}`
            : `${enabled} enabled · top: ${topName}`}
      </div>
    </button>
  )
}

// ── Secondary action (smaller, monochrome) ─────────────────────

interface SecondaryActionProps {
  label: string
  icon: ReactNode
  onClick: () => void
  disabled?: boolean
}

function SecondaryAction({
  label,
  icon,
  onClick,
  disabled,
}: SecondaryActionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="group inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold uppercase tracking-[0.05em] transition-all hover:scale-[1.015] hover:bg-[var(--theme-card)]/70 hover:text-[var(--theme-text)] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50"
      style={{
        borderColor: 'var(--theme-border)',
        color: 'var(--theme-muted)',
        background:
          'linear-gradient(135deg, color-mix(in srgb, var(--theme-card) 80%, transparent), transparent)',
      }}
    >
      <span className="transition-colors group-hover:text-[var(--theme-accent)]">
        {icon}
      </span>
      <span>{label}</span>
    </button>
  )
}

// ── Quick Action ─────────────────────────────────────────────────

interface QuickActionProps {
  label: string
  icon: string
  onClick: () => void
  accentColor: string
  disabled?: boolean
  badge?: string
}

function QuickAction({
  label,
  icon,
  onClick,
  accentColor,
  disabled,
  badge,
}: QuickActionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'relative overflow-hidden flex min-h-12 w-full items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium transition-all',
        'border-[var(--theme-border)] bg-[var(--theme-card)] text-left',
        disabled
          ? 'cursor-not-allowed opacity-60'
          : 'hover:border-[var(--theme-accent-border)] hover:scale-[1.01] active:scale-[0.99]',
      )}
    >
      <div
        className="flex size-7 shrink-0 items-center justify-center rounded-md text-sm"
        style={{ background: `${accentColor}18` }}
      >
        {icon}
      </div>
      <span
        className="min-w-0 flex-1 text-xs font-semibold"
        style={{ color: 'var(--theme-text)' }}
      >
        {label}
      </span>
      {badge ? (
        <span className="ml-auto shrink-0 rounded-full border border-amber-300 bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-amber-700">
          {badge}
        </span>
      ) : null}
      <div
        className="absolute bottom-0 left-0 right-0 h-[2px]"
        style={{
          background: `linear-gradient(90deg, ${accentColor}, transparent)`,
        }}
      />
    </button>
  )
}

// ── Session Row (minimal) ────────────────────────────────────────

interface SessionRowProps {
  session: ClaudeSession
  maxTokens: number
  onClick: () => void
  palette: ReturnType<typeof readDashboardPalette>
}

function SessionRow({
  session,
  maxTokens,
  onClick,
  palette,
}: SessionRowProps) {
  const tokens = (session.input_tokens ?? 0) + (session.output_tokens ?? 0)
  const msgs = session.message_count ?? 0
  const tools = session.tool_call_count ?? 0
  const barWidth = maxTokens > 0 ? Math.max(1, (tokens / maxTokens) * 100) : 0

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left px-4 py-2.5 rounded-lg hover:bg-[var(--theme-card2)] transition-colors group"
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[13px] font-medium text-ink truncate flex-1 group-hover:text-ink">
          {session.title || session.id}
        </span>
        <span className="text-[10px] tabular-nums text-muted shrink-0">
          {session.started_at ? timeAgo(session.started_at) : ''}
        </span>
      </div>
      <div className="mb-1.5 flex items-center gap-2 text-[10px] text-neutral-500">
        {session.model && (
          <span
            className="rounded px-1.5 py-0.5 font-mono text-[9px] font-medium"
            style={{
              background: alpha(palette.accent, 0.1),
              color: palette.accent,
            }}
          >
            {session.model}
          </span>
        )}
        <span>{msgs} msgs</span>
        {tools > 0 && <span>{tools} tools</span>}
        {tokens > 0 && <span>{formatNumber(tokens)} tok</span>}
      </div>
      <div className="h-[3px] rounded-full w-full bg-[var(--theme-border)] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${barWidth}%`,
            background: `linear-gradient(90deg, ${palette.accent}, ${palette.accentSecondary})`,
          }}
        />
      </div>
    </button>
  )
}

// ── Main Dashboard ───────────────────────────────────────────────

export default function DashboardScreen({
  navigate = (path: string) => { window.location.hash = path },
  sessionsAvailable = true,
  skillsAvailable = true,
}: DashboardScreenProps) {
  const [isDark, setIsDark] = useState(() => {
    if (typeof document === 'undefined') return true
    const dt = document.documentElement.getAttribute('data-theme') || ''
    return !dt.endsWith('-light')
  })

  // Sessions data (replaces useQuery)
  const [rawSessions, setRawSessions] = useState<Array<Record<string, unknown>>>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)

  useEffect(() => {
    if (!sessionsAvailable) return
    setSessionsLoading(true)
    const fetchSessions = async () => {
      try {
        const res = await fetch('/api/sessions?limit=200&offset=0')
        if (!res.ok) { setRawSessions([]); return }
        const data = await res.json() as { sessions?: Array<Record<string, unknown>> }
        setRawSessions(data.sessions ?? [])
      } catch {
        setRawSessions([])
      } finally {
        setSessionsLoading(false)
      }
    }
    fetchSessions()
    const id = setInterval(fetchSessions, 30_000)
    return () => clearInterval(id)
  }, [sessionsAvailable])

  // Adapter shape kept for the legacy fallbacks that still reference
  // ClaudeSession (HeroMetrics fallback path, etc.).
  const sessions = useMemo(
    () =>
      rawSessions.map((s) => ({
        id: (s.key ?? s.id) as string,
        started_at: s.startedAt ? (s.startedAt as number) / 1000 : undefined,
        message_count: (s.message_count as number | undefined) ?? 0,
        tool_call_count: (s.tool_call_count as number | undefined) ?? 0,
        input_tokens: (s.tokenCount as number | undefined) ?? 0,
        output_tokens: 0,
      })) as Array<ClaudeSession>,
    [rawSessions],
  )

  // Enriched rows for the Sessions Intelligence card. Keeps the rich
  // fields (`derivedTitle`, `kind`, `status`, `source`, `updatedAt`,
  // etc.) the legacy adapter dropped.
  const sessionRows: Array<SessionRowData> = useMemo(
    () =>
      [...rawSessions]
        .sort(
          (a, b) =>
            ((b.updatedAt as number | undefined) ??
              (b.startedAt as number | undefined) ??
              0) -
            ((a.updatedAt as number | undefined) ??
              (a.startedAt as number | undefined) ??
              0),
        )
        .slice(0, 12)
        .map((s) => ({
          key: String(s.key ?? s.id ?? ''),
          title:
            (s.derivedTitle as string | undefined) ||
            (s.title as string | undefined) ||
            (s.preview as string | undefined) ||
            String(s.key ?? ''),
          kind: String(s.kind ?? 'chat'),
          status: String(s.status ?? ''),
          source: (s.source as string | undefined) ?? null,
          model: (s.model as string | undefined) ?? null,
          messageCount:
            ((s.messageCount as number | undefined) ??
              (s.message_count as number | undefined) ??
              0),
          toolCallCount:
            ((s.toolCallCount as number | undefined) ??
              (s.tool_call_count as number | undefined) ??
              0),
          tokenCount:
            ((s.tokenCount as number | undefined) ??
              (s.totalTokens as number | undefined) ??
              0),
          startedAt: (s.startedAt as number | undefined) ?? null,
          updatedAt: (s.updatedAt as number | undefined) ?? null,
        })),
    [rawSessions],
  )

  const stats = useMemo(() => {
    let totalMessages = 0,
      totalToolCalls = 0,
      totalTokens = 0
    for (const s of sessions) {
      totalMessages += s.message_count ?? 0
      totalToolCalls += s.tool_call_count ?? 0
      totalTokens += (s.input_tokens ?? 0) + (s.output_tokens ?? 0)
    }
    return {
      totalSessions: sessions.length,
      totalMessages,
      totalToolCalls,
      totalTokens,
    }
  }, [sessions])

  const recentSessions = useMemo(
    () =>
      [...sessions]
        .sort((a, b) => (b.started_at ?? 0) - (a.started_at ?? 0))
        .slice(0, 6),
    [sessions],
  )

  const maxTokens = useMemo(() => {
    let max = 0
    for (const s of recentSessions) {
      const t = (s.input_tokens ?? 0) + (s.output_tokens ?? 0)
      if (t > max) max = t
    }
    return max
  }, [recentSessions])

  // Skills count (replaces useQuery)
  const [skillsInstalled, setSkillsInstalled] = useState(0)

  useEffect(() => {
    if (!skillsAvailable) return
    const fetchSkillsCount = async () => {
      try {
        const res = await fetch('/api/skills?tab=installed&limit=200&summary=search')
        if (!res.ok) { setSkillsInstalled(0); return }
        const data = await res.json() as { skills?: Array<unknown> }
        setSkillsInstalled(data.skills?.length ?? 0)
      } catch {
        setSkillsInstalled(0)
      }
    }
    fetchSkillsCount()
    const id = setInterval(fetchSkillsCount, 60_000)
    return () => clearInterval(id)
  }, [skillsAvailable])

  // Period selector for analytics; persists across navigation via
  // localStorage so refreshes don't reset the operator's preference.
  const [period, setPeriod] = useState<number>(() => {
    if (typeof window === 'undefined') return 30
    const stored = window.localStorage.getItem('dashboard.analyticsPeriod')
    const n = Number(stored)
    if (n === 7 || n === 14 || n === 30) return n
    return 30
  })
  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(
        'dashboard.analyticsPeriod',
        String(period),
      )
    }
  }, [period])

  // Dashboard overview data (replaces useQuery)
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)

  useEffect(() => {
    setOverviewLoading(true)
    const fetchOverview = async () => {
      try {
        const res = await fetch(`/api/dashboard/overview?days=${period}&achievements=5`)
        if (!res.ok) return
        const data = await res.json() as DashboardOverview
        setOverview(data)
      } catch {
        // silent
      } finally {
        setOverviewLoading(false)
      }
    }
    fetchOverview()
    const id = setInterval(fetchOverview, 30_000)
    return () => clearInterval(id)
  }, [period])

  const palette = useDashboardPalette()

  const applyTheme = (mode: string) => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', mode)
    }
  }

  return (
    <div className="min-h-full">
      {/* Floating mobile nav: hamburger left, theme toggle right */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-2 h-12" style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}>
        <button
          type="button"
          aria-label="Open navigation menu"
          className="flex items-center justify-center w-11 h-11 rounded-xl active:bg-white/10 transition-colors touch-manipulation"
        >
          <svg width="20" height="16" viewBox="0 0 20 16" fill="none" className="opacity-70" style={{ color: 'var(--color-ink, #111)' }}>
            <path d="M1 1.5H19M1 8H19M1 14.5H13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
        <button
          type="button"
          aria-label="Toggle theme"
          onClick={() => {
            const LIGHT_DARK_PAIRS: Record<string, string> = {
              'claude-nous': 'claude-nous-light',
              'claude-nous-light': 'claude-nous',
              'claude-official': 'claude-official-light',
              'claude-official-light': 'claude-official',
              'claude-classic': 'claude-classic-light',
              'claude-classic-light': 'claude-classic',
              'claude-slate': 'claude-slate-light',
              'claude-slate-light': 'claude-slate',
            }
            const cur = document.documentElement.getAttribute('data-theme') || 'claude-official'
            const nextDataTheme = LIGHT_DARK_PAIRS[cur] || (isDark ? 'claude-official-light' : 'claude-official')
            applyTheme(nextDataTheme)
            setIsDark(!nextDataTheme.endsWith('-light'))
          }}
          className="flex items-center justify-center w-11 h-11 rounded-xl active:bg-white/10 transition-colors touch-manipulation"
          style={{ color: 'var(--theme-muted)' }}
        >
          {isDark ? <Sun size={20} strokeWidth={1.5} /> : <Moon size={20} strokeWidth={1.5} />}
        </button>
      </div>
      <div className="px-4 pt-14 md:pt-4 py-4 md:px-8 md:py-6 lg:px-10 space-y-5 pb-28">
      {/* ── Header: brand lockup left, action cluster right.
           Iteration 010: dropped redundant "Dashboard" eyebrow (the
           page IS the dashboard); promoted "Hermes Workspace" to
           the primary heading at a larger weight. Logo bumped from
           36px → 44px and gets a soft accent glow + ring so the
           lockup commands the left side instead of feeling like
           filler before the action cluster. Kept anchored left
           (not centered) on purpose: ops dashboards put brand left
           + actions right because that's the spatial hierarchy
           operators expect (Linear, Vercel, Datadog all do this). */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <span
            className="relative inline-flex shrink-0 items-center justify-center rounded-xl border"
            style={{
              width: 44,
              height: 44,
              borderColor:
                'color-mix(in srgb, var(--theme-accent) 35%, var(--theme-border))',
              background:
                'linear-gradient(135deg, color-mix(in srgb, var(--theme-accent) 14%, var(--theme-card)), var(--theme-card))',
              boxShadow:
                '0 0 0 4px color-mix(in srgb, var(--theme-accent) 6%, transparent)',
            }}
          >
            <img
              src="/claude-avatar.webp"
              alt="Hermes Workspace logo"
              className="size-8 rounded-md"
              style={{ background: 'transparent' }}
            />
          </span>
          {/* Iter 011: dropped the 'Operator console · vX.Y.Z'
              eyebrow. The gateway version is already on the OpsStrip
              (♦ GATEWAY V0.12.0), so the eyebrow was duplicating it.
              Single bold lockup feels cleaner; vertical centering on
              the lockup matches the height of the action cluster on
              the right so they don't visually drift. */}
          <div className="flex flex-col justify-center">
            <h1
              className="text-2xl font-bold tracking-tight"
              style={{
                color: 'var(--theme-text)',
                letterSpacing: '-0.015em',
                lineHeight: 1.1,
              }}
            >
              Hermes Workspace
            </h1>
          </div>
        </div>
        {/* Action row: hierarchy per Hermes Agent review.
           New Chat is primary (full button + accent), Terminal +
           Skills are secondary, Settings collapses to icon-only. */}
        <div className="flex w-full flex-wrap items-center justify-end gap-2 lg:max-w-xl">
          <button
            type="button"
            onClick={() => navigate('/chat/new')}
            className="group relative inline-flex items-center gap-2 overflow-hidden rounded-lg px-3.5 py-2 text-sm font-semibold uppercase tracking-[0.05em] transition-all hover:scale-[1.02] active:scale-[0.99]"
            style={{
              background: `linear-gradient(135deg, ${palette.accent}, ${palette.accentSecondary})`,
              color: 'var(--theme-on-accent, white)',
              boxShadow: `0 6px 18px -8px ${palette.accent}aa, inset 0 1px 0 0 rgba(255,255,255,0.18)`,
            }}
          >
            <span
              aria-hidden
              className="pointer-events-none absolute inset-0 opacity-0 transition-opacity group-hover:opacity-100"
              style={{
                background:
                  'linear-gradient(135deg, rgba(255,255,255,0.15), transparent 60%)',
              }}
            />
            <MessageSquarePlus size={16} strokeWidth={1.8} />
            <span>New Chat</span>
          </button>
          <SecondaryAction
            label="Terminal"
            icon={<Terminal size={14} strokeWidth={1.6} />}
            onClick={() => navigate('/terminal')}
          />
          <SecondaryAction
            label="Skills"
            icon={<Puzzle size={14} strokeWidth={1.6} />}
            onClick={() => navigate('/skills')}
            disabled={!skillsAvailable}
          />
          {/* Edit toggle: enters "layout edit mode" where each widget
              shows an X button and a banner appears for re-adding
              hidden widgets. Persisted to localStorage. */}
          <button
            type="button"
            aria-label="Edit layout"
            title="Edit layout"
            className="inline-flex size-9 items-center justify-center rounded-lg border transition-all hover:scale-[1.05] hover:bg-[var(--theme-card)]/70"
            style={{
              borderColor: 'var(--theme-border)',
              background: 'linear-gradient(135deg, color-mix(in srgb, var(--theme-card) 80%, transparent), transparent)',
              color: 'var(--theme-muted)',
            }}
          >
            <Pencil size={15} strokeWidth={1.7} />
          </button>
          <button
            type="button"
            aria-label="Settings"
            title="Settings"
            onClick={() => navigate('/settings')}
            className="inline-flex size-9 items-center justify-center rounded-lg border transition-all hover:scale-[1.05] hover:bg-[var(--theme-card)]/70 hover:text-[var(--theme-text)]"
            style={{
              borderColor: 'var(--theme-border)',
              color: 'var(--theme-muted)',
              background:
                'linear-gradient(135deg, color-mix(in srgb, var(--theme-card) 80%, transparent), transparent)',
            }}
          >
            <Settings size={15} strokeWidth={1.7} />
          </button>
        </div>
      </div>

      {/* ── Attention marquee ── */}
      {(overview?.incidents?.length ?? 0) > 0 ? (
        <div className="text-center text-sm text-muted py-2">
          Attention alerts active
        </div>
      ) : null}

      {/* ── Ops strip ── */}
      <div className="flex items-center gap-2 text-xs text-muted py-1">
        <span>Status: {overview?.status ? 'Online' : '—'}</span>
      </div>

      {/* ── Hero Metrics: 3 analytics tiles + Active Model KPI in slot 4 ── */}
      <HeroMetrics
        analytics={overview?.analytics ?? null}
        fallback={{
          sessions: stats.totalSessions,
          messages: stats.totalMessages,
          toolCalls: stats.totalToolCalls,
          tokens: stats.totalTokens,
        }}
        extraTile={
          <ActiveModelKpi
            modelInfo={overview?.modelInfo ?? null}
            analytics={overview?.analytics ?? null}
          />
        }
      />

      {/* ── Analytics chart (left) + side cards ── */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <GlassCard title="Analytics" accentColor={palette.accent} className="h-full">
            <div className="text-sm text-muted">Analytics chart placeholder</div>
          </GlassCard>
        </div>
        <div className="flex flex-col gap-3 lg:col-span-4">
          <GlassCard title="Top Models" accentColor={palette.accent}>
            <div className="text-sm text-muted">Top models placeholder</div>
          </GlassCard>
          <GlassCard title="Cache Efficiency" accentColor={palette.success}>
            <div className="text-sm text-muted">Cache efficiency placeholder</div>
          </GlassCard>
          <GlassCard title="Provider Mix" accentColor={palette.accentSecondary}>
            <div className="text-sm text-muted">Provider mix placeholder</div>
          </GlassCard>
        </div>
      </div>

      {/* ── Primary content: Sessions + side rail ── */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        <div className="flex min-h-full flex-col gap-3 lg:col-span-8">
          <GlassCard title="Recent Sessions" accentColor={palette.accent}>
            {recentSessions.map((s) => (
              <SessionRow
                key={s.id}
                session={s}
                maxTokens={maxTokens}
                onClick={() => navigate(`/chat/${s.id}`)}
                palette={palette}
              />
            ))}
          </GlassCard>
        </div>
        <div className="flex min-h-full flex-col gap-3 lg:col-span-4">
          <GlassCard title="Achievements" accentColor={palette.warning}>
            <div className="text-sm text-muted">Achievements placeholder</div>
          </GlassCard>
          <SkillsWidget
            palette={palette}
            onOpen={() => navigate('/skills')}
            usage={overview?.skillsUsage ?? null}
          />
        </div>
      </div>
      </div>
    </div>
  )
}
