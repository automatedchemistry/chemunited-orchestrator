<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { type NodeCard, type ProcessCard, type RunState, useRunStatusStore } from '../stores/runStatus'
import { type AcceptedProtocolPlan, operatorInputKey, protocolFileExists } from '../lib/runPresentation'
import { useRunOptions } from '../composables/useRunOptions'
import ExtensionSlot from '../extensions/ExtensionSlot.vue'
import PageActions from '../extensions/PageActions.vue'
import ProcessExecutionCard from '../components/run/ProcessExecutionCard.vue'
import RepeatExecutionGroup from '../components/run/RepeatExecutionGroup.vue'

interface ProtocolMeta { filename: string; modified: string; size_bytes: number }
const store = useRunStatusStore()
const runOptions = useRunOptions()
const timeoutText = computed(() => runOptions.timeout.trim())
const protocols = ref<ProtocolMeta[]>([])
const streamStatus = ref<'closed' | 'opening' | 'open' | 'reconnecting'>('closed')
const runId = ref<string | null>(store.activeRunId)
const isDeleting = ref(false)
const isLoadingPlan = ref(false)
const inputDrafts = ref<Record<string, string>>({})
const nowSeconds = ref(Date.now() / 1000)
let waitTicker: ReturnType<typeof window.setInterval> | null = null
let eventSource: EventSource | null = null
let planRequest = 0
const isRunning = computed(() => store.runState === 'running')
const isPaused = computed(() => store.runState === 'paused')
const isActive = computed(() => isRunning.value || isPaused.value)
const selectedFileExists = computed(() => protocolFileExists(store.selectedProtocol, protocols.value))
const canStart = computed(() => selectedFileExists.value && Boolean(store.protocolPlan) && !isActive.value && !isLoadingPlan.value)
const canDelete = computed(() => selectedFileExists.value && !isActive.value && !isDeleting.value)
const wasStopped = computed(() => store.runState === 'failed' || store.runState === 'cancelled')
const stateText: Record<string, [string, string]> = {
  idle: ['Idle', 'Waiting for protocol dispatch.'], running: ['Running', 'Protocol is executing.'],
  paused: ['Paused', 'Protocol execution is on hold.'], finished: ['Finished', 'Protocol completed successfully.'],
  failed: ['Error', 'Protocol stopped with an error.'], cancelled: ['Cancelled', 'Protocol cancellation requested.'],
}
const stateLabel = computed(() => store.stoppedWithReason ? 'Stopped' : stateText[store.runState]?.[0] ?? store.runState)
const stateCaption = computed(() => store.stoppedWithReason ? store.stopReason : stateText[store.runState]?.[1] ?? '')
const liveCycleCaption = computed(() => {
  const current = store.currentOccurrence
  return current?.group_id && current.cycle ? `${current.group_label || 'Repeat group'} · Cycle ${current.cycle} of ${current.count}` : ''
})
function ordinaryCard(sourceId: string): ProcessCard | undefined { return store.processCards.find(card => card.sourceId === sourceId && !card.occurrence?.group_id) }
async function loadProtocols() {
  try { const res = await fetch('/protocols/'); if (res.ok) protocols.value = await res.json() as ProtocolMeta[] } catch { /* Keep the last available list. */ }
}
async function loadProcessDescriptions() {
  try {
    const res = await fetch('/processes/')
    if (res.ok) {
      const values = await res.json() as Array<{ name: string; description: string }>
      store.descriptions = Object.fromEntries(values.map(item => [item.name, item.description]))
      for (const card of store.processCards) {
        const name = card.occurrence?.process_name || card.stepKey.replace(/_\d+$/, '')
        card.description = store.descriptions[name] ?? ''
      }
    }
  } catch { /* Descriptions are optional; execution status remains available. */ }
}
async function onProtocolChange() {
  const request = ++planRequest
  store.setPlan(null)
  store.setRunState('idle', null)
  runId.value = null
  inputDrafts.value = {}
  if (!store.selectedProtocol) return
  isLoadingPlan.value = true
  store.setMessage('Loading protocol plan…', 'info')
  try {
    const res = await fetch(`/protocols/${encodeURIComponent(store.selectedProtocol)}/plan`)
    if (!res.ok) {
      const error = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(error.detail ?? 'Could not load the protocol plan.')
    }
    const plan = await res.json() as AcceptedProtocolPlan
    if (request !== planRequest) return
    store.setPlan(plan)
    store.setMessage('')
  } catch (error) {
    if (request === planRequest) store.setMessage(error instanceof Error ? error.message : 'Could not load protocol.', 'error')
  } finally { if (request === planRequest) isLoadingPlan.value = false }
}
async function deleteProtocol() {
  if (!canDelete.value) return
  const name = store.selectedProtocol
  if (!window.confirm(`Permanently delete "${name}"? This cannot be undone.`)) return
  isDeleting.value = true
  try {
    const res = await fetch(`/protocols/${encodeURIComponent(name)}`, { method: 'DELETE' })
    if (!res.ok) {
      const error = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(error.detail ?? res.statusText)
    }
    store.selectedProtocol = ''
    store.setPlan(null)
    await loadProtocols()
    store.setMessage(`Protocol "${name}" deleted.`, 'success')
  } catch (error) { store.setMessage(`Delete failed: ${error instanceof Error ? error.message : 'Could not reach the server.'}`, 'error') }
  finally { isDeleting.value = false }
}
function closeStream({ markFailed = false }: { markFailed?: boolean } = {}) {
  if (eventSource) { eventSource.close(); eventSource = null }
  streamStatus.value = 'closed'
  if (markFailed) for (const card of store.processCards) if (card.status === 'running') card.status = 'failed'
}
function openStream() {
  if (eventSource) eventSource.close()
  streamStatus.value = 'opening'
  eventSource = new EventSource('/run/stream')
  eventSource.onopen = () => { streamStatus.value = 'open' }
  eventSource.onmessage = (event: MessageEvent) => {
    let data: Record<string, unknown>
    try { data = JSON.parse(event.data as string) } catch { return }
    if (data.error) {
      store.setMessage(String(data.error), 'error')
      store.setRunState('failed', runId.value)
      closeStream({ markFailed: true })
      return
    }
    if ('event_type' in data) { store.applyEvent(data); return }
    if (!('state' in data)) return
    const state = data.state as RunState
    const reason = typeof data.reason === 'string' ? data.reason : ''
    const wasPaused = store.runState === 'paused'
    store.setRunState(state, runId.value, reason)
    if (state === 'paused') { store.setMessage('Run paused.', 'info'); return }
    if (state === 'running') {
      if (wasPaused) {
        const pausedFor = Date.now() / 1000 - nowSeconds.value
        for (const card of store.processCards) for (const node of card.nodes) if (node.waitStartedAt !== null) node.waitStartedAt += pausedFor
        store.setMessage('Run resumed.', 'info')
      }
      return
    }
    closeStream({ markFailed: state === 'failed' || state === 'cancelled' })
    if (state === 'finished') store.setMessage('Run finished. All processes completed.', 'success')
    else if (state === 'failed') store.setMessage('Run stopped with an error.', 'error')
    else if (reason) store.setMessage(`Run stopped: ${reason}`, 'error')
    else store.setMessage('Run cancelled.', '')
    store.applyStopReason()
    void store.restoreRunSnapshot()
  }
  eventSource.onerror = () => {
    if (eventSource?.readyState === EventSource.CLOSED) closeStream()
    else streamStatus.value = 'reconnecting'
  }
}
async function startRun() {
  if (!canStart.value) return
  store.setMessage('Dispatching protocol request…')
  try {
    const res = await fetch('/run/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ protocol: store.selectedProtocol, dry_run: runOptions.dryRun, timeout_commands: timeoutText.value, error_resilient: runOptions.errorResilient, record_monitoring: runOptions.recordMonitoring }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({})) as { detail?: string }
      store.setMessage(`Failed to start run: ${error.detail ?? res.statusText}`, 'error')
      return
    }
    const data = await res.json() as { run_id: string }
    runId.value = data.run_id
    const selectedPlan = store.protocolPlan
    store.setPlan(null)
    store.setRunState('running', data.run_id)
    if (!await store.restoreRunSnapshot() && selectedPlan) store.setPlan(selectedPlan)
    inputDrafts.value = {}
    store.setMessage('Run accepted. Listening for live events.', 'info')
    openStream()
  } catch (error) { store.setMessage(`Network error: ${error instanceof Error ? error.message : 'Unknown error'}`, 'error') }
}
async function controlRun(path: string, method: string, message: string) {
  store.setMessage(message)
  try {
    const res = await fetch(path, { method })
    if (!res.ok) {
      const error = await res.json().catch(() => ({})) as { detail?: string }
      store.setMessage(error.detail ?? 'The run control request failed.', 'error')
    }
  } catch { store.setMessage('Could not reach the run endpoint.', 'error') }
}
function cancelRun() { return controlRun('/run/', 'DELETE', 'Cancellation requested…') }
function pauseRun() { return controlRun('/run/pause', 'POST', 'Pause requested…') }
function resumeRun() { return controlRun('/run/resume', 'POST', 'Resume requested…') }
async function submitOperatorInput(card: ProcessCard, node: NodeCard) {
  const key = operatorInputKey(card.stepKey, node.nodeId)
  try {
    const res = await fetch('/run/input', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ process_key: card.stepKey, node_id: node.nodeId, value: inputDrafts.value[key] ?? '' }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({})) as { detail?: string }
      store.setMessage(`Reply failed: ${error.detail ?? res.statusText}`, 'error')
      return
    }
    delete inputDrafts.value[key]
    node.awaitingInput = false
    delete store.pendingInputs[key]
  } catch { store.setMessage('Could not reach the run endpoint.', 'error') }
}
onMounted(async () => {
  waitTicker = window.setInterval(() => { if (store.runState !== 'paused') nowSeconds.value = Date.now() / 1000 }, 250)
  await Promise.all([loadProtocols(), loadProcessDescriptions(), store.checkActiveRun()])
  runId.value = store.activeRunId
  if (isActive.value && store.activeRunId) {
    store.setMessage('Reconnected to active run. Listening for events.', 'info')
    store.applyPendingInputs()
    openStream()
  }
})
onUnmounted(() => { closeStream(); if (waitTicker !== null) window.clearInterval(waitTicker) })
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Protocol Execution</p>
        <h1 class="page-title">Run Control</h1>
        <p class="page-description">
          Select a protocol, start it, and follow its progress live.
        </p>
      </div>
    </header>

    <PageActions page="run-control" :context="{ run_id: runId, run_state: store.runState }" />

    <div class="control-grid">
      <!-- Control Panel -->
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Control Panel</h2>
            <p>Pick a protocol and start it.</p>
          </div>
        </div>

        <form class="control-form" @submit.prevent>
          <div class="field">
            <label for="protocol-select">Protocol</label>
            <div class="protocol-row">
              <select
                id="protocol-select"
                v-model="store.selectedProtocol"
                :disabled="isActive || protocols.length === 0"
                @change="onProtocolChange"
              >
                <option value="" disabled>
                  {{ protocols.length === 0 ? 'No protocols available' : 'Select a protocol' }}
                </option>
                <option v-if="store.selectedProtocol && !selectedFileExists" :value="store.selectedProtocol" disabled>
                  {{ store.selectedProtocol }} (run snapshot)
                </option>
                <option v-for="p in protocols" :key="p.filename" :value="p.filename">
                  {{ p.filename }}
                </option>
              </select>
              <button
                type="button"
                class="icon-action"
                :disabled="!canDelete"
                title="Delete selected protocol"
                aria-label="Delete selected protocol"
                @click="deleteProtocol"
              >
                <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path d="M4 6h12M8 3h4l1 3H7l1-3ZM6 6l1 11h6l1-11M9 9v5M11 9v5"/>
                </svg>
              </button>
            </div>
            <span class="field-help">
              {{ store.selectedProtocol && !selectedFileExists
                ? 'The saved source file is no longer available. This run snapshot remains readable; choose a saved protocol to start another run.'
                : 'Protocol file from the project history folder. Use the trash icon to delete the selected file.' }}
            </span>
          </div>

          <div class="field">
            <span class="field-title">Run options</span>
            <div class="option-summary">
              <span
                :class="['option-chip', { dry: runOptions.dryRun }]"
                :title="runOptions.dryRun
                  ? 'Validates the workflow without calling physical devices.'
                  : 'Calls the physical devices.'"
              >
                {{ runOptions.dryRun ? 'Dry run' : 'Real run' }}
              </span>
              <span v-if="runOptions.errorResilient" class="option-chip">Error-resilient</span>
              <span v-if="runOptions.recordMonitoring" class="option-chip">Recording</span>
              <span v-if="timeoutText" class="option-chip">Timeout {{ timeoutText }}</span>
              <RouterLink to="/configurations#run-control" class="option-change">Change</RouterLink>
            </div>
          </div>

          <div class="control-actions">
            <button
              type="button"
              class="primary-action"
              :disabled="!canStart"
              @click="startRun"
            >
              {{ isRunning ? 'Running…' : isPaused ? 'Paused' : 'Start Protocol' }}
            </button>
            <button
              v-if="isRunning"
              type="button"
              class="secondary-action"
              @click="pauseRun"
            >
              Pause
            </button>
            <button
              v-if="isPaused"
              type="button"
              class="secondary-action"
              @click="resumeRun"
            >
              Resume
            </button>
            <button
              v-if="isActive"
              type="button"
              class="danger-action"
              @click="cancelRun"
            >
              Cancel Run
            </button>
          </div>

          <p
            v-if="store.formMessage"
            :class="['form-message', store.formMessageType]"
            role="status"
            aria-live="polite"
          >
            {{ store.formMessage }}
          </p>
        </form>
      </section>

      <!-- System State -->
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>System State</h2>
            <p>Idle, running, and error states update from the live execution stream.</p>
          </div>
          <span :class="['badge', store.stateStyle]">
            {{ stateLabel }}
          </span>
        </div>

        <div class="state-readout" :data-state="store.runState">
          <span :class="['status-orb', store.stateStyle]" aria-hidden="true" />
          <span>
            <span class="status-label">{{ stateLabel }}</span>
            <span :class="['status-caption', { error: store.stoppedWithReason }]">{{ stateCaption }}</span>
          </span>
        </div>

        <div class="run-meta">
          <div class="meta-row">
            <span class="meta-label">Run ID</span>
            <span class="meta-value">{{ runId ?? 'Not assigned' }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">Stream</span>
            <span class="meta-value">{{ streamStatus }}</span>
          </div>
        </div>
      </section>
    </div>

    <ExtensionSlot name="run-control.panels" :context="{ run_id: runId, run_state: store.runState }" />

    <section v-if="store.protocolPlan || store.processCards.length" class="panel spaced-top">
      <div class="panel-header">
        <div>
          <h2>Process Execution</h2>
          <p>{{ store.totalExecutions }} process executions. Shared settings apply to every cycle.</p>
          <p v-if="liveCycleCaption" class="live-cycle-caption" aria-live="polite">{{ liveCycleCaption }}</p>
        </div>
      </div>
      <div v-if="store.protocolPlan" class="execution-tree">
        <template v-for="located in store.locatedItems" :key="located.item.id">
          <RepeatExecutionGroup v-if="located.item.type === 'repeat'" :key="`${runId ?? store.selectedProtocol}:${located.item.id}`" :group="located.item" :offset="located.offset" :plan="store.protocolPlan" :now-seconds="nowSeconds" :drafts="inputDrafts" @reply="submitOperatorInput" @draft="(key, value) => inputDrafts[key] = value" />
          <ProcessExecutionCard v-else-if="ordinaryCard(located.item.id)" :card="ordinaryCard(located.item.id)!" :now-seconds="nowSeconds" :drafts="inputDrafts" :not-executed="wasStopped" @reply="submitOperatorInput" @draft="(key, value) => inputDrafts[key] = value" />
        </template>
      </div>
      <div v-else class="process-grid">
        <ProcessExecutionCard v-for="card in store.processCards" :key="card.stepKey" :card="card" :now-seconds="nowSeconds" :drafts="inputDrafts" :not-executed="wasStopped" @reply="submitOperatorInput" @draft="(key, value) => inputDrafts[key] = value" />
      </div>
    </section>
  </div>
</template>

<style scoped>
/* ── Layout ─────────────────────────────────────────── */
.control-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}

