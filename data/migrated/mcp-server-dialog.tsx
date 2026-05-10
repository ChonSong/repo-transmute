import { useEffect, useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import {
  DialogContent,
  DialogDescription,
  DialogRoot,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  ScrollAreaRoot,
  ScrollAreaScrollbar,
  ScrollAreaThumb,
  ScrollAreaViewport,
} from '@/components/ui/scroll-area'
import { useMcpCapabilityMode } from '@/screens/mcp/hooks/use-mcp-capability-mode'
import type { McpClientInput, McpServer } from '@/types/mcp'

interface Props {
  open: boolean
  initial?: McpServer | McpClientInput | null
  onClose: () => void
}

const EMPTY: McpClientInput = {
  name: '',
  transportType: 'http',
  url: '',
  args: [],
  env: {},
  headers: {},
  authType: 'none',
  toolMode: 'all',
}

const FIELD =
  'h-9 w-full rounded-lg border border-primary-200 bg-primary-100/60 px-3 text-sm text-ink outline-none transition-colors focus:border-primary'

const LABEL = 'flex flex-col gap-1.5 text-sm text-primary-500'

function fromServer(server: McpServer): McpClientInput {
  return {
    name: server.name,
    transportType: server.transportType,
    url: server.url,
    command: server.command,
    args: server.args,
    env: {},
    headers: {},
    authType: server.authType,
    toolMode: server.toolMode,
    includeTools: server.includeTools,
    excludeTools: server.excludeTools,
  }
}

function isMcpServer(value: unknown): value is McpServer {
  return Boolean(value && typeof value === 'object' && 'discoveredToolsCount' in value)
}

// ---------------------------------------------------------------------------
// Mutation hooks using fetch + useState (replaces @tanstack/react-query)
// ---------------------------------------------------------------------------

interface UseUpsertReturn {
  isPending: boolean
  error: Error | null
  mutateAsync: (input: McpClientInput & { bearerToken?: string }) => Promise<unknown>
}

function useUpsertMcpServer(): UseUpsertReturn {
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const mutateAsync = useCallback(async (input: McpClientInput & { bearerToken?: string }) => {
    setIsPending(true)
    setError(null)
    try {
      const { bearerToken, ...rest } = input
      const payload = bearerToken ? { ...rest, bearerToken } : rest
      const res = await fetch('/api/mcp/servers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(`Save failed: ${res.status}`)
      return res.json()
    } catch (e) {
      const err = e instanceof Error ? e : new Error(String(e))
      setError(err)
      throw err
    } finally {
      setIsPending(false)
    }
  }, [])

  return { isPending, error, mutateAsync }
}

interface UseDiscoverReturn {
  isPending: boolean
  error: Error | null
  data: { tools: Array<unknown> } | null
  mutate: (input: McpClientInput) => void
}

function useDiscoverMcpTools(): UseDiscoverReturn {
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [data, setData] = useState<{ tools: Array<unknown> } | null>(null)

  const mutate = useCallback(async (input: McpClientInput) => {
    setIsPending(true)
    setError(null)
    try {
      const res = await fetch('/api/mcp/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      })
      if (!res.ok) throw new Error(`Discover failed: ${res.status}`)
      const result = await res.json()
      setData(result)
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)))
    } finally {
      setIsPending(false)
    }
  }, [])

  return { isPending, error, data, mutate }
}

