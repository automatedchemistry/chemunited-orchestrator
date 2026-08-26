<script lang="ts">
interface PlatformDevice {
  id: string
  label: string
  figure?: string | null
  is_electronic?: boolean | null
  x: number
  y: number
  w: number
  h: number
}

// Module-level cache — persists across mount/unmount (no re-fetch on dashboard revisit)
let _platformSvgCache: string | 'missing' | null = null
let _platformDevicesCache: PlatformDevice[] | 'missing' | null = null
</script>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import DevicePropertiesPanel, { clearDeviceCommandsCache } from '../components/DevicePropertiesPanel.vue'

interface ProjectResponse {
  project_dir: string | null
}

interface ProtocolMeta {
  filename: string
  modified: string
  size_bytes: number
}

interface ProcessInfo {
  name: string
  description: string
}

interface ActiveRunResponse {
  active_run_id: string | null
  state: string | null
}

interface RunReport {
  run_id: string
  state: string
}

const isLoading = ref(true)
const pageError = ref('')
const projectLoaded = ref<boolean | null>(null)
const projectDir = ref<string | null>(null)
const protocolCount = ref<number | null>(null)
const latestProtocol = ref<string | null>(null)
const processCount = ref<number | null>(null)
const activeRunId = ref<string | null>(null)
const activeRunState = ref<string | null>(null)
const lastRun = ref<RunReport | null>(null)
const platformSvg = ref<string | null>(null)
const platformDevices = ref<PlatformDevice[]>([])
const selectedDeviceId = ref<string | null>(null)

const selectedDevice = computed(
  () => platformDevices.value.find(device => device.id === selectedDeviceId.value) ?? null,
)

