<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  DEFAULT_CONFIG,
  DEFAULT_STATE,
  type MonitoringConfig,
  type MonitoringState,
  type MonitoringVariable,
  STATE_POLL_INTERVAL_MS,
  isPlainRecord,
  normalizeConfig,
  variableKey,
} from './monitoringConfig'

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

interface DiscoveredCommand {
  command: string
  summary?: string
  parameters?: unknown[]
}

interface OpenApiParameter {
  name?: unknown
  in?: unknown
  required?: unknown
  description?: unknown
  schema?: {
    type?: unknown
  }
}

interface ParameterField {
  name: string
  required: boolean
  description: string
  type: string
}

type NoticeType = 'info' | 'error' | 'warning' | 'success'

// Reserved pseudo-component: its "commands" are function names registered in
// the project's customizations/monitoring/monitoring_hook.py rather than GET
// endpoints on a real device (see docs/api-reference.md#custom-sources).
const CUSTOM_COMPONENT = 'custom'

const projectLoaded = ref<boolean | null>(null)
const connectivity = ref<ConnectivityMap | null>(null)
const config = ref<MonitoringConfig>({ ...DEFAULT_CONFIG, variables: [] })
const state = ref<MonitoringState>({ ...DEFAULT_STATE })

const isLoading = ref(true)
const loadError = ref('')
const notice = ref('')
const noticeType = ref<NoticeType>('info')
const timingMessage = ref('')
const timingMessageType = ref<NoticeType>('info')

const selectedComponent = ref('')
const selectedCommand = ref('')
const discoveredCommands = ref<DiscoveredCommand[]>([])
const isDiscovering = ref(false)
const discoveryMessage = ref('')
const discoveryMessageType = ref<NoticeType>('info')
const paramValues = ref<Record<string, string>>({})
const rawKwargsJson = ref('{}')
const addVariableError = ref('')

let statePollTimer: ReturnType<typeof window.setInterval> | undefined

const associations = computed(() => connectivity.value?.associations ?? [])
const configuredAssociations = computed(() =>
  associations.value.filter(assoc => Boolean(assoc.component_url?.trim())),
)
// The work-server reads the config when monitoring turns on, so the list is
// locked while it polls, as it was on the Monitoring page.
const isLocked = computed(() => state.value.effective_on)
const selectedDiscoveredCommand = computed(() =>
  discoveredCommands.value.find(command => command.command === selectedCommand.value),
)
const parameterFields = computed(() =>
  normalizeParameters(selectedDiscoveredCommand.value?.parameters ?? []),
)
const canAddVariable = computed(() =>
  Boolean(selectedComponent.value && selectedCommand.value && !isLocked.value),
)

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
    // Keep the friendly fallback when the response is not JSON.
  }
  return fallback
}

function normalizeParameters(parameters: unknown[]): ParameterField[] {
  return parameters
    .map(parameter => parameter as OpenApiParameter)
    .filter(parameter => typeof parameter.name === 'string' && parameter.name.trim())
    .filter(parameter => parameter.in === undefined || parameter.in === 'query')
    .map(parameter => ({
      name: String(parameter.name),
      required: Boolean(parameter.required),
      description: typeof parameter.description === 'string' ? parameter.description : '',
      type: typeof parameter.schema?.type === 'string' ? parameter.schema.type : 'string',
    }))
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function convertParameterValue(value: string, field: ParameterField): unknown {
  if (field.type === 'integer') {
    const parsed = Number.parseInt(value, 10)
    return Number.isNaN(parsed) ? value : parsed
  }
  if (field.type === 'number') {
    const parsed = Number.parseFloat(value)
    return Number.isNaN(parsed) ? value : parsed
  }
  if (field.type === 'boolean') {
    if (value.toLowerCase() === 'true') return true
    if (value.toLowerCase() === 'false') return false
  }
  return value
}

function buildKwargs(): Record<string, unknown> {
  if (parameterFields.value.length === 0) {
    const raw = rawKwargsJson.value.trim()
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!isPlainRecord(parsed)) {
      throw new Error('Kwargs JSON must be an object.')
    }
    return parsed
  }

  const kwargs: Record<string, unknown> = {}
  for (const field of parameterFields.value) {
    const raw = paramValues.value[field.name]?.trim() ?? ''
    if (!raw) {
      if (field.required) throw new Error(`${field.name} is required.`)
      continue
    }
    kwargs[field.name] = convertParameterValue(raw, field)
  }
  return kwargs
}

