<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useNotification } from '../composables/useNotification'

interface ProjectResponse {
  project_dir: string | null
}

interface ErrorResponse {
  detail?: string | Array<{ msg?: string }>
}

interface ComponentAssociation {
  component: string
  component_url?: string
}

interface ConnectivityMap {
  server_url?: string
  associations?: ComponentAssociation[]
}

type Reachability = 'online' | 'offline' | 'unknown'

interface ComponentStatus {
  component: string
  url: string
  online: boolean
  status_code: number | null
  latency_ms: number | null
  error: string | null
  reachability: Reachability | null
  reachability_supported: boolean | null
}

const { notify } = useNotification()

const projectLoaded = ref<boolean | null>(null)
const connectivity = ref<ConnectivityMap | null>(null)
const statuses = ref<Record<string, ComponentStatus>>({})
const pinging = ref<Record<string, boolean>>({})
const isLoadingPage = ref(true)
const pageError = ref('')
const isPingingAll = ref(false)

const associations = computed(() => connectivity.value?.associations ?? [])
const configuredAssociations = computed(() =>
  associations.value.filter(assoc => Boolean(assoc.component_url?.trim())),
)
const serverUrl = computed(() => connectivity.value?.server_url?.trim() ?? '')

function apiError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

async function responseError(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json() as ErrorResponse
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map(error => error.msg)
        .filter((value): value is string => Boolean(value))
      if (messages.length) return messages.join(', ')
    }
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail
  } catch {
    // Use the friendly fallback when the response is not JSON.
  }
  return fallback
}

function normalizeUrlPart(value: string, side: 'left' | 'right') {
  if (side === 'left') return value.replace(/\/+$/, '')
  return value.replace(/^\/+/, '')
}

function fullUrl(assoc: ComponentAssociation): string {
  const componentUrl = assoc.component_url?.trim()
  if (!componentUrl) return ''
  const base = normalizeUrlPart(serverUrl.value, 'left')
  const path = normalizeUrlPart(componentUrl, 'right')
  return base ? `${base}/${path}` : path
}

function hasComponentUrl(assoc: ComponentAssociation): boolean {
  return Boolean(assoc.component_url?.trim())
}

function statusClass(assoc: ComponentAssociation): string {
  if (!hasComponentUrl(assoc)) return 'not-configured'
  const status = statuses.value[assoc.component]
  if (!status) return 'unchecked'
  if (status.reachability) return status.reachability
  return status.online ? 'online' : 'offline'
}

function statusLabel(assoc: ComponentAssociation): string {
  if (!hasComponentUrl(assoc)) return 'Not configured'
  const status = statuses.value[assoc.component]
  if (!status) return 'Unchecked'
  if (status.reachability === 'online') return 'Online'
  if (status.reachability === 'offline') return 'Offline'
  if (status.reachability === 'unknown') return 'Unknown'
  return status.online ? 'Online' : 'Offline'
}

function statusDetail(assoc: ComponentAssociation): string {
  if (!hasComponentUrl(assoc)) return 'No endpoint path'
  const status = statuses.value[assoc.component]
  if (!status) return 'Not checked yet'
  if (status.online) {
    const parts = []
    if (status.status_code !== null) parts.push(`HTTP ${status.status_code}`)
    if (status.latency_ms !== null) parts.push(`${status.latency_ms} ms`)
    return parts.join(' / ') || 'Reachable'
  }
  return status.error || 'Request failed'
}

function needsFlowchemUpdate(assoc: ComponentAssociation): boolean {
  const status = statuses.value[assoc.component]
  return Boolean(status?.online && status.reachability_supported === false)
}

function collectUnsupported(components: string[]): string[] {
  return components.filter(name => {
    const status = statuses.value[name]
    return Boolean(status?.online && status.reachability_supported === false)
  })
}

function notifyUnsupported(components: string[]) {
  const unsupported = collectUnsupported(components)
  if (unsupported.length === 0) return
  if (unsupported.length === 1) {
    notify(
      `"${unsupported[0]}" does not expose /is-reachable — update flowchem on that device server to see live status.`,
      'warning',
    )
  } else {
    notify(
      `${unsupported.length} devices don't expose /is-reachable — update flowchem on those device servers to see live status.`,
      'warning',
    )
  }
}

function isPinging(component: string): boolean {
  return Boolean(pinging.value[component])
}

