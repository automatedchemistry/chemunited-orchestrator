/**
 * The `chemunited` module that custom pages and widgets import:
 *
 *   import { api, callCustomRoute, attempt, notify } from 'chemunited'
 *
 * Part of the public UI API: within a UI_API_VERSION it only gains additions.
 */
import { computed } from 'vue'
import { useNotification } from '../composables/useNotification'
import { useRunStatusStore } from '../stores/runStatus'

export { UI_API_VERSION as version } from './manifest'
export { usePlatformLive } from '../composables/usePlatformLive'
export { default as SchemaForm } from '../components/SchemaForm.vue'

export type NotificationType = 'success' | 'error' | 'info' | 'warning'

/** A request the server answered with an error status, or a custom route that failed. */
export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(message: string, status: number, detail: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function failure(response: Response): Promise<ApiError> {
  let detail: unknown = null
  let message = `HTTP ${response.status}`
  try {
    detail = (await response.json() as { detail?: unknown }).detail ?? null
    if (typeof detail === 'string' && detail.trim()) message = detail
    else if (Array.isArray(detail)) {
      const parts = detail.map(item => (item as { msg?: string })?.msg).filter(Boolean)
      if (parts.length) message = parts.join(', ')
    }
  } catch {
    // Not JSON: keep the status.
  }
  return new ApiError(message, response.status, detail)
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: { Accept: 'application/json' } }
  if (body !== undefined) {
    init.headers = { ...init.headers, 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }
  // fetch() carries the API token for writes (see useApiToken.ts).
  const response = await fetch(url, init)
  if (!response.ok) throw await failure(response)
  if (response.status === 204) return undefined as T
  const type = response.headers.get('content-type') ?? ''
  return (type.includes('json') ? await response.json() : await response.text()) as T
}

/** JSON requests to the dashboard's REST API; failures throw an ApiError. */
export const api = {
  get: <T = unknown>(url: string) => request<T>('GET', url),
  post: <T = unknown>(url: string, body?: unknown) => request<T>('POST', url, body),
  put: <T = unknown>(url: string, body?: unknown) => request<T>('PUT', url, body),
  delete: <T = unknown>(url: string) => request<T>('DELETE', url),
}

interface CustomRouteResult<T> {
  name: string
  ok: boolean
  result: T | null
  error: string | null
}

/**
 * Call a function from customizations/routers/router_hook.py and return its
 * result. Throws an ApiError when the call fails or the function raises.
 */
export async function callCustomRoute<T = unknown>(
  name: string,
  kwargs: Record<string, unknown> = {},
): Promise<T> {
  const body = await api.post<CustomRouteResult<T>>(`/custom/${encodeURIComponent(name)}`, kwargs)
  if (!body.ok) throw new ApiError(body.error ?? `${name} failed`, 200, body)
  return body.result as T
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/** Show a message in the dashboard's notification bar. */
export function notify(message: string, type: NotificationType = 'info'): void {
  useNotification().notify(message, type)
}

/**
 * Run `work`, notify on success (if `success` is given) and on failure, and
 * never throw: resolves to the result, or undefined when `work` failed. Use it
 * so a page doesn't need its own error handling.
 */
export async function attempt<T>(
  work: () => Promise<T>,
  messages: { success?: string, error?: string } = {},
): Promise<T | undefined> {
  try {
    const result = await work()
    if (messages.success) notify(messages.success, 'success')
    return result
  } catch (error) {
    notify(`${messages.error ?? 'That did not work'}: ${errorMessage(error)}`, 'error')
    return undefined
  }
}

/** The active run, as the dashboard tracks it. */
export function useRunStatus() {
  const store = useRunStatusStore()
  return {
    runId: computed(() => store.activeRunId),
    runState: computed(() => store.runState),
    stopReason: computed(() => store.stopReason),
    refresh: () => store.checkActiveRun(),
  }
}

/** URL of a file under customizations/ui/. */
export function extUrl(path: string): string {
  return `/ui/ext/${path.replace(/^\/+/, '')}`
}
