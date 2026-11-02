<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MonitoringConfigPanel from '../components/monitoring/MonitoringConfigPanel.vue'
import { useApiToken } from '../composables/useApiToken'
import { useNotification } from '../composables/useNotification'
import { useRunOptions } from '../composables/useRunOptions'
import { useTheme } from '../composables/useTheme'
import { useRunStatusStore } from '../stores/runStatus'

const TABS = [
  { id: 'run-control', label: 'Run control' },
  { id: 'monitoring', label: 'Monitoring' },
  { id: 'api-access', label: 'API access' },
  { id: 'appearance', label: 'Appearance' },
] as const

type TabId = (typeof TABS)[number]['id']

const ACTIVE_RUN_POLL_MS = 5000

const route = useRoute()
const router = useRouter()
const { notify } = useNotification()
const runOptions = useRunOptions()
const runStatus = useRunStatusStore()
const { token: apiToken, setToken } = useApiToken()
const { theme, setTheme } = useTheme()

const tokenDraft = ref('')

// The tab lives in the URL hash, so other pages can link straight to one.
const activeTab = computed<TabId>(() => {
  const id = route.hash.replace(/^#/, '')
  return TABS.find(tab => tab.id === id)?.id ?? 'run-control'
})

function selectTab(id: TabId) {
  void router.replace({ hash: `#${id}` })
}

// Run options apply when a run starts, so they stay as the active run used
// them until it ends, as they did on Run Control.
const runActive = computed(() => runStatus.runState === 'running' || runStatus.runState === 'paused')
let runPollTimer: ReturnType<typeof window.setInterval> | undefined

function stopRunPolling() {
  if (runPollTimer !== undefined) {
    window.clearInterval(runPollTimer)
    runPollTimer = undefined
  }
}

watch(runActive, active => {
  if (!active) {
    stopRunPolling()
  } else if (runPollTimer === undefined) {
    runPollTimer = window.setInterval(() => {
      void runStatus.checkActiveRun()
    }, ACTIVE_RUN_POLL_MS)
  }
}, { immediate: true })

function saveToken() {
  if (!tokenDraft.value.trim()) return
  setToken(tokenDraft.value)
  tokenDraft.value = ''
  notify('API token saved.', 'success')
}

function clearToken() {
  setToken('')
  tokenDraft.value = ''
  notify('API token cleared.', 'success')
}

onMounted(() => {
  void runStatus.checkActiveRun()
})

onBeforeUnmount(stopRunPolling)
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Settings</p>
        <h1 class="page-title">Configurations</h1>
        <p class="page-description">
          Run options, what to monitor, and API access. The defaults suit most work; change them
          here when you need to.
        </p>
      </div>
    </header>

    <div class="config-content">
      <div class="config-tabs" role="tablist" aria-label="Configuration sections">
        <button
          v-for="tab in TABS"
          :id="`tab-${tab.id}`"
          :key="tab.id"
          type="button"
          role="tab"
          class="config-tab"
          :class="{ active: activeTab === tab.id }"
          :aria-selected="activeTab === tab.id"
          :aria-controls="`panel-${tab.id}`"
          @click="selectTab(tab.id)"
        >
          {{ tab.label }}
        </button>
      </div>

      <section
        v-if="activeTab === 'run-control'"
        id="panel-run-control"
        class="config-card"
        role="tabpanel"
        aria-labelledby="tab-run-control"
      >
        <div class="card-header">
          <h2>Run control</h2>
          <p>How the next run you start from Run Control behaves. Saved in this browser.</p>
        </div>

        <div class="card-body">
          <div v-if="runActive" class="notice warning">
            A run is active. These options can be changed once it ends.
          </div>

          <div class="field">
            <label for="timeout-input">Command timeout</label>
            <input
              id="timeout-input"
              v-model="runOptions.timeout"
              type="text"
              inputmode="text"
              placeholder="10 s"
              :disabled="runActive"
            />
            <span class="field-help">
              Leave blank to wait indefinitely. Use values like <code>5 s</code>.
            </span>
          </div>

          <div class="toggle-list" aria-label="Execution options">
            <label class="toggle-row" for="dry-run-check">
              <input
                id="dry-run-check"
                v-model="runOptions.dryRun"
                type="checkbox"
                :disabled="runActive"
              />
              <span>
                <span class="toggle-title">Dry run</span>
                <span class="field-help">
                  Validate workflow logic without calling physical devices.
                </span>
              </span>
            </label>
            <label class="toggle-row" for="error-resilient-check">
              <input
                id="error-resilient-check"
                v-model="runOptions.errorResilient"
                type="checkbox"
                :disabled="runActive"
              />
              <span>
                <span class="toggle-title">Error-resilient mode</span>
                <span class="field-help">
                  Log device errors and allow independent workflow branches to continue.
                </span>
              </span>
            </label>
            <label class="toggle-row" for="record-monitoring-check">
              <input
                id="record-monitoring-check"
                v-model="runOptions.recordMonitoring"
                type="checkbox"
                :disabled="runActive"
              />
              <span>
                <span class="toggle-title">Record monitoring data</span>
                <span class="field-help">
                  Save every monitored variable reading for the run to log/monitoring/&lt;run_id&gt;/.
                  A run needs at least one variable under Monitoring to record.
                </span>
              </span>
            </label>
          </div>
        </div>
      </section>

      <div
        v-else-if="activeTab === 'monitoring'"
        id="panel-monitoring"
        role="tabpanel"
        aria-labelledby="tab-monitoring"
      >
        <MonitoringConfigPanel />
      </div>

      <section
        v-else-if="activeTab === 'api-access'"
        id="panel-api-access"
        class="config-card"
        role="tabpanel"
        aria-labelledby="tab-api-access"
      >
        <div class="card-header">
          <h2>API access</h2>
          <p>For scripts, and for controlling this work-server from another computer.</p>
        </div>

        <div class="card-body">
          <div class="setting-row">
            <div class="setting-copy">
              <h3>API documentation</h3>
              <p class="field-help">
                The work-server's interactive HTTP reference: every endpoint, with a form to try it.
              </p>
            </div>
            <a href="/docs" target="_blank" rel="noopener" class="button">
              Open API docs
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M14 3h7v7M21 3l-9 9"/>
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              </svg>
            </a>
          </div>

          <div class="setting-row">
            <div class="setting-copy">
              <h3>
                API token
                <span :class="['token-status', { set: apiToken }]">
                  {{ apiToken ? 'Set' : 'Not set' }}
                </span>
              </h3>
              <p class="field-help">
                Only needed to change things (start runs, send commands, save settings) from
                another computer: the work-server accepts those from its own computer, and
                read-only requests from anywhere, without one. Use the token the work-server was
                started with (<code>--token</code>, <code>CHEMUNITED_API_TOKEN</code>, or the
                launcher's API token). It is stored in this browser.
              </p>
            </div>
            <form class="token-form" @submit.prevent="saveToken">
              <input
                v-model="tokenDraft"
                type="password"
                autocomplete="off"
                :placeholder="apiToken ? 'Enter a new token' : 'Paste the token'"
                aria-label="API access token"
              />
              <button type="submit" class="button primary" :disabled="!tokenDraft.trim()">
                Save
              </button>
              <button v-if="apiToken" type="button" class="button" @click="clearToken">
                Clear
              </button>
            </form>
          </div>
        </div>
      </section>

      <section
        v-else
        id="panel-appearance"
        class="config-card"
        role="tabpanel"
        aria-labelledby="tab-appearance"
      >
        <div class="card-header">
          <h2>Appearance</h2>
          <p>How the dashboard looks in this browser.</p>
        </div>

        <div class="card-body">
          <div class="setting-row">
            <div class="setting-copy">
              <h3>Theme</h3>
              <p class="field-help">The toggle at the bottom of the sidebar switches it too.</p>
            </div>
            <div class="segmented" role="radiogroup" aria-label="Theme">
              <button
                type="button"
                role="radio"
                :aria-checked="theme === 'light'"
                :class="{ active: theme === 'light' }"
                @click="setTheme('light')"
              >
                Light
              </button>
              <button
                type="button"
                role="radio"
                :aria-checked="theme === 'dark'"
                :class="{ active: theme === 'dark' }"
                @click="setTheme('dark')"
              >
                Dark
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.config-content {
  max-width: 960px;
}

/* ── Tabs ───────────────────────────────────────────── */
.config-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-bottom: 1.1rem;
}

.config-tab {
  padding: 0.45rem 0.95rem;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-background-soft);
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 680;
  transition:
    color 150ms ease,
    border-color 150ms ease,
    background-color 150ms ease;
}

