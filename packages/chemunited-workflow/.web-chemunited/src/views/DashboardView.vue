<script lang="ts">
import type { LiveMap } from '../components/live/liveFormat'

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
let _platformLiveCache: LiveMap | 'missing' | null = null
</script>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { RouterLink } from 'vue-router'
import DevicePropertiesPanel, { clearDeviceCommandsCache } from '../components/DevicePropertiesPanel.vue'
import ExtensionSlot from '../extensions/ExtensionSlot.vue'
import PageActions from '../extensions/PageActions.vue'
import PlatformLiveLayer from '../components/live/PlatformLiveLayer.vue'
import type { Box } from '../components/live/liveFormat'
import { createSvgPanZoom, type SvgPanZoom } from '../components/svgPanZoom'
import { usePlatformLive } from '../composables/usePlatformLive'

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
  reason?: string | null
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
// A run stopped with a reason (a safety interlock, say) ended 'cancelled'
// but reads as an error: "stopped", with the reason underneath.
const lastRunLabel = computed(() => (lastRun.value?.reason ? 'stopped' : lastRun.value?.state ?? ''))
const platformSvg = ref<string | null>(null)
const platformDevices = ref<PlatformDevice[]>([])
const selectedDeviceId = ref<string | null>(null)
const platformBox = ref<HTMLElement | null>(null)
const platformWrap = ref<HTMLElement | null>(null)
const isFullscreen = ref(false)
const canFullscreen = document.fullscreenEnabled
const panZoom = shallowRef<SvgPanZoom | null>(null)

// Live platform view: device states and LCD values from /platform/stream,
// drawn where the desktop export's map (/project/platform-live) says.
const {
  live,
  pictures,
  devices: liveDevices,
  displays: liveDisplays,
  connection,
  flashing,
  start: startLive,
  stop: stopLive,
} = usePlatformLive()
const platformLiveMap = ref<LiveMap | null>(null)
const liveLayer = shallowRef<SVGGElement | null>(null)
const showLegend = ref(false)

// A map whose hash no longer matches the SVG would put pictures in the wrong
// places: then only rings and command text, on the platform-devices boxes.
const validLiveMap = computed(() => platformLiveMap.value?.svg_matches ? platformLiveMap.value : null)
const liveMapStale = computed(() => platformLiveMap.value !== null && !platformLiveMap.value.svg_matches)
const deviceBoxes = computed<Record<string, Box>>(() => Object.fromEntries(
  platformDevices.value.map(device => [device.id, [device.x, device.y, device.w, device.h]]),
))
const liveOn = computed(() => live.value && connection.value === 'open')
const livePill = computed(() => {
  if (connection.value === 'open') return live.value ? 'live' : 'not-live'
  return connection.value
})
const LIVE_PILL_TEXT: Record<string, string> = {
  live: '● Live',
  connecting: '◌ Connecting…',
  reconnecting: '◌ Reconnecting…',
  disconnected: '■ Disconnected — picture frozen',
}
const selectedLiveState = computed(() =>
  selectedDeviceId.value ? liveDevices.value[selectedDeviceId.value] ?? null : null,
)

const selectedDevice = computed(
  () => platformDevices.value.find(device => device.id === selectedDeviceId.value) ?? null,
)

const devicesByLabel = computed(() => [...platformDevices.value].sort(
  (a, b) => a.label.localeCompare(b.label, undefined, { numeric: true, sensitivity: 'base' }),
))

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
  if (s === 'failed' || s === 'error' || s === 'stopped') return 'state-failed'
  if (s === 'running') return 'state-running'
  if (s === 'paused') return 'state-paused'
  return 'state-idle'
}

