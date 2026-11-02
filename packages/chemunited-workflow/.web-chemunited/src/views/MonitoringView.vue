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
  variableParams,
} from '../components/monitoring/monitoringConfig'

interface ProjectResponse {
  project_dir: string | null
}

interface ErrorResponse {
  detail?: string | Array<{ msg?: string }>
}

interface MonitoringReading {
  tick: number
  time: string
  value: unknown
  error: string | null
}

type DisplayMode = 'unknown' | 'numeric' | 'table'
type NoticeType = 'info' | 'error' | 'warning' | 'success'

// Server-authoritative cap on the in-memory history buffer (see HISTORY_MAXLEN
// in monitoring_store.py) — kept here only as a defensive client-side trim,
// not load-bearing.
const MAX_PROFILE_POINTS = 300
const CHART_WIDTH = 520
const CHART_HEIGHT = 160
const CHART_PADDING = 18

const projectLoaded = ref<boolean | null>(null)
const config = ref<MonitoringConfig>({ ...DEFAULT_CONFIG, variables: [] })
const state = ref<MonitoringState>({ ...DEFAULT_STATE })

const isLoadingPage = ref(true)
const pageError = ref('')
const pageNotice = ref('')
const pageNoticeType = ref<NoticeType>('info')
const startError = ref('')

const isStarting = ref(false)
const isStopping = ref(false)
const isPollingLatest = ref(false)
const pollError = ref('')

const latestReadings = ref<Record<string, MonitoringReading>>({})
const profiles = ref<Record<string, MonitoringReading[]>>({})
const displayModes = ref<Record<string, DisplayMode>>({})

let pollTimer: ReturnType<typeof window.setInterval> | undefined
let statePollTimer: ReturnType<typeof window.setInterval> | undefined

const isRunning = computed(() => state.value.effective_on)
// Start and Stop also switch the dashboard's platform view live, so they
// work during a run (only the manual flag changes) and with no variables.
// The variables themselves are chosen under Configurations → Monitoring.
const canStart = computed(() =>
  projectLoaded.value === true
  && !isLoadingPage.value
  && !pageError.value
  && !state.value.manual_on
  && !isStarting.value
)
const startTitle = computed(() => {
  if (isLoadingPage.value || pageError.value) {
    return 'Available once the monitoring config has loaded.'
  }
  if (state.value.run_active) {
    return 'Keeps monitoring on after the run, and makes the platform view live.'
  }
  if (config.value.variables.length === 0) {
    return 'Nothing to read yet; the platform view still goes live.'
  }
  return 'Starts polling, and makes the platform view live.'
})

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

function setNotice(message: string, type: NoticeType = 'info') {
  pageNotice.value = message
  pageNoticeType.value = type
}

function clearNotice() {
  pageNotice.value = ''
}

function historyUrl(variable: MonitoringVariable): string {
  const component = encodeURIComponent(variable.component)
  const command = variable.command
    .replace(/^\/+/, '')
    .split('/')
    .filter(Boolean)
    .map(part => encodeURIComponent(part))
    .join('/')
  const params = variableParams(variable)
  const query = params ? `?kwargs=${encodeURIComponent(params)}` : ''
  return `/monitoring/history/${component}/${command}${query}`
}

function isFlatObject(value: unknown): value is Record<string, unknown> {
  if (!isPlainRecord(value)) return false
  return Object.values(value).every(item => item === null || typeof item !== 'object')
}

function isComplexValue(value: unknown): boolean {
  return Boolean(value) && typeof value === 'object'
}