async function initialize() {
  isLoading.value = true
  loadError.value = ''
  notice.value = ''

  try {
    const projectResponse = await fetch('/project/')
    if (!projectResponse.ok) {
      throw new Error(await responseError(projectResponse, 'Could not check the current project.'))
    }

    const project = await projectResponse.json() as ProjectResponse
    projectLoaded.value = Boolean(project.project_dir)
    if (!projectLoaded.value) return

    const [componentsResponse, configResponse, stateResponse] = await Promise.all([
      fetch('/components/'),
      fetch('/monitoring/config'),
      fetch('/monitoring/state'),
    ])

    if (!componentsResponse.ok) {
      throw new Error(await responseError(componentsResponse, 'Could not load device connectivity.'))
    }
    if (!configResponse.ok) {
      throw new Error(await responseError(configResponse, 'Could not load monitoring config.'))
    }
    if (!stateResponse.ok) {
      throw new Error(await responseError(stateResponse, 'Could not load monitoring state.'))
    }

    connectivity.value = await componentsResponse.json() as ConnectivityMap
    config.value = normalizeConfig(await configResponse.json() as Partial<MonitoringConfig>)
    state.value = await stateResponse.json() as MonitoringState
    startStatePolling()
  } catch (error) {
    loadError.value = apiError(error, 'Could not load the monitoring config.')
  } finally {
    isLoading.value = false
  }
}

function startStatePolling() {
  stopStatePolling()
  statePollTimer = window.setInterval(() => {
    void refreshState()
  }, STATE_POLL_INTERVAL_MS)
}

function stopStatePolling() {
  if (statePollTimer !== undefined) {
    window.clearInterval(statePollTimer)
    statePollTimer = undefined
  }
}

async function refreshState() {
  try {
    const response = await fetch('/monitoring/state')
    if (response.ok) state.value = await response.json() as MonitoringState
  } catch {
    // Leave state unchanged on a transient network error — the next poll retries.
  }
}

async function discoverCommands() {
  if (!selectedComponent.value || isLocked.value) return

  isDiscovering.value = true
  discoveryMessage.value = ''
  discoveryMessageType.value = 'info'
  discoveredCommands.value = []
  selectedCommand.value = ''
  paramValues.value = {}
  rawKwargsJson.value = '{}'
  addVariableError.value = ''

  try {
    const response = await fetch(`/monitoring/discover/${encodeURIComponent(selectedComponent.value)}`)
    if (response.status === 404) {
      discoveryMessage.value = 'Component not found.'
      discoveryMessageType.value = 'warning'
      return
    }
    if (response.status === 502) {
      discoveryMessage.value = await responseError(response, 'Device server unreachable.')
      discoveryMessageType.value = 'warning'
      return
    }
    if (!response.ok) {
      throw new Error(await responseError(response, 'Could not discover monitoring commands.'))
    }
    discoveredCommands.value = await response.json() as DiscoveredCommand[]
    if (discoveredCommands.value.length === 0) {
      discoveryMessage.value = selectedComponent.value === CUSTOM_COMPONENT
        ? 'No custom sources registered. Add one to CUSTOM_SOURCES in customizations/monitoring/monitoring_hook.py.'
        : 'No GET variables discovered for this component.'
      discoveryMessageType.value = 'info'
    }
  } catch (error) {
    discoveryMessage.value = apiError(error, 'Could not discover monitoring commands.')
    discoveryMessageType.value = 'error'
  } finally {
    isDiscovering.value = false
  }
}