.config-tab:hover {
  color: var(--color-heading);
  border-color: var(--color-border-hover);
}

.config-tab.active {
  color: var(--color-primary);
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

/* ── Card ───────────────────────────────────────────── */
.config-card {
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
}

.card-header {
  padding: 1.2rem 1.3rem;
  border-bottom: 1px solid var(--color-border);
}

.card-header h2 {
  margin: 0;
  color: var(--color-heading);
  font-size: 1.05rem;
  font-weight: 720;
}

.card-header p {
  margin: 0.32rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.82rem;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
  padding: 1.2rem 1.3rem 1.3rem;
}

.notice {
  padding: 0.72rem 0.85rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
}

.notice.warning {
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 24%, var(--color-border));
  background: var(--color-warning-soft);
}

/* ── Run options ────────────────────────────────────── */
.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  max-width: 420px;
}

.field label {
  font-size: 0.82rem;
  font-weight: 650;
  color: var(--color-heading);
}

.field input[type='text'],
.token-form input {
  width: 100%;
  padding: 0.5rem 0.7rem;
  font-size: 0.875rem;
  color: var(--color-text);
  background: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  transition: border-color 150ms;
}

.field input[type='text']:hover:not(:disabled),
.token-form input:hover {
  border-color: var(--color-border-hover);
}