async function initialize() {
  isLoadingPage.value = true
  pageError.value = ''

  try {
    const projectResponse = await fetch('/project/')
    if (!projectResponse.ok) {
      throw new Error(
        await responseError(projectResponse, 'Could not check the current project.'),
      )
    }

    const project = await projectResponse.json() as ProjectResponse
    projectLoaded.value = Boolean(project.project_dir)
    if (!projectLoaded.value) return

    const componentsResponse = await fetch('/components/')
    if (!componentsResponse.ok) {
      throw new Error(
        await responseError(componentsResponse, 'Could not load device connectivity.'),
      )
    }

    connectivity.value = await componentsResponse.json() as ConnectivityMap
    statuses.value = {}
  } catch (error) {
    pageError.value = apiError(error, 'Could not load devices.')
  } finally {
    isLoadingPage.value = false
  }
}

async function pingComponent(assoc: ComponentAssociation) {
  if (!hasComponentUrl(assoc) || isPinging(assoc.component)) return

  pinging.value[assoc.component] = true
  try {
    const response = await fetch(
      `/components/ping/${encodeURIComponent(assoc.component)}`,
    )
    if (!response.ok) {
      throw new Error(
        await responseError(response, `Could not ping ${assoc.component}.`),
      )
    }
    const status = await response.json() as ComponentStatus
    statuses.value[status.component] = status
  } catch (error) {
    statuses.value[assoc.component] = {
      component: assoc.component,
      url: fullUrl(assoc),
      online: false,
      status_code: null,
      latency_ms: null,
      error: apiError(error, `Could not ping ${assoc.component}.`),
      reachability: null,
      reachability_supported: null,
    }
  } finally {
    pinging.value[assoc.component] = false
  }
}

async function pingComponentAndNotify(assoc: ComponentAssociation) {
  await pingComponent(assoc)
  notifyUnsupported([assoc.component])
}

async function pingAll() {
  if (isPingingAll.value || configuredAssociations.value.length === 0) return

  isPingingAll.value = true
  try {
    await Promise.all(configuredAssociations.value.map(assoc => pingComponent(assoc)))
    notifyUnsupported(configuredAssociations.value.map(assoc => assoc.component))
  } finally {
    isPingingAll.value = false
  }
}

onMounted(() => {
  void initialize()
})
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Connectivity</p>
        <h1 class="page-title">Devices</h1>
        <p class="page-description">
          Inspect component mappings and run connectivity checks against configured endpoints.
        </p>
      </div>
      <button
        v-if="projectLoaded"
        type="button"
        class="button primary"
        :disabled="isPingingAll || configuredAssociations.length === 0"
        @click="pingAll"
      >
        <span v-if="isPingingAll" class="mini-spinner" aria-hidden="true"></span>
        {{ isPingingAll ? 'Pinging...' : 'Ping All' }}
      </button>
    </header>

    <section v-if="isLoadingPage" class="state-card" aria-live="polite">
      <span class="spinner" aria-hidden="true"></span>
      <h2>Loading devices</h2>
      <p>Checking the current project and connectivity map.</p>
    </section>

    <section v-else-if="pageError" class="state-card error-state" role="alert">
      <h2>Devices unavailable</h2>
      <p>{{ pageError }}</p>
      <button type="button" class="button" @click="initialize">Try again</button>
    </section>

    <section v-else-if="projectLoaded === false" class="state-card">
      <h2>Open a project to inspect devices</h2>
      <p>The connectivity map is loaded from the active project.</p>
    </section>

    <section v-else class="devices-panel">
      <div class="panel-header">
        <div>
          <h2>Connectivity Map</h2>
          <p>
            {{ associations.length }}
            {{ associations.length === 1 ? 'component' : 'components' }}
            configured against
            <code>{{ serverUrl || 'no server URL' }}</code>.
          </p>
        </div>
      </div>



      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Component</th>
              <th>URL</th>
              <th><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="assoc in associations" :key="assoc.component">
              <td>
                <span class="status-stack">
                  <span class="status-badge" :class="statusClass(assoc)">
                    <span class="status-dot" aria-hidden="true"></span>
                    {{ statusLabel(assoc) }}
                  </span>
                  <small>{{ statusDetail(assoc) }}</small>
                  <small v-if="needsFlowchemUpdate(assoc)" class="update-warning">
                    ⚠ flowchem update needed
                  </small>
                </span>
              </td>
              <td class="component-cell">{{ assoc.component }}</td>
              <td class="url-cell">
                <code v-if="fullUrl(assoc)">{{ fullUrl(assoc) }}</code>
                <span v-else class="not-configured">not configured</span>
              </td>
              <td class="actions-cell">
                <button
                  type="button"
                  class="button compact"
                  :disabled="!hasComponentUrl(assoc) || isPingingAll || isPinging(assoc.component)"
                  @click="pingComponentAndNotify(assoc)"
                >
                  <span
                    v-if="isPinging(assoc.component)"
                    class="mini-spinner"
                    aria-hidden="true"
                  ></span>
                  {{ isPinging(assoc.component) ? 'Pinging' : 'Ping' }}
                </button>
              </td>
            </tr>
            <tr v-if="associations.length === 0">
              <td colspan="4" class="empty-row">No component associations found.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.button {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.62rem 0.95rem;
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-soft);
  cursor: pointer;
  font-size: 0.83rem;
  font-weight: 680;
}