function resetCommandInputs() {
  paramValues.value = {}
  rawKwargsJson.value = '{}'
  addVariableError.value = ''
}

async function addVariable() {
  if (!canAddVariable.value) return

  addVariableError.value = ''
  const nextVariable: MonitoringVariable = {
    component: selectedComponent.value,
    command: selectedCommand.value,
    kwargs: {},
  }

  if (config.value.variables.some(variable => variableKey(variable) === variableKey(nextVariable))) {
    addVariableError.value = 'This variable is already selected.'
    return
  }

  try {
    nextVariable.kwargs = buildKwargs()
  } catch (error) {
    addVariableError.value = apiError(error, 'Invalid kwargs.')
    return
  }

  config.value = {
    ...config.value,
    variables: [...config.value.variables, nextVariable],
  }
  selectedCommand.value = ''
  resetCommandInputs()

  try {
    await persistConfig()
  } catch (error) {
    addVariableError.value = apiError(error, 'Variable added, but could not be saved to the project.')
  }
}

async function removeVariable(variable: MonitoringVariable) {
  if (isLocked.value) return
  const key = variableKey(variable)
  config.value = {
    ...config.value,
    variables: config.value.variables.filter(item => variableKey(item) !== key),
  }

  try {
    await persistConfig()
  } catch (error) {
    notice.value = apiError(error, 'Variable removed, but could not be saved to the project.')
    noticeType.value = 'error'
  }
}

// Start no longer saves the config, so the timings are saved as they change.
async function saveTimings() {
  if (isLocked.value) return
  if (!(Number(config.value.sample_time) > 0) || !(Number(config.value.request_timeout) > 0)) {
    timingMessage.value = 'Sample time and request timeout must be positive numbers of seconds.'
    timingMessageType.value = 'error'
    return
  }
  try {
    await persistConfig()
    timingMessage.value = 'Saved.'
    timingMessageType.value = 'success'
  } catch (error) {
    timingMessage.value = apiError(error, 'Could not save monitoring config.')
    timingMessageType.value = 'error'
  }
}

async function persistConfig(): Promise<void> {
  const body: MonitoringConfig = {
    sample_time: Number(config.value.sample_time),
    request_timeout: Number(config.value.request_timeout),
    variables: config.value.variables,
  }
  const response = await fetch('/monitoring/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(await responseError(response, 'Could not save monitoring config.'))
  }
  // Deliberately does NOT reassign config.value from the response. The local
  // list is already the source of truth for what THIS request intended to
  // persist — two auto-saves fired close together (e.g. removing two
  // variables back to back) could otherwise let an older response's echoed
  // variables list clobber a newer local edit if it happens to resolve later.
}

onMounted(() => {
  void initialize()
})

onBeforeUnmount(() => {
  stopStatePolling()
})
</script>

