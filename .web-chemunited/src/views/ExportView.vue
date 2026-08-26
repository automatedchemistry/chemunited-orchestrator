<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useNotification } from '../composables/useNotification'

interface ProjectResponse {
  project_dir: string | null
}

interface ExportEntry {
  filename: string
  size_bytes: number
  modified: string
}

interface ExportMonitoringGroup {
  run_id: string
  files: ExportEntry[]
  total_size_bytes: number
}

interface ExportRow {
  log: ExportEntry
  monitoring: ExportMonitoringGroup | null
  protocol: ExportEntry | null
}

interface ExportCleanResult {
  deleted: string[]
  count: number
}

interface ErrorResponse {
  detail?: string
}

const { notify } = useNotification()

const projectLoaded = ref<boolean | null>(null)
const rows = ref<ExportRow[]>([])
const selected = ref<Set<string>>(new Set())
const pageError = ref('')
const isLoadingPage = ref(true)
const isCleaning = ref(false)

const selectedCount = computed(() => selected.value.size)
const allSelected = computed(
  () => rows.value.length > 0 && selected.value.size === rows.value.length,
)
const someSelected = computed(
  () => selected.value.size > 0 && !allSelected.value,
)
const downloadHref = computed(() => {
  if (selected.value.size === 0) return null
  const params = [...selected.value]
    .map(filename => `log=${encodeURIComponent(filename)}`)
    .join('&')
  return `/export/download?${params}`
})

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  )
  const value = bytes / 1024 ** exponent
  return `${exponent === 0 ? value : value.toFixed(1)} ${units[exponent]}`
}

function isSelected(filename: string): boolean {
  return selected.value.has(filename)
}

function toggleRow(filename: string) {
  const next = new Set(selected.value)
  if (next.has(filename)) next.delete(filename)
  else next.add(filename)
  selected.value = next
}

function toggleAll() {
  selected.value = allSelected.value
    ? new Set()
    : new Set(rows.value.map(r => r.log.filename))
}

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

async function loadPreview() {
  const response = await fetch('/export/preview')
  if (!response.ok) {
    throw new Error(await responseError(response, 'Could not load export preview.'))
  }
  rows.value = await response.json() as ExportRow[]
  const known = new Set(rows.value.map(r => r.log.filename))
  selected.value = new Set([...selected.value].filter(f => known.has(f)))
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

    await loadPreview()
  } catch (error) {
    pageError.value = apiError(error, 'Could not load the export page.')
  } finally {
    isLoadingPage.value = false
  }
}