function isNumericValue(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function formatPrimitive(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function formatTime(value: string | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString()
}

function objectEntries(value: unknown): Array<[string, string]> {
  if (!isFlatObject(value)) return []
  return Object.entries(value).map(([key, item]) => [key, formatPrimitive(item)])
}

async function loadMonitoringConfig() {
  const response = await fetch('/monitoring/config')
  if (!response.ok) {
    throw new Error(await responseError(response, 'Could not load monitoring config.'))
  }
  config.value = normalizeConfig(await response.json() as Partial<MonitoringConfig>)
}

async function initialize() {
  isLoadingPage.value = true
  pageError.value = ''
  clearNotice()

  try {
    const projectResponse = await fetch('/project/')
    if (!projectResponse.ok) {
      throw new Error(await responseError(projectResponse, 'Could not check the current project.'))
    }

    const project = await projectResponse.json() as ProjectResponse
    projectLoaded.value = Boolean(project.project_dir)
    if (!projectLoaded.value) return

    const [configResponse, stateResponse] = await Promise.all([
      fetch('/monitoring/config'),
      fetch('/monitoring/state'),
    ])

    if (!configResponse.ok) {
      throw new Error(await responseError(configResponse, 'Could not load monitoring config.'))
    }
    if (!stateResponse.ok) {
      throw new Error(await responseError(stateResponse, 'Could not load monitoring state.'))
    }

    config.value = normalizeConfig(await configResponse.json() as Partial<MonitoringConfig>)
    state.value = await stateResponse.json() as MonitoringState

    if (state.value.effective_on) {
      await afterTurnedOn(
        state.value.run_active ? 'Monitoring is running automatically for the active protocol run.' : '',
        'info',
        false,
      )
    }
    startStatePolling()
  } catch (error) {
    pageError.value = apiError(error, 'Could not load monitoring.')
  } finally {
    isLoadingPage.value = false
  }
}

// The variable list and timings are saved under Configurations → Monitoring,
// so Start only turns monitoring on.
async function startMonitoring() {
  if (!canStart.value) return

  isStarting.value = true
  startError.value = ''
  pollError.value = ''
  clearNotice()

  try {
    const response = await fetch('/monitoring/start', { method: 'POST' })
    if (!response.ok) {
      throw new Error(await responseError(response, 'Could not start monitoring.'))
    }
    state.value = await response.json() as MonitoringState
    await afterTurnedOn('Monitoring started.', 'success')
  } catch (error) {
    startError.value = apiError(error, 'Could not start monitoring.')
  } finally {
    isStarting.value = false
  }
}

async function stopMonitoring() {
  if (!state.value.manual_on || isStopping.value) return

  isStopping.value = true
  startError.value = ''
  pollError.value = ''

  try {
    const response = await fetch('/monitoring/stop', { method: 'POST' })
    if (!response.ok) {
      throw new Error(await responseError(response, 'Could not stop monitoring.'))
    }
    state.value = await response.json() as MonitoringState
    if (state.value.effective_on) {
      setNotice(
        'The platform view is no longer live. Monitoring goes on for the active run and stops when it ends.',
        'info',
      )
    } else {
      clearPolling()
      setNotice('Monitoring stopped.', 'success')
    }
  } catch (error) {
    pollError.value = apiError(error, 'Could not stop monitoring.')
  } finally {
    isStopping.value = false
  }
}

// The list may have changed since the page loaded (under Configurations, or
// in another browser), so the panels follow the saved one unless it was just
// read.
async function afterTurnedOn(notice = '', type: NoticeType = 'info', reloadConfig = true) {
  pollError.value = ''
  startError.value = ''
  if (notice) setNotice(notice, type)
  if (reloadConfig) {
    try {
      await loadMonitoringConfig()
    } catch (error) {
      pollError.value = apiError(error, 'Could not load monitoring config.')
    }
  }
  await seedHistory(config.value.variables)
  startPolling()
  await pollLatest()
}

async function seedHistory(variables: MonitoringVariable[]) {
  if (variables.length === 0) return
  await Promise.all(variables.map(variable => fetchHistory(variable)))
}

async function fetchHistory(variable: MonitoringVariable) {
  const key = variableKey(variable)
  try {
    const response = await fetch(historyUrl(variable))
    if (!response.ok) {
      throw new Error(await responseError(response, `Could not load history for ${key}.`))
    }
    const readings = await response.json() as MonitoringReading[]
    profiles.value = {
      ...profiles.value,
      [key]: readings.slice(-MAX_PROFILE_POINTS),
    }
    const last = readings[readings.length - 1]
    if (last) {
      latestReadings.value = { ...latestReadings.value, [key]: last }
    }
    pinDisplayModeFromReadings(key, readings)
  } catch (error) {
    pollError.value = apiError(error, `Could not load history for ${key}.`)
  }
}

function startPolling() {
  clearPolling()
  const interval = Math.max(Number(config.value.sample_time) || DEFAULT_CONFIG.sample_time, 1) * 1000
  pollTimer = window.setInterval(() => {
    void pollLatest()
  }, interval)
}

function clearPolling() {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function pollLatest() {
  if (!isRunning.value || isPollingLatest.value) return

  isPollingLatest.value = true
  try {
    const response = await fetch('/monitoring/latest')
    if (!response.ok) {
      throw new Error(await responseError(response, 'Could not load latest monitoring readings.'))
    }
    const latest = await response.json() as Record<string, MonitoringReading>
    latestReadings.value = { ...latestReadings.value, ...latest }
    for (const [key, reading] of Object.entries(latest)) {
      appendReading(key, reading)
      pinDisplayModeFromReading(key, reading)
    }
    pollError.value = ''
  } catch (error) {
    pollError.value = apiError(error, 'Could not refresh monitoring readings.')
  } finally {
    isPollingLatest.value = false
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
    if (!response.ok) return
    const next = await response.json() as MonitoringState
    const wasOn = state.value.effective_on
    state.value = next
    if (!wasOn && next.effective_on) {
      await afterTurnedOn(
        next.run_active ? 'Monitoring is running automatically for the active protocol run.' : 'Monitoring is on.',
        'info',
      )
    } else if (wasOn && !next.effective_on) {
      clearPolling()
      setNotice('Monitoring stopped.', 'info')
    }
  } catch {
    // Leave state unchanged on a transient network error — the next poll retries.
  }
}

function appendReading(key: string, reading: MonitoringReading) {
  const existing = profiles.value[key] ?? []
  const last = existing[existing.length - 1]
  if (last && last.tick === reading.tick && last.time === reading.time) return
  profiles.value = {
    ...profiles.value,
    [key]: [...existing, reading].slice(-MAX_PROFILE_POINTS),
  }
}

function pinDisplayModeFromReadings(key: string, readings: MonitoringReading[]) {
  if (displayModes.value[key] && displayModes.value[key] !== 'unknown') return
  for (const reading of readings) {
    if (pinDisplayModeFromReading(key, reading)) return
  }
}

function pinDisplayModeFromReading(key: string, reading: MonitoringReading): boolean {
  if (displayModes.value[key] && displayModes.value[key] !== 'unknown') return true
  if (reading.error || reading.value === null || reading.value === undefined) return false
  displayModes.value = {
    ...displayModes.value,
    [key]: isNumericValue(reading.value) ? 'numeric' : 'table',
  }
  return true
}

function displayMode(variable: MonitoringVariable): DisplayMode {
  return displayModes.value[variableKey(variable)] ?? 'unknown'
}

function variableReadings(variable: MonitoringVariable): MonitoringReading[] {
  return profiles.value[variableKey(variable)] ?? []
}

function latestFor(variable: MonitoringVariable): MonitoringReading | undefined {
  return latestReadings.value[variableKey(variable)]
}

function chartReadings(variable: MonitoringVariable): MonitoringReading[] {
  return variableReadings(variable).filter(reading => !reading.error && isNumericValue(reading.value))
}

function chartPath(variable: MonitoringVariable): string {
  const readings = chartReadings(variable)
  if (readings.length === 0) return ''
  const values = readings.map(reading => reading.value as number)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const usableWidth = CHART_WIDTH - (CHART_PADDING * 2)
  const usableHeight = CHART_HEIGHT - (CHART_PADDING * 2)
  const denom = Math.max(readings.length - 1, 1)

  return readings.map((reading, index) => {
    const value = reading.value as number
    const x = CHART_PADDING + (index / denom) * usableWidth
    const y = CHART_PADDING + ((max - value) / span) * usableHeight
    return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
  }).join(' ')
}

function chartStats(variable: MonitoringVariable): string {
  const readings = chartReadings(variable)
  if (readings.length === 0) return 'No numeric readings yet.'
  const values = readings.map(reading => reading.value as number)
  const min = Math.min(...values)
  const max = Math.max(...values)
  return `${readings.length} points | min ${min} | max ${max}`
}

async function refreshNumericProfiles() {
  if (!isRunning.value) return
  const numericVariables = config.value.variables
    .filter(variable => displayMode(variable) === 'numeric')
  await Promise.all(numericVariables.map(variable => fetchHistory(variable)))
}

function onVisibilityChange() {
  if (document.visibilityState !== 'visible' || !isRunning.value) return
  void refreshNumericProfiles().then(() => pollLatest())
}

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  void initialize()
})

onBeforeUnmount(() => {
  clearPolling()
  stopStatePolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Live instrumentation</p>
        <h1 class="page-title">Monitoring</h1>
        <p class="page-description">Observe live process conditions and equipment state.</p>
      </div>
      <div v-if="projectLoaded" class="header-actions">
        <span v-if="isRunning" class="session-pill running">
          <span class="status-dot" aria-hidden="true"></span>
          Running
        </span>
        <span v-if="state.recording" class="session-pill recording">
          Recording <code>{{ state.run_id }}</code>
        </span>
        <span v-if="state.manual_on" class="session-pill">Platform view live</span>
        <button
          v-if="state.manual_on"
          type="button"
          class="button danger"
          :disabled="isStopping"
          :title="state.run_active ? 'The run keeps monitoring until it ends; the platform view stops being live.' : 'Stops polling; the platform view stops being live.'"
          @click="stopMonitoring"
        >
          <span v-if="isStopping" class="mini-spinner" aria-hidden="true"></span>
          {{ isStopping ? 'Stopping...' : 'Stop' }}
        </button>
        <button
          v-else
          type="button"
          class="button primary"
          :disabled="!canStart"
          :title="startTitle"
          @click="startMonitoring"
        >
          <span v-if="isStarting" class="mini-spinner" aria-hidden="true"></span>
          {{ isStarting ? 'Starting...' : 'Start' }}
        </button>
      </div>
    </header>

    <section v-if="isLoadingPage" class="state-card" aria-live="polite">
      <span class="spinner" aria-hidden="true"></span>
      <h2>Loading monitoring</h2>
      <p>Checking project, config, and state.</p>
    </section>

    <section v-else-if="pageError" class="state-card error-state" role="alert">
      <h2>Monitoring unavailable</h2>
      <p>{{ pageError }}</p>
      <button type="button" class="button" @click="initialize">Try again</button>
    </section>

    <section v-else-if="projectLoaded === false" class="state-card">
      <h2>Open a project to monitor variables</h2>
      <p>The monitoring config is loaded from the active project.</p>
    </section>

    <div v-else class="monitoring-layout">
      <div v-if="pageNotice" class="notice" :class="pageNoticeType">
        {{ pageNotice }}
      </div>
      <div v-if="pollError" class="notice error">
        {{ pollError }}
      </div>
      <div v-if="startError" class="notice error">
        {{ startError }}
      </div>

      <section class="profiles-area">
        <div class="profiles-header">
          <div>
            <h2>Profiles</h2>
            <p>
              {{ config.variables.length }} {{ config.variables.length === 1 ? 'variable' : 'variables' }}
              · every {{ config.sample_time }} s
              <template v-if="state.run_active">· polled for the active run</template>
              · <RouterLink to="/configurations#monitoring" class="inline-link">Change</RouterLink>
            </p>
          </div>
          <span v-if="isPollingLatest" class="refresh-label">
            <span class="mini-spinner" aria-hidden="true"></span>
            Refreshing
          </span>
        </div>

        <div v-if="config.variables.length === 0" class="empty-profiles">
          <h3>No variables selected</h3>
          <p>
            Choose what to monitor under
            <RouterLink to="/configurations#monitoring" class="inline-link">Configurations → Monitoring</RouterLink>.
          </p>
        </div>

        <div v-else class="profile-grid">
          <article
            v-for="variable in config.variables"
            :key="variableKey(variable)"
            class="profile-card"
          >
            <header class="profile-card-header">
              <div>
                <h3>{{ variable.component }}</h3>
                <code>{{ variable.command }}</code>
              </div>
              <span
                class="reading-status"
                :class="latestFor(variable)?.error ? 'error' : displayMode(variable)"
              >
                {{ latestFor(variable)?.error ? 'Error' : displayMode(variable) }}
              </span>
            </header>

            <div class="latest-block">
              <span>Latest</span>
              <strong v-if="latestFor(variable)?.error">{{ latestFor(variable)?.error }}</strong>
              <pre v-else-if="isComplexValue(latestFor(variable)?.value)">{{ formatJson(latestFor(variable)?.value) }}</pre>
              <strong v-else>{{ formatPrimitive(latestFor(variable)?.value) }}</strong>
              <small>{{ formatTime(latestFor(variable)?.time) }}</small>
            </div>

            <div v-if="displayMode(variable) === 'numeric'" class="chart-wrap">
              <svg
                :viewBox="`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`"
                role="img"
                aria-label="Numeric monitoring profile"
              >
                <path class="chart-grid" :d="`M ${CHART_PADDING} ${CHART_PADDING} H ${CHART_WIDTH - CHART_PADDING} M ${CHART_PADDING} ${CHART_HEIGHT / 2} H ${CHART_WIDTH - CHART_PADDING} M ${CHART_PADDING} ${CHART_HEIGHT - CHART_PADDING} H ${CHART_WIDTH - CHART_PADDING}`" />
                <path v-if="chartPath(variable)" class="chart-line" :d="chartPath(variable)" />
              </svg>
              <p>{{ chartStats(variable) }}</p>
            </div>

            <div v-else-if="displayMode(variable) === 'table'" class="history-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Tick</th>
                    <th>Time</th>
                    <th>Value</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="reading in variableReadings(variable)" :key="`${reading.tick}-${reading.time}`">
                    <td>{{ reading.tick }}</td>
                    <td>{{ formatTime(reading.time) }}</td>
                    <td>
                      <dl v-if="isFlatObject(reading.value)" class="kv-list">
                        <template
                          v-for="[entryKey, entryValue] in objectEntries(reading.value)"
                          :key="entryKey"
                        >
                          <dt>{{ entryKey }}</dt>
                          <dd>{{ entryValue }}</dd>
                        </template>
                      </dl>
                      <pre v-else-if="isComplexValue(reading.value)">{{ formatJson(reading.value) }}</pre>
                      <span v-else>{{ formatPrimitive(reading.value) }}</span>
                    </td>
                    <td class="error-cell">{{ reading.error || '-' }}</td>
                  </tr>
                  <tr v-if="variableReadings(variable).length === 0">
                    <td colspan="4" class="empty-row">No readings yet.</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else class="waiting-block">
              Waiting for a valid reading.
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.header-actions {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.7rem;
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

.button.primary {
  color: #ffffff;
  border-color: var(--color-primary);
  background: var(--color-primary);
  box-shadow: 0 6px 16px color-mix(in srgb, var(--color-primary) 20%, transparent);
}

.button.danger {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 28%, var(--color-border));
  background: var(--color-danger-soft);
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

.state-card,
.profiles-area,
.profile-card {
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

.monitoring-layout {
  display: grid;
  gap: 1rem;
}

.profiles-area {
  overflow: hidden;
}

.profiles-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.2rem 1.3rem;
  border-bottom: 1px solid var(--color-border);
}

.profiles-header h2 {
  margin: 0;
  color: var(--color-heading);
  font-size: 1.05rem;
  font-weight: 720;
}

.profiles-header p {
  margin: 0.32rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.82rem;
}

.inline-link {
  color: var(--color-primary);
  font-weight: 650;
}

.inline-link:hover {
  text-decoration: underline;
}

.notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.72rem 0.85rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  background: var(--color-background-mute);
  font-size: 0.82rem;
}

.notice.error {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 22%, var(--color-border));
  background: var(--color-danger-soft);
}

.notice.warning {
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 24%, var(--color-border));
  background: var(--color-warning-soft);
}

.notice.success {
  color: var(--color-success);
  border-color: color-mix(in srgb, var(--color-success) 22%, var(--color-border));
  background: var(--color-success-soft);
}

.history-table-wrap {
  width: 100%;
  overflow-x: auto;
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

code,
pre {
  color: var(--color-heading);
  border-radius: 5px;
  background: var(--color-background-mute);
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}

code {
  padding: 0.12rem 0.3rem;
  font-size: 0.8em;
}

pre {
  max-width: 100%;
  margin: 0;
  padding: 0.5rem;
  overflow-x: auto;
  font-size: 0.74rem;
  white-space: pre-wrap;
}

.empty-row {
  padding: 1.5rem;
  color: var(--color-text-muted);
  text-align: center;
}

.profiles-area {
  min-height: 460px;
}

.refresh-label,
.session-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.42rem;
  width: fit-content;
  padding: 0.32rem 0.58rem;
  border-radius: 999px;
  background: var(--color-background-mute);
  color: var(--color-text-muted);
  font-size: 0.72rem;
  font-weight: 760;
}

.session-pill.running {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.session-pill.warning {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.session-pill.recording {
  color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.empty-profiles {
  min-height: 320px;
  display: grid;
  place-items: center;
  padding: 2rem;
  color: var(--color-text-muted);
  text-align: center;
}

.empty-profiles h3 {
  margin: 0 0 0.35rem;
  color: var(--color-heading);
  font-size: 1rem;
}

.empty-profiles p {
  margin: 0;
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 0.9rem;
  padding: 1rem;
}

.profile-card {
  overflow: hidden;
  box-shadow: none;
}

.profile-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.profile-card-header h3 {
  margin: 0 0 0.35rem;
  color: var(--color-heading);
  font-size: 0.98rem;
}

.reading-status {
  display: inline-flex;
  padding: 0.28rem 0.52rem;
  border-radius: 999px;
  color: var(--color-text-muted);
  background: var(--color-background-mute);
  font-size: 0.68rem;
  font-weight: 780;
  text-transform: capitalize;
}

.reading-status.numeric {
  color: var(--color-primary);
}

.reading-status.table {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.reading-status.error {
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.latest-block {
  display: grid;
  gap: 0.32rem;
  padding: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.latest-block span,
.latest-block small {
  color: var(--color-text-muted);
  font-size: 0.72rem;
}

.latest-block strong {
  color: var(--color-heading);
  font-size: 1.2rem;
  font-weight: 720;
  overflow-wrap: anywhere;
}

.chart-wrap {
  padding: 1rem;
}

.chart-wrap svg {
  width: 100%;
  height: auto;
  display: block;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background);
}

.chart-grid {
  fill: none;
  stroke: color-mix(in srgb, var(--color-border) 78%, transparent);
  stroke-width: 1;
}

.chart-line {
  fill: none;
  stroke: var(--color-primary);
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2.5;
}

.chart-wrap p,
.waiting-block {
  margin: 0.65rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.78rem;
}

.waiting-block {
  padding: 1rem;
}

.history-table-wrap table {
  min-width: 620px;
}

.history-table-wrap td {
  font-size: 0.8rem;
}

.kv-list {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 0.24rem 0.55rem;
  margin: 0;
}

.kv-list dt {
  color: var(--color-text-muted);
  font-weight: 720;
}

.kv-list dd {
  min-width: 0;
  margin: 0;
  color: var(--color-heading);
  overflow-wrap: anywhere;
}

.error-cell {
  color: var(--color-danger);
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

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 640px) {
  .header-actions,
  .header-actions .button {
    width: 100%;
  }

  .profiles-header {
    padding: 1rem;
  }

  .profile-grid {
    grid-template-columns: 1fr;
    padding: 0.75rem;
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