<template>
  <section class="config-panel">
    <div class="panel-header">
      <div>
        <h2>Monitoring</h2>
        <p>
          Which device variables the work-server polls, and how often. The Monitoring page plots
          them, the Dashboard's LCDs show them, and recorded runs save them.
        </p>
      </div>
      <span v-if="state.effective_on" class="session-pill running">
        <span class="status-dot" aria-hidden="true"></span>
        Monitoring on
      </span>
    </div>

    <div v-if="isLoading" class="panel-state" aria-live="polite">
      <span class="mini-spinner" aria-hidden="true"></span>
      Loading the monitoring config…
    </div>

    <div v-else-if="loadError" class="notice error" role="alert">
      <span>{{ loadError }}</span>
      <button type="button" class="button compact" @click="initialize">Try again</button>
    </div>

    <div v-else-if="projectLoaded === false" class="panel-state">
      Open a project to choose what to monitor.
    </div>

    <template v-else>
      <div v-if="isLocked" class="notice warning">
        <span v-if="state.run_active">
          A protocol run is polling these variables. They can be changed once it ends.
        </span>
        <span v-else>
          Monitoring is on, so these settings are locked.
          <RouterLink to="/monitoring">Stop it on the Monitoring page</RouterLink>
          to change them.
        </span>
      </div>
      <div v-if="notice" class="notice" :class="noticeType">
        {{ notice }}
      </div>

      <div class="config-grid">
        <label class="field">
          <span>Sample time (s)</span>
          <input
            v-model.number="config.sample_time"
            type="number"
            min="0.1"
            step="0.1"
            :disabled="isLocked"
            @change="saveTimings"
          >
        </label>
        <label class="field">
          <span>Request timeout (s)</span>
          <input
            v-model.number="config.request_timeout"
            type="number"
            min="0.1"
            step="0.1"
            :disabled="isLocked"
            @change="saveTimings"
          >
        </label>
      </div>
      <p v-if="timingMessage" class="timing-message" :class="timingMessageType" role="status">
        {{ timingMessage }}
      </p>

      <div class="selector-grid">
        <label class="field">
          <span>Component</span>
          <select v-model="selectedComponent" :disabled="isLocked" @change="discoverCommands">
            <option value="">Select component</option>
            <optgroup label="Devices">
              <option
                v-for="assoc in configuredAssociations"
                :key="assoc.component"
                :value="assoc.component"
              >
                {{ assoc.component }}
              </option>
            </optgroup>
            <optgroup label="Custom sources">
              <option :value="CUSTOM_COMPONENT">{{ CUSTOM_COMPONENT }}</option>
            </optgroup>
          </select>
        </label>
        <label class="field">
          <span>{{ selectedComponent === CUSTOM_COMPONENT ? 'Custom source' : 'GET variable' }}</span>
          <select
            v-model="selectedCommand"
            :disabled="isLocked || isDiscovering || discoveredCommands.length === 0"
            @change="resetCommandInputs"
          >
            <option value="">{{ isDiscovering ? 'Discovering...' : 'Select variable' }}</option>
            <option
              v-for="command in discoveredCommands"
              :key="command.command"
              :value="command.command"
            >
              {{ command.command }}
            </option>
          </select>
        </label>
      </div>

      <div v-if="discoveryMessage" class="inline-message" :class="discoveryMessageType">
        {{ discoveryMessage }}
      </div>

      <div v-if="selectedCommand" class="kwargs-panel">
        <template v-if="parameterFields.length">
          <label
            v-for="field in parameterFields"
            :key="field.name"
            class="field"
          >
            <span>{{ field.name }}{{ field.required ? ' *' : '' }}</span>
            <input
              v-model="paramValues[field.name]"
              type="text"
              :placeholder="field.description || field.type"
              :disabled="isLocked"
            >
          </label>
        </template>
        <label v-else class="field">
          <span>Kwargs JSON</span>
          <textarea
            v-model="rawKwargsJson"
            rows="4"
            spellcheck="false"
            :disabled="isLocked"
          ></textarea>
        </label>
      </div>

      <div v-if="addVariableError" class="inline-message error">
        {{ addVariableError }}
      </div>

      <button
        type="button"
        class="button"
        :disabled="!canAddVariable"
        @click="addVariable"
      >
        Add Variable
      </button>

      <div class="selected-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Command</th>
              <th>Kwargs</th>
              <th><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="variable in config.variables" :key="variableKey(variable)">
              <td>{{ variable.component }}</td>
              <td><code>{{ variable.command }}</code></td>
              <td><code>{{ formatJson(variable.kwargs) }}</code></td>
              <td class="actions-cell">
                <button
                  type="button"
                  class="button compact"
                  :disabled="isLocked"
                  @click="removeVariable(variable)"
                >
                  Remove
                </button>
              </td>
            </tr>
            <tr v-if="config.variables.length === 0">
              <td colspan="4" class="empty-row">No variables selected.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="panel-footnote">
        To keep a run's readings, turn on <strong>Record monitoring data</strong> under
        <RouterLink to="/configurations#run-control">Run control</RouterLink>.
      </p>
    </template>
  </section>
</template>