.spaced-top {
  margin-top: 0;
}

/* ── Panel ──────────────────────────────────────────── */
.panel {
  min-width: 0;
  padding: 1.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.panel-header h2 {
  margin-bottom: 0.2rem;
  font-size: 0.95rem;
  font-weight: 680;
  color: var(--color-heading);
}

.panel-header p {
  margin-bottom: 0;
  font-size: 0.82rem;
  color: var(--color-text-muted);
}

/* ── Run-level badge ────────────────────────────────── */
.badge {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.65rem;
  font-size: 0.72rem;
  font-weight: 720;
  letter-spacing: 0.04em;
  border-radius: 999px;
}

.badge::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.badge.idle      { color: var(--color-text-muted);  background: var(--color-background-mute); }
.badge.running   { color: var(--color-primary);     background: var(--color-primary-soft); }
.badge.paused    { color: var(--color-warning);     background: var(--color-warning-soft); }
.badge.finished  { color: var(--color-success);     background: var(--color-success-soft); }
.badge.failed    { color: var(--color-danger);      background: var(--color-danger-soft); }
.badge.cancelled { color: var(--color-text-muted);  background: var(--color-background-mute); }

/* ── State readout ──────────────────────────────────── */
.state-readout {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 0.9rem;
  margin-bottom: 1.25rem;
  border-radius: var(--radius-sm);
  background: var(--color-background-mute);
}

.status-orb {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  border-radius: 50%;
}

.status-orb.idle      { background: var(--color-text-muted); opacity: 0.55; }
.status-orb.running   { background: var(--color-primary); animation: orb-pulse 1.5s ease-in-out infinite; }
.status-orb.paused    { background: var(--color-warning); }
.status-orb.finished  { background: var(--color-success); }
.status-orb.failed    { background: var(--color-danger); }
.status-orb.cancelled { background: var(--color-text-muted); opacity: 0.55; }

.status-label {
  display: block;
  font-size: 0.87rem;
  font-weight: 680;
  color: var(--color-heading);
}

.status-caption {
  display: block;
  font-size: 0.79rem;
  color: var(--color-text-muted);
}

.status-caption.error {
  color: var(--color-danger);
}

/* ── Run meta ───────────────────────────────────────── */
.run-meta {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.meta-row {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  font-size: 0.82rem;
}

.meta-label {
  min-width: 64px;
  flex-shrink: 0;
  color: var(--color-text-muted);
  font-weight: 600;
}

.meta-value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-heading);
  font-family: monospace;
  font-size: 0.78rem;
}