.button.primary {
  color: #ffffff;
  border-color: var(--color-primary);
  background: var(--color-primary);
  box-shadow: 0 6px 16px color-mix(in srgb, var(--color-primary) 20%, transparent);
}

.button:hover:not(:disabled) {
  border-color: var(--color-border-hover);
  background: var(--color-background-mute);
}

.button.primary:hover:not(:disabled) {
  border-color: var(--color-primary-hover);
  background: var(--color-primary-hover);
}

.button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
  box-shadow: none;
}

.button.compact {
  min-height: 34px;
  padding: 0.45rem 0.7rem;
  font-size: 0.76rem;
}

.state-card,
.devices-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
}

.state-card {
  min-height: 320px;
  display: grid;
  place-items: center;
  padding: 2.25rem;
  color: var(--color-text-muted);
  text-align: center;
}

.state-card h2 {
  margin: 0.85rem 0 0.4rem;
  color: var(--color-heading);
  font-size: 1.05rem;
}

.state-card p {
  max-width: 460px;
  margin-bottom: 0;
}

.error-state {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 24%, var(--color-border));
  background: var(--color-danger-soft);
}

.error-state p {
  margin-bottom: 1rem;
}

.spinner,
.mini-spinner {
  display: inline-block;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-right-color: transparent;
  animation: spin 800ms linear infinite;
}

.spinner {
  width: 30px;
  height: 30px;
  color: var(--color-primary);
}

.mini-spinner {
  width: 14px;
  height: 14px;
}

.devices-panel {
  overflow: hidden;
}

.panel-header {
  padding: 1.25rem 1.35rem;
  border-bottom: 1px solid var(--color-border);
}

.panel-header h2 {
  margin: 0;
  color: var(--color-heading);
  font-size: 1.08rem;
  font-weight: 720;
}

.panel-header p {
  margin: 0.35rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.84rem;
}

code {
  padding: 0.12rem 0.3rem;
  color: var(--color-heading);
  border-radius: 5px;
  background: var(--color-background-mute);
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 0.82em;
}

.table-wrap {
  width: 100%;
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
}

th,
td {
  padding: 0.85rem 1.35rem;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: middle;
}

th {
  color: var(--color-text-muted);
  background: var(--color-background-mute);
  font-size: 0.68rem;
  font-weight: 780;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

tbody tr:last-child td {
  border-bottom: 0;
}

.status-stack {
  display: inline-flex;
  flex-direction: column;
  gap: 0.28rem;
}

.status-stack small {
  max-width: 280px;
  overflow: hidden;
  color: var(--color-text-muted);
  font-size: 0.72rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-badge {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.28rem 0.55rem;
  border-radius: 999px;
  background: var(--color-background-mute);
  font-size: 0.72rem;
  font-weight: 760;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.status-badge.unchecked {
  color: var(--color-text-muted);
}

.status-badge.online {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.status-badge.offline {
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.status-badge.not-configured {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.status-badge.unknown {
  color: var(--color-text-muted);
  background: var(--color-background-mute);
}

.status-stack small.update-warning {
  color: var(--color-warning);
}

.component-cell {
  color: var(--color-heading);
  font-weight: 680;
}

.url-cell code {
  white-space: nowrap;
}

.not-configured {
  color: var(--color-text-muted);
  font-style: italic;
}

.actions-cell {
  width: 1%;
  text-align: right;
  white-space: nowrap;
}

.empty-row {
  padding: 2rem;
  color: var(--color-text-muted);
  text-align: center;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 640px) {
  .button.primary {
    width: 100%;
  }

  .panel-header {
    padding: 1rem;
  }

  th,
  td {
    padding: 0.75rem 1rem;
  }

  .state-card {
    min-height: 260px;
    padding: 1.5rem 1rem;
    border-radius: var(--radius-md);
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner,
  .mini-spinner {
    animation: none;
  }
}
</style>