async function handleClean() {
  if (isCleaning.value || selected.value.size === 0) return
  const count = selected.value.size
  if (!window.confirm(
    `Permanently delete the log and monitoring recording for ${count} selected `
    + `run${count === 1 ? '' : 's'}? This cannot be undone. Protocol history is never deleted.`,
  )) return

  isCleaning.value = true
  try {
    const response = await fetch('/export/clean', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ logs: [...selected.value] }),
    })
    if (!response.ok) {
      notify(await responseError(response, 'Could not clean the selected runs.'), 'error')
      return
    }
    const body = await response.json() as ExportCleanResult
    notify(
      body.count
        ? `Deleted ${body.count} file${body.count === 1 ? '' : 's'}.`
        : 'Nothing to clean.',
      'success',
    )
    await loadPreview()
  } catch (error) {
    notify(apiError(error, 'Could not clean the selected runs.'), 'error')
  } finally {
    isCleaning.value = false
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
        <p class="page-eyebrow">Housekeeping</p>
        <h1 class="page-title">Export</h1>
        <p class="page-description">
          One row per executed run — its log, correlated monitoring recording (if any),
          and source protocol. Select the runs you want, then download a zip or
          permanently clean them out of the project.
        </p>
      </div>
    </header>

    <section v-if="isLoadingPage" class="state-card" aria-live="polite">
      <span class="spinner" aria-hidden="true"></span>
      <h2>Loading export preview</h2>
      <p>Checking the current project and its executed runs.</p>
    </section>

    <section v-else-if="pageError" class="state-card error-state" role="alert">
      <h2>Export unavailable</h2>
      <p>{{ pageError }}</p>
      <button type="button" class="retry-button" @click="initialize">Try again</button>
    </section>

    <section v-else-if="projectLoaded === false" class="state-card">
      <h2>No project loaded</h2>
      <p>
        Load a project to export its files.
        <RouterLink to="/">Return to Dashboard</RouterLink>.
      </p>
    </section>

    <div v-else class="export-content">
      <div class="actions-bar">
        <a
          class="action-button primary"
          :class="{ disabled: !downloadHref }"
          :href="downloadHref ?? undefined"
          :aria-disabled="!downloadHref"
          @click="!downloadHref && $event.preventDefault()"
        >
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 3v12m0 0-4-4m4 4 4-4"/>
            <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>
          </svg>
          <span>Download selected ({{ selectedCount }})</span>
        </a>
        <button
          type="button"
          class="action-button danger"
          :disabled="isCleaning || selectedCount === 0"
          @click="handleClean"
        >
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 7h16M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2m-8 0 1 13a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2l1-13"/>
          </svg>
          <span>{{ isCleaning ? 'Cleaning…' : `Clean selected (${selectedCount})` }}</span>
        </button>
        <p class="actions-note">
          Download never deletes anything. Clean permanently removes the selected runs'
          logs and monitoring recordings; protocol history is always kept.
        </p>
      </div>

      <section class="panel">
        <div v-if="rows.length === 0" class="muted">No executed runs yet.</div>
        <div v-else class="table-scroll">
          <table class="runs-table">
            <thead>
              <tr>
                <th class="checkbox-cell">
                  <input
                    type="checkbox"
                    aria-label="Select all runs"
                    :checked="allSelected"
                    :indeterminate="someSelected"
                    @change="toggleAll"
                  >
                </th>
                <th>Log</th>
                <th>Monitoring</th>
                <th>Protocol</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.log.filename" :class="{ selected: isSelected(row.log.filename) }">
                <td class="checkbox-cell">
                  <input
                    type="checkbox"
                    :aria-label="`Select ${row.log.filename}`"
                    :checked="isSelected(row.log.filename)"
                    @change="toggleRow(row.log.filename)"
                  >
                </td>
                <td>
                  <span class="cell-primary">{{ row.log.filename }}</span>
                  <small>{{ formatBytes(row.log.size_bytes) }} &middot; {{ row.log.modified }}</small>
                </td>
                <td>
                  <template v-if="row.monitoring">
                    <span class="cell-primary">{{ row.monitoring.files.length }} file{{ row.monitoring.files.length === 1 ? '' : 's' }}</span>
                    <small>{{ formatBytes(row.monitoring.total_size_bytes) }}</small>
                  </template>
                  <span v-else class="muted-inline">&mdash;</span>
                </td>
                <td>
                  <template v-if="row.protocol">
                    <span class="cell-primary">{{ row.protocol.filename }}</span>
                    <small>{{ formatBytes(row.protocol.size_bytes) }}</small>
                  </template>
                  <span v-else class="muted-inline">&mdash;</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.export-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.actions-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  padding: 1.1rem 1.25rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
}

.action-button {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.65rem 1rem;
  color: #fff;
  border: 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-weight: 650;
  font-size: 0.88rem;
  text-decoration: none;
}

.action-button svg {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.action-button.primary {
  background: var(--color-primary);
}

.action-button.primary:hover {
  background: var(--color-primary-hover);
}

.action-button.danger {
  background: var(--color-danger);
}

.action-button.danger:hover:not(:disabled) {
  filter: brightness(1.08);
}

.action-button:disabled,
.action-button.disabled {
  cursor: not-allowed;
  opacity: 0.55;
  pointer-events: none;
}

.actions-note {
  flex: 1 1 240px;
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8rem;
}

.panel {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
}

.table-scroll {
  overflow-x: auto;
}

.runs-table {
  width: 100%;
  border-collapse: collapse;
}

.runs-table th,
.runs-table td {
  padding: 0.75rem 1rem;
  text-align: left;
  vertical-align: top;
  white-space: nowrap;
}

.runs-table thead th {
  color: var(--color-text-muted);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--color-border);
}

.runs-table tbody tr + tr td {
  border-top: 1px solid var(--color-border);
}

.runs-table tbody tr.selected {
  background: var(--color-primary-soft);
}

.checkbox-cell {
  width: 2.5rem;
}

.checkbox-cell input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.cell-primary {
  display: block;
  color: var(--color-text);
  font-size: 0.85rem;
  font-weight: 600;
}

.runs-table td small {
  display: block;
  margin-top: 0.15rem;
  color: var(--color-text-muted);
  font-size: 0.72rem;
}

.muted-inline {
  color: var(--color-text-muted);
}

.muted {
  margin: 0;
  padding: 1.25rem;
  color: var(--color-text-muted);
}

.state-card {
  min-height: 280px;
  display: grid;
  place-content: center;
  justify-items: center;
  padding: 2rem;
  text-align: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
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

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}
</style>