/* ── Form ───────────────────────────────────────────── */
.control-form {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.field label,
.field-title {
  font-size: 0.82rem;
  font-weight: 650;
  color: var(--color-heading);
}

.field select {
  width: 100%;
  padding: 0.5rem 0.7rem;
  font-size: 0.875rem;
  color: var(--color-text);
  background: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  transition: border-color 150ms;
}

.field select:hover:not(:disabled) {
  border-color: var(--color-border-hover);
}

.field select:focus {
  border-color: var(--color-primary);
  outline: none;
}

.field select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.protocol-row {
  display: flex;
  align-items: stretch;
  gap: 0.5rem;
}

.protocol-row select {
  flex: 1;
  min-width: 0;
}

.icon-action {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 2.4rem;
  padding: 0;
  color: var(--color-danger);
  background: var(--color-danger-soft);
  border: 1px solid color-mix(in srgb, var(--color-danger) 22%, transparent);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition:
    background 150ms,
    opacity 150ms;
}

.icon-action:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-danger) 18%, transparent);
}

.icon-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.icon-action svg {
  width: 17px;
  height: 17px;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.field-help {
  font-size: 0.77rem;
  color: var(--color-text-muted);
}

/* ── Run options summary ────────────────────────────── */
.option-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.option-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.22rem 0.6rem;
  font-size: 0.75rem;
  font-weight: 650;
  color: var(--color-text);
  background: var(--color-background-mute);
  border: 1px solid var(--color-border);
  border-radius: 999px;
}