export default function McpServerDialog({ open, initial, onClose }: Props) {
  const upsert = useUpsertMcpServer()
  const discover = useDiscoverMcpTools()
  const { mode: capabilityMode } = useMcpCapabilityMode()
  const [draft, setDraft] = useState<McpClientInput>(EMPTY)
  const [bearerToken, setBearerToken] = useState('')
  const [initialHasBearer, setInitialHasBearer] = useState(false)
  const [authEnvRef, setAuthEnvRef] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setBearerToken('')
    if (!initial) {
      setDraft(EMPTY)
      setInitialHasBearer(false)
      setAuthEnvRef(null)
    } else if (isMcpServer(initial)) {
      setDraft(fromServer(initial))
      setInitialHasBearer(Boolean(initial.hasBearerToken))
      setAuthEnvRef(initial.authEnvRef ?? null)
    } else {
      setDraft(initial)
      setInitialHasBearer(false)
      setAuthEnvRef(null)
    }
  }, [open, initial])

  const update = (patch: Partial<McpClientInput>) =>
    setDraft((prev) => ({ ...prev, ...patch }))

  const fallbackMode = capabilityMode === 'fallback'
  const discoverDisabledReason = fallbackMode
    ? 'Discover requires runtime /api/mcp endpoint (not available in local fallback mode).'
    : ''

  return (
    <DialogRoot
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <DialogContent className="w-[min(720px,95vw)] border-primary-200 bg-primary-50/95 backdrop-blur-sm">
        <div className="flex max-h-[85vh] flex-col">
          <div className="border-b border-primary-200 px-5 py-4">
            <DialogTitle className="text-balance">
              🔌 {draft.name || (initial ? 'Edit MCP Server' : 'Add MCP Server')}
            </DialogTitle>
            <DialogDescription className="mt-1 text-pretty">
              {initial ? 'Edit MCP Server' : 'Add MCP Server'} •{' '}
              {draft.transportType.toUpperCase()} transport •{' '}
              {draft.authType || 'none'} auth
            </DialogDescription>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="rounded-md border border-primary-200 bg-primary-100/50 px-2 py-0.5 text-xs text-primary-500">
                {draft.transportType}
              </span>
              <span className="rounded-md border border-primary-200 bg-primary-100/50 px-2 py-0.5 text-xs text-primary-500">
                auth: {draft.authType || 'none'}
              </span>
              {fallbackMode ? (
                <span className="rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
                  config-only mode
                </span>
              ) : null}
            </div>
          </div>

          <ScrollAreaRoot className="h-[56vh]">
            <ScrollAreaViewport className="px-5 py-4">
              <div className="space-y-3">
                <label className={LABEL}>
                  <span>Name</span>
                  <input
                    className={FIELD}
                    value={draft.name}
                    onChange={(e) => update({ name: e.target.value })}
                    placeholder="my-mcp-server"
                  />
                </label>
                <label className={LABEL}>
                  <span>Transport</span>
                  <select
                    className={FIELD}
                    value={draft.transportType}
                    onChange={(e) =>
                      update({
                        transportType: e.target.value as 'http' | 'stdio',
                      })
                    }
                  >
                    <option value="http">HTTP</option>
                    <option value="stdio">stdio</option>
                  </select>
                </label>
                {draft.transportType === 'http' ? (
                  <label className={LABEL}>
                    <span>URL</span>
                    <input
                      className={FIELD}
                      value={draft.url || ''}
                      onChange={(e) => update({ url: e.target.value })}
                      placeholder="https://example.com/mcp"
                    />
                  </label>
                ) : (
                  <>
                    <label className={LABEL}>
                      <span>Command</span>
                      <input
                        className={FIELD}
                        value={draft.command || ''}
                        onChange={(e) => update({ command: e.target.value })}
                        placeholder="/usr/local/bin/my-mcp"
                      />
                    </label>
                    <label className={LABEL}>
                      <span>Args (one per line)</span>
                      <textarea
                        className={`${FIELD} h-auto py-2 font-mono text-xs`}
                        rows={3}
                        value={(draft.args || []).join('\n')}
                        onChange={(e) =>
                          update({
                            args: e.target.value
                              .split('\n')
                              .map((s) => s.trim())
                              .filter(Boolean),
                          })
                        }
                      />
                    </label>
                  </>
                )}
                <label className={LABEL}>
                  <span>Auth</span>
                  <select
                    className={FIELD}
                    value={draft.authType || 'none'}
                    onChange={(e) =>
                      update({
                        authType: e.target.value as 'none' | 'bearer' | 'oauth',
                      })
                    }
                  >
                    <option value="none">none</option>
                    <option value="bearer">bearer</option>
                    <option value="oauth">oauth</option>
                  </select>
                </label>
                {draft.authType === 'bearer' ? (
                  <label className={LABEL}>
                    <span>Bearer token</span>
                    <input
                      type="password"
                      className={FIELD}
                      value={bearerToken}
                      onChange={(e) => setBearerToken(e.target.value)}
                      autoComplete="off"
                      placeholder={
                        initialHasBearer
                          ? '••••••• (currently set — leave blank to keep, type to replace)'
                          : 'Enter bearer token'
                      }
                    />
                    {authEnvRef ? (
                      <span className="text-[11px] text-amber-700 dark:text-amber-300">
                        Token resolved from env var <code className="font-mono">{authEnvRef}</code> — leave blank to keep current, or type to override.
                      </span>
                    ) : initialHasBearer ? (
                      <span className="text-[11px] text-emerald-700 dark:text-emerald-300">
                        Token currently set on server. Leave blank to keep
                        existing; type a new value to replace.
                      </span>
                    ) : null}
                  </label>
                ) : null}

                {fallbackMode ? (
                  <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
                    ⚠ Local fallback mode — config-only CRUD. Live tool
                    Discover and connectivity Test require the runtime
                    /api/mcp endpoint.
                  </p>
                ) : null}
                {discover.data ? (
                  <p className="text-xs text-primary-500">
                    Discovered {discover.data.tools.length} tools.
                  </p>
                ) : null}
                {discover.error ? (
                  <p className="text-xs text-red-700 dark:text-red-300">
                    {discover.error.message}
                  </p>
                ) : null}
                {upsert.error ? (
                  <p className="text-xs text-red-700 dark:text-red-300">
                    {upsert.error.message}
                  </p>
                ) : null}
              </div>
            </ScrollAreaViewport>
            <ScrollAreaScrollbar orientation="vertical">
              <ScrollAreaThumb />
            </ScrollAreaScrollbar>
          </ScrollAreaRoot>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-primary-200 px-5 py-3">
            <p className="min-w-0 flex-1 truncate text-sm text-primary-500 text-pretty">
              Target:{' '}
              <code className="inline-code">
                {draft.transportType === 'http'
                  ? draft.url || '—'
                  : draft.command || '—'}
              </code>
            </p>
            <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              disabled={upsert.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={discover.isPending || !draft.name || fallbackMode}
              title={discoverDisabledReason}
              onClick={() => discover.mutate(draft)}
            >
              {discover.isPending ? 'Discovering…' : 'Discover'}
            </Button>
            <Button
              size="sm"
              disabled={upsert.isPending || !draft.name}
              onClick={async () => {
                const payload = bearerToken
                  ? { ...draft, bearerToken }
                  : draft
                try {
                  await upsert.mutateAsync(payload)
                  onClose()
                } finally {
                  setBearerToken('')
                }
              }}
            >
              {upsert.isPending ? 'Saving…' : 'Save'}
            </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </DialogRoot>
  )
}