async function initialize(forceRefresh = false) {
  if (forceRefresh) {
    _platformSvgCache = null
    _platformDevicesCache = null
    _platformLiveCache = null
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
    if (_platformLiveCache !== null) {
      platformLiveMap.value = _platformLiveCache === 'missing' ? null : _platformLiveCache
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

    // The live map is missing for projects saved before the live view
    // existed: the panel then shows rings and command text only.
    if (_platformLiveCache === null) {
      try {
        const res = await fetch('/project/platform-live')
        if (res.ok) {
          const map = await res.json() as LiveMap
          _platformLiveCache = map
          platformLiveMap.value = map
        } else {
          _platformLiveCache = 'missing'
          platformLiveMap.value = null
        }
      } catch {
        _platformLiveCache = 'missing'
        platformLiveMap.value = null
      }
    }
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : 'Could not load dashboard.'
  } finally {
    isLoading.value = false
  }
}

const SVG_NS = 'http://www.w3.org/2000/svg'

// The click boxes are a layer inside the platform <svg>, so they follow pan and
// zoom with no alignment code. Redrawing them never touches the viewBox.
function drawDeviceLayer() {
  const svg = platformWrap.value?.querySelector('svg')
  if (!svg) return

  // Idempotent: drop any previously drawn hit areas before re-adding.
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
  markSelectedDevice()
}

function markSelectedDevice() {
  platformWrap.value?.querySelectorAll<SVGRectElement>('.device-hit-area').forEach(rect => {
    rect.classList.toggle('is-selected', rect.dataset.deviceId === selectedDeviceId.value)
  })
}

function onPlatformClick(event: MouseEvent) {
  const target = (event.target as Element).closest('[data-device-id]')
  const id = target?.getAttribute('data-device-id')
  if (id) selectedDeviceId.value = id
}

function findDevice(id: string) {
  const device = platformDevices.value.find(item => item.id === id)
  if (!device) return
  selectedDeviceId.value = device.id
  panZoom.value?.focus({ x: device.x, y: device.y, width: device.w, height: device.h })
}

function toggleFullscreen() {
  if (document.fullscreenElement) {
    void document.exitFullscreen()
    return
  }
  platformBox.value?.requestFullscreen().catch(() => {
    // Refused by the browser; the panel simply stays inline.
  })
}

function onFullscreenChange() {
  const box = platformBox.value
  isFullscreen.value = box !== null && document.fullscreenElement === box
}

// v-html creates a new <svg> each time the panel mounts (first load, Refresh),
// so navigation is attached to each new element and torn down with it.
watch([platformWrap, platformSvg], ([wrap], _previous, onCleanup) => {
  const svg = wrap?.querySelector('svg')
  if (!svg) return
  const controller = createSvgPanZoom(svg)
  panZoom.value = controller
  onCleanup(() => {
    controller.destroy()
    if (panZoom.value === controller) panZoom.value = null
  })
}, { flush: 'post' })

// The live layer sits in the <svg> under the click boxes, which drawDeviceLayer
// always appends after it, so clicks still reach the devices.
watch([platformWrap, platformSvg], ([wrap], _previous, onCleanup) => {
  const svg = wrap?.querySelector('svg')
  if (!svg) return
  const layer = document.createElementNS(SVG_NS, 'g')
  layer.setAttribute('class', 'live-layer')
  layer.setAttribute('pointer-events', 'none')
  svg.insertBefore(layer, svg.querySelector('.device-hit-area'))
  liveLayer.value = layer
  onCleanup(() => {
    layer.remove()
    if (liveLayer.value === layer) liveLayer.value = null
  })
}, { flush: 'post' })

watch(platformSvg, svg => {
  if (svg) startLive()
  else stopLive()
})

watch([platformWrap, platformSvg, platformDevices], drawDeviceLayer, { flush: 'post' })
watch(selectedDeviceId, markSelectedDevice, { flush: 'post' })

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  void initialize()
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
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
              <span class="run-badge" :class="runStateClass(lastRunLabel)">
                {{ lastRunLabel }}
              </span>
            </p>
            <p class="stat-sub">{{ lastRun.run_id.slice(0, 8) }}…</p>
            <p v-if="lastRun.reason" class="stat-sub stat-reason" :title="lastRun.reason">
              {{ lastRun.reason }}
            </p>
          </template>
          <template v-else>
            <p class="stat-value muted">—</p>
            <p class="stat-sub">No runs recorded yet</p>
          </template>
        </div>
      </div>

      <PageActions page="dashboard" :context="{ project_dir: projectDir }" />
      <ExtensionSlot
        name="dashboard.cards"
        :context="{ project_dir: projectDir, run_id: activeRunId, run_state: activeRunState }"
      />

      <!-- Platform SVG (only shown when project_dir/draw/platform.svg exists) -->
      <div v-if="platformSvg" ref="platformBox" class="platform-box">
        <div class="platform-header">
          <p class="stat-label">Platform</p>
          <RouterLink
            v-if="livePill === 'not-live'"
            to="/monitoring"
            class="live-pill is-not-live"
            title="The platform view is live while monitoring is on"
          >
            ○ Not live — start monitoring
          </RouterLink>
          <span v-else class="live-pill" :class="`is-${livePill}`" role="status">
            {{ LIVE_PILL_TEXT[livePill] }}
          </span>
          <span class="platform-hint">Ctrl + scroll to zoom · drag to pan</span>
          <div class="platform-toolbar" role="toolbar" aria-label="Platform view">
            <template v-if="devicesByLabel.length">
              <select
                class="find-select"
                title="Find component"
                aria-label="Find component"
                :value="selectedDeviceId ?? ''"
                @change="findDevice(($event.target as HTMLSelectElement).value)"
              >
                <option value="" disabled>Find component…</option>
                <option v-for="device in devicesByLabel" :key="device.id" :value="device.id">
                  {{ device.label }}
                </option>
              </select>
              <span class="toolbar-divider"></span>
            </template>
            <button
              type="button"
              class="icon-button"
              title="Zoom out"
              aria-label="Zoom out"
              @click="panZoom?.zoomOut()"
            >
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <circle cx="9" cy="9" r="5.5"/>
                <path d="m13 13 4 4M6.5 9h5"/>
              </svg>
            </button>
            <button
              type="button"
              class="icon-button"
              title="Zoom in"
              aria-label="Zoom in"
              @click="panZoom?.zoomIn()"
            >
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <circle cx="9" cy="9" r="5.5"/>
                <path d="m13 13 4 4M6.5 9h5M9 6.5v5"/>
              </svg>
            </button>
            <button
              type="button"
              class="icon-button"
              title="Fit to view"
              aria-label="Fit to view"
              @click="panZoom?.fit()"
            >
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M3.5 9.5 10 4l6.5 5.5M5.5 8v8h9V8"/>
              </svg>
            </button>
            <span class="toolbar-divider"></span>
            <button
              type="button"
              class="icon-button"
              :class="{ 'is-active': showLegend }"
              title="Legend"
              aria-label="Legend"
              :aria-expanded="showLegend"
              @click="showLegend = !showLegend"
            >
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <circle cx="10" cy="10" r="7"/>
                <path d="M8 8a2 2 0 1 1 2.6 1.9c-.4.2-.6.5-.6.9V12M10 14.5v.1"/>
              </svg>
            </button>
            <template v-if="canFullscreen">
              <span class="toolbar-divider"></span>
              <button
                type="button"
                class="icon-button"
                :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
                :aria-label="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
                @click="toggleFullscreen"
              >
                <svg v-if="isFullscreen" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path d="M7.5 3v4.5H3M17 7.5h-4.5V3M12.5 17v-4.5H17M3 12.5h4.5V17"/>
                </svg>
                <svg v-else viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path d="M3 7.5V3h4.5M12.5 3H17v4.5M17 12.5V17h-4.5M7.5 17H3v-4.5"/>
                </svg>
              </button>
            </template>
          </div>
        </div>
        <p v-if="liveMapStale" class="platform-note">
          The drawing changed after its live map was saved. Save the project again in
          the desktop app to see device pictures and LCDs.
        </p>
        <p v-else-if="liveOn && !pictures" class="platform-note">
          Device pictures are off: the work-server needs chemunited-core
          (<code>pip install chemunited-workflow[live]</code>).
        </p>
        <dl v-if="showLegend" class="live-legend">
          <dt>Rotor lines, badges, relay lights</dt>
          <dd>The last command the device received</dd>
          <dt>Turning ring and command text</dt>
          <dd>The device is running that command</dd>
          <dt>Short flash</dt>
          <dd>A command went to a device that doesn't report when it finishes</dd>
          <dt>Grey “?”</dt>
          <dd>Unknown: no command since the work-server started, or the last one failed</dd>
          <dt>Black LCD with a value</dt>
          <dd>The latest monitoring reading of its variable</dd>
          <dt>LCD showing --</dt>
          <dd>Not live, no reading yet, or the reading failed</dd>
          <dt>LCD showing “not monitored”</dt>
          <dd>Its variable isn't in the monitoring list</dd>
        </dl>
        <!-- eslint-disable vue/no-v-html -->
        <div
          ref="platformWrap"
          class="platform-svg-wrap"
          v-html="platformSvg"
          @click="onPlatformClick"
        />
        <!-- eslint-enable vue/no-v-html -->
        <Teleport v-if="liveLayer" :to="liveLayer">
          <PlatformLiveLayer
            :live="live"
            :connection="connection"
            :devices="liveDevices"
            :displays="liveDisplays"
            :flashing="flashing"
            :map="validLiveMap"
            :boxes="deviceBoxes"
          />
        </Teleport>
        <DevicePropertiesPanel
          v-if="selectedDevice"
          :device="selectedDevice"
          :live-state="selectedLiveState"
          :live-on="liveOn"
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

.stat-reason {
  margin-top: 0.2rem;
  color: var(--color-danger);
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

.platform-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}

.platform-header .stat-label {
  margin: 0;
}

.platform-hint {
  color: var(--color-text-muted);
  font-size: 0.74rem;
}

.live-pill {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.74rem;
  font-weight: 700;
  text-decoration: none;
  white-space: nowrap;
}

.live-pill.is-live {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.live-pill.is-not-live {
  color: var(--color-text);
  border: 1px solid var(--color-border);
  background: var(--color-background-mute);
}

.live-pill.is-not-live:hover {
  border-color: var(--color-border-hover);
  color: var(--color-heading);
}

.live-pill.is-connecting,
.live-pill.is-reconnecting {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.live-pill.is-disconnected {
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.icon-button.is-active {
  color: var(--color-primary);
  border-color: var(--color-border);
  background: var(--color-background-soft);
}

.platform-note {
  margin: 0.6rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.78rem;
}

.live-legend {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.3rem 1rem;
  margin: 0.75rem 0 0;
  padding: 0.75rem 0.9rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-mute);
  font-size: 0.78rem;
}

.live-legend dt {
  color: var(--color-heading);
  font-weight: 680;
}

.live-legend dd {
  margin: 0;
  color: var(--color-text-muted);
}

.platform-toolbar {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: auto;
  padding: 0.25rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-mute);
}

.find-select {
  min-width: 0;
  max-width: 220px;
  height: 31px;
  padding: 0 0.5rem;
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 7px;
  background: var(--color-background-soft);
  cursor: pointer;
  font-size: 0.78rem;
}

.icon-button {
  width: 31px;
  height: 31px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  padding: 0;
  color: var(--color-text);
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  cursor: pointer;
}

.icon-button:hover {
  color: var(--color-heading);
  border-color: var(--color-border);
  background: var(--color-background-soft);
}

.icon-button svg {
  width: 17px;
  height: 17px;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.toolbar-divider {
  width: 1px;
  height: 19px;
  flex: 0 0 auto;
  margin: 0 0.15rem;
  background: var(--color-border);
}

.platform-svg-wrap {
  height: 480px;
  min-height: 240px;
  margin-top: 0.75rem;
  overflow: hidden;
  resize: vertical;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.platform-svg-wrap > :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
}

.platform-svg-wrap > :deep(svg.is-panning),
.platform-svg-wrap :deep(svg.is-panning .device-hit-area) {
  cursor: grabbing;
}

.platform-svg-wrap :deep(.device-hit-area) {
  cursor: pointer;
}

.platform-svg-wrap :deep(.device-hit-area:hover),
.platform-svg-wrap :deep(.device-hit-area.is-selected) {
  fill: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

.platform-svg-wrap :deep(.device-hit-area.is-selected) {
  stroke: var(--color-primary);
  stroke-width: 2px;
  vector-effect: non-scaling-stroke;
}

.platform-box:fullscreen {
  display: flex;
  flex-direction: column;
  overflow: auto;
  border-radius: 0;
}

.platform-box:fullscreen .platform-svg-wrap {
  flex: 1 1 auto;
  /* The resize handle leaves an inline height behind; the screen decides here. */
  height: auto !important;
  max-height: none;
  resize: none;
}

.platform-box:fullscreen .device-panel {
  flex: 0 0 auto;
  max-height: 40vh;
  overflow: auto;
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

  .platform-hint {
    display: none;
  }
}

@media (max-width: 640px) {
  .platform-toolbar {
    width: 100%;
    margin-left: 0;
  }

  .live-legend {
    grid-template-columns: 1fr;
  }

  .live-legend dd {
    margin-bottom: 0.3rem;
  }

  .find-select {
    flex: 1;
    max-width: none;
  }
}

/* On touch screens dragging the drawing pans it, so leave some page around it
   to scroll by. */
@media (pointer: coarse) {
  .platform-hint {
    display: none;
  }

  .platform-svg-wrap {
    max-height: 70vh;
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
