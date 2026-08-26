<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

interface ProjectResponse {
  project_dir: string | null
}

interface LogMeta {
  filename: string
  modified: string
  size_bytes: number
}

interface LogContentResponse {
  content: string
}

interface ActiveRunResponse {
  active_run_id: string | null
}

interface ErrorResponse {
  detail?: string
}

const route = useRoute()
const projectLoaded = ref<boolean | null>(null)
const logFiles = ref<LogMeta[]>([])
const selectedLog = ref<string | null>(null)
const logContent = ref('Click a log file to view its contents.')
const pageError = ref('')
const contentError = ref('')
const isLoadingPage = ref(true)
const isLoadingContent = ref(false)
const activeRunId = ref<string | null>(null)

let refreshTimer: ReturnType<typeof window.setInterval> | undefined
let contentRequestId = 0
let contentRequestController: AbortController | undefined

const isAutoRefreshing = computed(
  () => Boolean(activeRunId.value && selectedLog.value),
)

function apiError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

async function responseError(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json() as ErrorResponse
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail
  } catch {
    // Use the friendly fallback when the response is not JSON.
  }
  return fallback
}

function stopAutoRefresh() {
  if (refreshTimer !== undefined) {
    window.clearInterval(refreshTimer)
    refreshTimer = undefined
  }
}

function syncAutoRefresh() {
  stopAutoRefresh()
  if (!isAutoRefreshing.value) return

  refreshTimer = window.setInterval(() => {
    if (selectedLog.value && !isLoadingContent.value) {
      void loadLog(selectedLog.value, true)
    }
  }, 5000)
}

async function loadLog(filename: string, isRefresh = false) {
  const requestId = ++contentRequestId
  contentRequestController?.abort()
  contentRequestController = new AbortController()

  if (!isRefresh) {
    selectedLog.value = filename
    logContent.value = ''
    syncAutoRefresh()
  }

  contentError.value = ''
  isLoadingContent.value = true

  try {
    const response = await fetch(
      `/logs/${encodeURIComponent(filename)}?tail=200`,
      { signal: contentRequestController.signal },
    )
    if (!response.ok) {
      throw new Error(await responseError(response, `Could not load ${filename}.`))
    }

    const body = await response.json() as LogContentResponse
    if (requestId === contentRequestId && selectedLog.value === filename) {
      logContent.value = body.content
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    if (requestId === contentRequestId && selectedLog.value === filename) {
      contentError.value = apiError(error, `Could not load ${filename}.`)
    }
  } finally {
    if (requestId === contentRequestId) {
      isLoadingContent.value = false
    }
  }
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

    const [logsResponse, activeRunResponse] = await Promise.all([
      fetch('/logs/'),
      fetch('/run/active'),
    ])
    if (!logsResponse.ok) {
      throw new Error(await responseError(logsResponse, 'Could not load log files.'))
    }

    logFiles.value = await logsResponse.json() as LogMeta[]
    if (activeRunResponse.ok) {
      const activeRun = await activeRunResponse.json() as ActiveRunResponse
      activeRunId.value = activeRun.active_run_id
    } else {
      // Older running servers may not expose this optional endpoint yet.
      // Log browsing remains available; only active-run auto-refresh is disabled.
      activeRunId.value = null
    }

    const queryFile = Array.isArray(route.query.file)
      ? route.query.file[0]
      : route.query.file
    if (queryFile) {
      await loadLog(queryFile)
    }
  } catch (error) {
    pageError.value = apiError(error, 'Could not load logs.')
  } finally {
    isLoadingPage.value = false
  }
}

onMounted(() => {
  void initialize()
})

onBeforeUnmount(() => {
  stopAutoRefresh()
  contentRequestController?.abort()
})
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Operational traces</p>
        <h1 class="page-title">Logs</h1>
        <p class="page-description">
          Browse execution logs and tail the selected file while a run is active.
        </p>
      </div>
    </header>

    <section v-if="isLoadingPage" class="state-card" aria-live="polite">
      <span class="spinner" aria-hidden="true"></span>
      <h2>Loading logs</h2>
      <p>Checking the current project and available log files.</p>
    </section>

    <section v-else-if="pageError" class="state-card error-state" role="alert">
      <h2>Logs unavailable</h2>
      <p>{{ pageError }}</p>
      <button type="button" class="retry-button" @click="initialize">Try again</button>
    </section>

    <section v-else-if="projectLoaded === false" class="state-card">
      <h2>No project loaded</h2>
      <p>
        Load a project to inspect logs.
        <RouterLink to="/">Return to Dashboard</RouterLink>.
      </p>
    </section>

    <div v-else class="logs-grid">
      <section class="panel log-files-panel">
        <div class="panel-header">
          <div>
            <h2>Log Files</h2>
            <p>Choose a file to load the latest content.</p>
          </div>
        </div>

        <ul v-if="logFiles.length" class="log-list">
          <li v-for="log in logFiles" :key="log.filename">
            <button
              type="button"
              :class="{ selected: selectedLog === log.filename }"
              :aria-current="selectedLog === log.filename ? 'true' : undefined"
              @click="loadLog(log.filename)"
            >
              <span>{{ log.filename }}</span>
              <small>{{ log.modified }}</small>
            </button>
          </li>
        </ul>
        <p v-else class="muted">No log files.</p>
      </section>

      <section class="panel log-content-panel">
        <div class="panel-header">
          <div>
            <h2>Log Content</h2>
            <p v-if="selectedLog" class="selected-file">
              <code>{{ selectedLog }}</code>
              <span v-if="isAutoRefreshing" class="running-badge">Auto-refreshing</span>
            </p>
            <p v-else>Select a log file from the list.</p>
          </div>
        </div>

        <div class="content-frame">
          <div v-if="isLoadingContent && !logContent" class="content-message">
            Loading log content…
          </div>
          <div v-else-if="contentError" class="content-message content-error" role="alert">
            <p>{{ contentError }}</p>
            <button
              v-if="selectedLog"
              type="button"
              class="retry-button"
              @click="loadLog(selectedLog)"
            >
              Try again
            </button>
          </div>
          <pre v-else id="log-content">{{ logContent }}</pre>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.logs-grid {
  display: grid;
  grid-template-columns: minmax(250px, 0.34fr) minmax(0, 1fr);
  gap: 1rem;
  align-items: stretch;
}