<style scoped>
.config-panel {
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.2rem 1.3rem;
  border-bottom: 1px solid var(--color-border);
}

.panel-header h2 {
  margin: 0;
  color: var(--color-heading);
  font-size: 1.05rem;
  font-weight: 720;
}

.panel-header p {
  max-width: 640px;
  margin: 0.32rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.82rem;
}

.panel-state {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 1.5rem 1.3rem;
  color: var(--color-text-muted);
  font-size: 0.86rem;
}

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

.button:hover:not(:disabled) {
  border-color: var(--color-border-hover);
  background: var(--color-background-mute);
}

.button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
  box-shadow: none;
}

.button.compact {
  min-height: 32px;
  padding: 0.4rem 0.65rem;
  font-size: 0.74rem;
}

.config-panel > .button {
  margin: 1rem 1.3rem;
}

.config-grid,
.selector-grid,
.kwargs-panel {
  display: grid;
  gap: 0.8rem;
  padding: 1rem 1.3rem 0;
}

.config-grid,
.selector-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.field {
  display: grid;
  gap: 0.35rem;
}

.field span {
  color: var(--color-text-muted);
  font-size: 0.72rem;
  font-weight: 760;
  text-transform: uppercase;
}

.field input,
.field select,
.field textarea {
  width: 100%;
  min-height: 38px;
  padding: 0.55rem 0.65rem;
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background);
  font: inherit;
  font-size: 0.84rem;
}

.field textarea {
  resize: vertical;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}

.field input:disabled,
.field select:disabled,
.field textarea:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.timing-message {
  margin: 0.5rem 1.3rem 0;
  color: var(--color-text-muted);
  font-size: 0.78rem;
}

.timing-message.success {
  color: var(--color-success);
}

.timing-message.error {
  color: var(--color-danger);
}

.notice,
.inline-message {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin: 1rem 1.3rem 0;
  padding: 0.72rem 0.85rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  background: var(--color-background-mute);
  font-size: 0.82rem;
}

.notice a {
  font-weight: 680;
  text-decoration: underline;
}

.notice.error,
.inline-message.error {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 22%, var(--color-border));
  background: var(--color-danger-soft);
}

.notice.warning,
.inline-message.warning {
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 24%, var(--color-border));
  background: var(--color-warning-soft);
}

.notice.success {
  color: var(--color-success);
  border-color: color-mix(in srgb, var(--color-success) 22%, var(--color-border));
  background: var(--color-success-soft);
}

.selected-table-wrap {
  width: 100%;
  overflow-x: auto;
  border-top: 1px solid var(--color-border);
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 0.75rem 0.85rem;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}

th {
  color: var(--color-text-muted);
  background: var(--color-background-mute);
  font-size: 0.66rem;
  font-weight: 780;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

tbody tr:last-child td {
  border-bottom: 0;
}

code {
  padding: 0.12rem 0.3rem;
  color: var(--color-heading);
  border-radius: 5px;
  background: var(--color-background-mute);
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 0.8em;
}

.actions-cell {
  width: 1%;
  text-align: right;
  white-space: nowrap;
}

.empty-row {
  padding: 1.5rem;
  color: var(--color-text-muted);
  text-align: center;
}

.panel-footnote {
  margin: 0;
  padding: 0.85rem 1.3rem;
  color: var(--color-text-muted);
  border-top: 1px solid var(--color-border);
  font-size: 0.8rem;
}

.panel-footnote a {
  color: var(--color-primary);
  font-weight: 650;
}

.panel-footnote a:hover {
  text-decoration: underline;
}

.session-pill {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.42rem;
  padding: 0.32rem 0.58rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 760;
}

.session-pill.running {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.mini-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 800ms linear infinite;
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
  .panel-header {
    padding: 1rem;
  }

  .config-grid,
  .selector-grid {
    grid-template-columns: 1fr;
  }

  .config-grid,
  .selector-grid,
  .kwargs-panel {
    padding-right: 1rem;
    padding-left: 1rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .mini-spinner {
    animation: none;
  }
}
</style>