.option-chip.dry {
  color: var(--color-warning);
  background: var(--color-warning-soft);
  border-color: color-mix(in srgb, var(--color-warning) 30%, var(--color-border));
}

.option-change {
  margin-left: 0.2rem;
  font-size: 0.78rem;
  font-weight: 650;
  color: var(--color-primary);
}

.option-change:hover {
  text-decoration: underline;
}

/* ── Control actions ────────────────────────────────── */
.control-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.primary-action,
.secondary-action,
.danger-action {
  padding: 0.55rem 1.1rem;
  font-size: 0.84rem;
  font-weight: 650;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition:
    background 150ms,
    opacity 150ms;
}

.primary-action {
  color: #ffffff;
  background: var(--color-primary);
}

.primary-action:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.primary-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.secondary-action {
  color: var(--color-heading);
  background: var(--color-background-mute);
  border: 1px solid var(--color-border);
}

.secondary-action:hover:not(:disabled) {
  border-color: var(--color-border-hover);
  background: var(--color-background-soft);
}

.danger-action {
  color: var(--color-danger);
  background: var(--color-danger-soft);
  border: 1px solid color-mix(in srgb, var(--color-danger) 22%, transparent);
}

.danger-action:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-danger) 18%, transparent);
}

/* ── Form message ───────────────────────────────────── */
.form-message {
  padding: 0.55rem 0.8rem;
  margin: 0;
  font-size: 0.82rem;
  color: var(--color-text-muted);
  background: var(--color-background-mute);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.form-message.error {
  color: var(--color-danger);
  background: var(--color-danger-soft);
  border-color: color-mix(in srgb, var(--color-danger) 24%, var(--color-border));
}

.form-message.success {
  color: var(--color-success);
  background: var(--color-success-soft);
  border-color: color-mix(in srgb, var(--color-success) 24%, var(--color-border));
}

.form-message.info {
  color: var(--color-primary);
  background: var(--color-primary-soft);
  border-color: color-mix(in srgb, var(--color-primary) 20%, var(--color-border));
}

.page-shell, .control-form, .field, .protocol-row, .panel-header > div { min-width: 0; }
.page-shell { overflow-wrap: anywhere; }
.execution-tree { display: flex; min-width: 0; flex-direction: column; gap: .9rem; }
.process-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr)); gap: 1rem; }
.live-cycle-caption { color: var(--color-primary) !important; font-weight: 650; margin-top: .5rem; }
@keyframes orb-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
@media (max-width: 840px) { .control-grid { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 480px) { .panel { padding: 1rem; } .panel-header { flex-wrap: wrap; } }
@media (prefers-reduced-motion: reduce) { .status-orb.running { animation: none; } }
</style>