function projectName(dir: string | null): string {
  if (!dir) return '—'
  return dir.replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? dir
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

function runStateClass(state: string): string {
  const s = state.toLowerCase()
  if (s === 'finished' || s === 'success') return 'state-success'
  if (s === 'failed' || s === 'error') return 'state-failed'
  if (s === 'running') return 'state-running'
  if (s === 'paused') return 'state-paused'
  return 'state-idle'
}

async function initialize(forceRefresh = false) {
  if (forceRefresh) {
    _platformSvgCache = null
    _platformDevicesCache = null
    clearDeviceCommandsCache()
    selectedDeviceId.value = null
  }
  isLoading.value = true
  pageError.value = ''

  try {
    const projectRes = await fetch('/project/')
    if (!projectRes.ok) throw new Error('Could not reach the project endpoint.')
    const project = await projectRes.json() as ProjectResponse
    projectLoaded.value = Boolean(project.project_dir)
    projectDir.value = project.project_dir

    if (!projectLoaded.value) return

    // Restore platform SVG/devices from cache immediately (avoids re-fetch on dashboard revisit)
    if (_platformSvgCache !== null) {
      platformSvg.value = _platformSvgCache === 'missing' ? null : _platformSvgCache
    }
    if (_platformDevicesCache !== null) {
      platformDevices.value = _platformDevicesCache === 'missing' ? [] : _platformDevicesCache
    }

    const [protocolsRes, processesRes, activeRes, reportRes] = await Promise.allSettled([
      fetch('/protocols/'),
      fetch('/processes/'),
      fetch('/run/active'),
      fetch('/run/report'),
    ])

    if (protocolsRes.status === 'fulfilled' && protocolsRes.value.ok) {
      const list = await protocolsRes.value.json() as ProtocolMeta[]
      protocolCount.value = list.length
      if (list.length > 0) {
        const sorted = [...list].sort(
          (a, b) => new Date(b.modified).getTime() - new Date(a.modified).getTime(),
        )
        latestProtocol.value = sorted[0]?.modified ?? null
      }
    }

    if (processesRes.status === 'fulfilled' && processesRes.value.ok) {
      const list = await processesRes.value.json() as ProcessInfo[]
      processCount.value = list.length
    }

    if (activeRes.status === 'fulfilled' && activeRes.value.ok) {
      const data = await activeRes.value.json() as ActiveRunResponse
      activeRunId.value = data.active_run_id
      activeRunState.value = data.state
    }

    if (reportRes.status === 'fulfilled' && reportRes.value.ok) {
      const data = await reportRes.value.json() as RunReport | null
      if (data !== null) lastRun.value = data
    }

    // Fetch platform SVG only once per session
    if (_platformSvgCache === null) {
      try {
        const res = await fetch('/project/platform-svg')
        if (res.ok) {
          const svg = await res.text()
          _platformSvgCache = svg
          platformSvg.value = svg
        } else {
          _platformSvgCache = 'missing'
        }
      } catch {
        _platformSvgCache = 'missing'
      }
    }

    // Fetch the device manifest only once per session; missing manifest (older
    // projects saved before this feature existed) degrades to a non-interactive
    // diagram rather than a page error.
    if (_platformDevicesCache === null) {
      try {
        const res = await fetch('/project/platform-devices')
        if (res.ok) {
          const devices = await res.json() as PlatformDevice[]
          _platformDevicesCache = devices
          platformDevices.value = devices
        } else {
          _platformDevicesCache = 'missing'
        }
      } catch {
        _platformDevicesCache = 'missing'
      }
    }
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : 'Could not load dashboard.'
  } finally {
    isLoading.value = false
  }

  // isLoading must already be false here — .platform-svg-wrap only exists in
  // the v-else branch, which mounts after this flip. Injecting earlier (while
  // still inside the try block above) finds no <svg> and silently no-ops.
  await nextTick()
  injectDeviceOverlay()
}

const SVG_NS = 'http://www.w3.org/2000/svg'

function injectDeviceOverlay() {
  const svg = document.querySelector('.platform-svg-wrap svg')
  if (!svg) return

  // Idempotent: drop any previously injected hit areas before re-adding, since
  // v-html repaints (e.g. after Refresh) wipe them anyway.
  svg.querySelectorAll('[data-device-id]').forEach(el => el.remove())

  for (const device of platformDevices.value) {
    const rect = document.createElementNS(SVG_NS, 'rect')
    rect.setAttribute('x', String(device.x))
    rect.setAttribute('y', String(device.y))
    rect.setAttribute('width', String(device.w))
    rect.setAttribute('height', String(device.h))
    rect.setAttribute('fill', 'transparent')
    rect.setAttribute('class', 'device-hit-area')
    rect.dataset.deviceId = device.id
    svg.appendChild(rect)
  }
}

function onPlatformClick(event: MouseEvent) {
  const target = (event.target as Element).closest('[data-device-id]')
  const id = target?.getAttribute('data-device-id')
  if (id) selectedDeviceId.value = id
}

onMounted(() => {
  void initialize()
})
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Workspace overview</p>
        <h1 class="page-title">Dashboard</h1>
        <p class="page-description">Current project status and quick navigation.</p>
      </div>
      <button type="button" class="button" @click="initialize(true)">
        Refresh
      </button>
    </header>

    <section v-if="isLoading" class="state-card" aria-live="polite">
      <span class="spinner" aria-hidden="true"></span>
      <h2>Loading dashboard</h2>
      <p>Checking project and workspace status.</p>
    </section>

    <section v-else-if="pageError" class="state-card error-state" role="alert">
      <h2>Dashboard unavailable</h2>
      <p>{{ pageError }}</p>
      <button type="button" class="button" @click="() => initialize()">Try again</button>
    </section>

    <section v-else-if="projectLoaded === false" class="state-card">
      <h2>No project loaded</h2>
      <p>Use the CLI to load a project and then refresh.</p>
    </section>

    <template v-else>
      <div class="stats-grid">
        <!-- Project -->
        <div class="stat-card">
          <p class="stat-label">Project</p>
          <p class="stat-value">{{ projectName(projectDir) }}</p>
          <p class="stat-sub">{{ projectDir }}</p>
        </div>

        <!-- Protocols -->
        <div class="stat-card">
          <p class="stat-label">Protocols</p>
          <p class="stat-value">
            <span v-if="protocolCount !== null">{{ protocolCount }}</span>
            <span v-else class="muted">—</span>
          </p>
          <p class="stat-sub">
            <template v-if="latestProtocol">
              Latest: {{ formatDate(latestProtocol) }}
            </template>
            <template v-else>No protocols saved yet</template>
          </p>
        </div>

        <!-- Processes -->
        <div class="stat-card">
          <p class="stat-label">Processes</p>
          <p class="stat-value">
            <span v-if="processCount !== null">{{ processCount }}</span>
            <span v-else class="muted">—</span>
          </p>
          <p class="stat-sub">Registered in project</p>
        </div>

        <!-- Run status -->
        <div class="stat-card">
          <p class="stat-label">Run status</p>
          <template v-if="activeRunId">
            <p class="stat-value">
              <span class="run-badge" :class="activeRunState === 'paused' ? 'state-paused' : 'state-running'">
                {{ activeRunState === 'paused' ? 'Paused' : 'Running' }}
              </span>
            </p>
            <p class="stat-sub">{{ activeRunId.slice(0, 8) }}…</p>
          </template>
          <template v-else-if="lastRun">
            <p class="stat-value">
              <span class="run-badge" :class="runStateClass(lastRun.state)">
                {{ lastRun.state }}
              </span>
            </p>
            <p class="stat-sub">{{ lastRun.run_id.slice(0, 8) }}…</p>
          </template>
          <template v-else>
            <p class="stat-value muted">—</p>
            <p class="stat-sub">No runs recorded yet</p>
          </template>
        </div>
      </div>

      <!-- Platform SVG (only shown when project_dir/draw/platform.svg exists) -->
      <div v-if="platformSvg" class="platform-box">
        <p class="stat-label">Platform</p>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="platform-svg-wrap" v-html="platformSvg" @click="onPlatformClick" />
        <DevicePropertiesPanel
          v-if="selectedDevice"
          :device="selectedDevice"
          @close="selectedDeviceId = null"
        />
      </div>

      <div class="quick-links">
        <RouterLink to="/run-control" class="link-card">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="9"/>
            <path d="m10 8 6 4-6 4V8Z"/>
          </svg>
          Run Control
        </RouterLink>
        <RouterLink to="/protocols" class="link-card">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M7 3h10v4H7zM7 17h10v4H7zM5 12h14M12 7v10"/>
          </svg>
          Protocols
        </RouterLink>
        <RouterLink to="/monitoring" class="link-card">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M3 12h4l2-5 4 10 2-5h6"/>
          </svg>
          Monitoring
        </RouterLink>
        <RouterLink to="/logs" class="link-card">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/>
            <path d="M8 8h8M8 12h8M8 16h5"/>
          </svg>
          Logs
        </RouterLink>
      </div>
    </template>
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
  transition:
    transform 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.button:hover:not(:disabled) {
  border-color: var(--color-border-hover);
  background: var(--color-background-mute);
  transform: translateY(-1px);
}

.state-card {
  min-height: 320px;
  display: grid;
  place-items: center;
  padding: 2.25rem;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
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

.spinner {
  display: inline-block;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-right-color: transparent;
  color: var(--color-primary);
  animation: spin 800ms linear infinite;
}

/* Stats grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.stat-card {
  padding: 1.35rem 1.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.stat-label {
  margin: 0 0 0.5rem;
  color: var(--color-primary);
  font-size: 0.68rem;
  font-weight: 760;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.stat-value {
  margin: 0 0 0.3rem;
  color: var(--color-heading);
  font-size: 1.6rem;
  font-weight: 720;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat-sub {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.78rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.muted {
  color: var(--color-text-muted);
}

/* Run badge */
.run-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.28rem 0.65rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: capitalize;
}

.run-badge::before {
  content: '';
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.state-success {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.state-failed {
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.state-running {
  color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

.state-paused {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.state-idle {
  color: var(--color-text-muted);
  background: var(--color-background-mute);
}

/* Platform SVG box */
.platform-box {
  padding: 1.35rem 1.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
  margin-bottom: 1.25rem;
}

.platform-svg-wrap {
  margin-top: 0.75rem;
  width: 100%;
  overflow: hidden;
}

.platform-svg-wrap :deep(svg) {
  display: block;
  width: 100%;
  height: auto;
  max-height: 480px;
}

.platform-svg-wrap :deep(.device-hit-area) {
  cursor: pointer;
}

.platform-svg-wrap :deep(.device-hit-area:hover) {
  fill: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

/* Quick links */
.quick-links {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
}

.link-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
  padding: 1.1rem 0.75rem;
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
  font-size: 0.82rem;
  font-weight: 640;
  text-decoration: none;
  transition:
    transform 150ms ease,
    border-color 150ms ease,
    background-color 150ms ease;
}

.link-card:hover {
  border-color: var(--color-border-hover);
  background: var(--color-background-mute);
  color: var(--color-heading);
  transform: translateY(-2px);
}

.link-card svg {
  width: 22px;
  height: 22px;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .quick-links {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .quick-links {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}
</style>