.panel,
.state-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
}

.panel {
  min-width: 0;
  overflow: hidden;
}

.panel-header {
  min-height: 94px;
  display: flex;
  align-items: center;
  padding: 1.15rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
}

.panel-header h2,
.state-card h2 {
  margin-bottom: 0.25rem;
  color: var(--color-heading);
  font-size: 1rem;
  font-weight: 700;
}

.panel-header p,
.state-card p {
  margin-bottom: 0;
  color: var(--color-text-muted);
  font-size: 0.84rem;
}

.log-list {
  max-height: min(65vh, 720px);
  margin: 0;
  padding: 0.65rem;
  overflow-y: auto;
  list-style: none;
}

.log-list li + li {
  margin-top: 0.25rem;
}

.log-list button {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.72rem 0.75rem;
  color: var(--color-text);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background-color 150ms ease, border-color 150ms ease;
}

.log-list button:hover {
  border-color: var(--color-border);
  background: var(--color-background-mute);
}

.log-list button.selected {
  color: var(--color-primary);
  border-color: color-mix(in srgb, var(--color-primary) 25%, var(--color-border));
  background: var(--color-primary-soft);
}

.log-list button span {
  max-width: 100%;
  overflow: hidden;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-list small {
  color: var(--color-text-muted);
  font-size: 0.72rem;
}

.muted {
  margin: 0;
  padding: 1.25rem;
  color: var(--color-text-muted);
}

.selected-file {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.selected-file code {
  color: var(--color-text);
}

.running-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.18rem 0.48rem;
  color: var(--color-success);
  border: 1px solid color-mix(in srgb, var(--color-success) 26%, transparent);
  border-radius: 999px;
  background: var(--color-success-soft);
  font-size: 0.7rem;
  font-weight: 700;
}

.running-badge::before {
  width: 0.42rem;
  height: 0.42rem;
  content: '';
  border-radius: 50%;
  background: currentColor;
}

.content-frame {
  min-height: 420px;
  height: min(65vh, 720px);
  background: color-mix(in srgb, var(--color-sidebar) 96%, black);
}

#log-content {
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 1.1rem 1.2rem;
  overflow: auto;
  color: #d7e5ef;
  background: transparent;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.78rem;
  line-height: 1.65;
  tab-size: 2;
  white-space: pre;
}

.content-message {
  height: 100%;
  display: grid;
  place-content: center;
  padding: 2rem;
  color: #9fb4c5;
  text-align: center;
}

.content-message p {
  margin-bottom: 0.8rem;
}

.content-error {
  color: #ffb0b8;
}

.state-card {
  min-height: 280px;
  display: grid;
  place-content: center;
  justify-items: center;
  padding: 2rem;
  text-align: center;
}

.state-card a {
  color: var(--color-primary);
  font-weight: 650;
}

.state-card a:hover {
  text-decoration: underline;
}

.error-state {
  border-color: color-mix(in srgb, var(--color-danger) 25%, var(--color-border));
  background: var(--color-danger-soft);
}

.retry-button {
  margin-top: 1rem;
  padding: 0.55rem 0.85rem;
  color: #fff;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  cursor: pointer;
  font-weight: 650;
}

.retry-button:hover {
  background: var(--color-primary-hover);
}

.spinner {
  width: 24px;
  height: 24px;
  margin-bottom: 0.85rem;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 700ms linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 820px) {
  .logs-grid {
    grid-template-columns: 1fr;
  }

  .log-list {
    max-height: 280px;
  }

  .content-frame {
    height: 55vh;
    min-height: 340px;
  }
}

@media (max-width: 640px) {
  .panel-header {
    min-height: auto;
    padding: 1rem;
  }

  .content-frame {
    height: 52vh;
    min-height: 300px;
  }

  #log-content {
    padding: 0.9rem;
    font-size: 0.72rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}
</style>