.field input[type='text']:focus,
.token-form input:focus {
  border-color: var(--color-primary);
  outline: none;
}

.field input[type='text']:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.field-help {
  font-size: 0.77rem;
  color: var(--color-text-muted);
}

.field-help code {
  padding: 0.1em 0.3em;
  border-radius: 4px;
  background: var(--color-background-mute);
  font-family: monospace;
}

.toggle-list {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.toggle-row {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition:
    border-color 150ms,
    background 150ms;
}

.toggle-row:hover {
  border-color: var(--color-border-hover);
  background: var(--color-background-mute);
}

.toggle-row input[type='checkbox'] {
  flex-shrink: 0;
  width: 15px;
  height: 15px;
  margin-top: 0.15rem;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.toggle-row input[type='checkbox']:disabled {
  cursor: not-allowed;
}

.toggle-title {
  display: block;
  margin-bottom: 0.15rem;
  font-size: 0.84rem;
  font-weight: 640;
  color: var(--color-heading);
}

/* ── API access and appearance ──────────────────────── */
.setting-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.85rem 1.5rem;
}

.setting-row + .setting-row {
  padding-top: 1.1rem;
  border-top: 1px solid var(--color-border);
}

.setting-copy {
  flex: 1 1 320px;
  min-width: 0;
}

.setting-copy h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.25rem;
  color: var(--color-heading);
  font-size: 0.9rem;
  font-weight: 680;
}

.setting-copy .field-help {
  margin: 0;
}

.token-status {
  padding: 0.12rem 0.5rem;
  color: var(--color-text-muted);
  border-radius: 999px;
  background: var(--color-background-mute);
  font-size: 0.7rem;
  font-weight: 720;
}

.token-status.set {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.token-form {
  display: flex;
  flex: 1 1 320px;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.token-form input {
  flex: 1 1 180px;
  width: auto;
  min-width: 0;
}

.button {
  min-height: 38px;
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  padding: 0.5rem 0.95rem;
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

.button.primary {
  color: #ffffff;
  border-color: var(--color-primary);
  background: var(--color-primary);
}

.button.primary:hover:not(:disabled) {
  border-color: var(--color-primary-hover);
  background: var(--color-primary-hover);
}

.button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.button svg {
  width: 15px;
  height: 15px;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.segmented {
  display: inline-flex;
  flex: 0 0 auto;
  padding: 0.2rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-mute);
}

.segmented button {
  min-width: 72px;
  padding: 0.4rem 0.8rem;
  color: var(--color-text-muted);
  border: 0;
  border-radius: 7px;
  background: transparent;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 680;
}

.segmented button.active {
  color: var(--color-heading);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
}

@media (max-width: 640px) {
  .card-header,
  .card-body {
    padding-right: 1rem;
    padding-left: 1rem;
  }

  .field {
    max-width: none;
  }
}
</style>
