<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import SchemaForm from '../components/SchemaForm.vue'
import { useNotification } from '../composables/useNotification'

const { notify } = useNotification()

async function extractError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (Array.isArray(body.detail))
      return body.detail.map((e: { msg: string }) => e.msg).join(', ')
    return String(body.detail ?? `HTTP ${res.status}`)
  } catch {
    return `HTTP ${res.status}`
  }
}

interface Process {
  name: string
  description: string
}

interface ProtocolMeta {
  filename: string
  modified: string
}

const processes = ref<Process[]>([])
const protocols = ref<ProtocolMeta[]>([])

const selectedLeftIdx = ref<number | null>(null)
const selectedLeftProcess = computed(() =>
  selectedLeftIdx.value !== null ? processes.value[selectedLeftIdx.value] : null
)

const protocolSteps = ref<string[]>([])
const selectedStepIdx = ref<number | null>(null)
const selectedStep = computed(() =>
  selectedStepIdx.value !== null ? protocolSteps.value[selectedStepIdx.value] : null
)

const selectedFilename = ref('')
const isModified = ref(false)
const newName = ref('')

const mode = computed<'view' | 'write'>(() =>
  selectedFilename.value && !isModified.value ? 'view' : 'write'
)

const stepSchema = ref<Record<string, unknown> | null>(null)
const stepValues = ref<Record<string, Record<string, unknown>>>({})

const stepDiagramSvg = ref<string | null>(null)
const _diagramCache = new Map<string, string | null>()

const mainParamProperties = computed<Record<string, unknown>>(() => {
  if (!stepSchema.value) return {}
  const s = stepSchema.value as {
    main_parameter_schema?: { properties?: Record<string, unknown> }
  }
  return s.main_parameter_schema?.properties ?? {}
})

async function loadProcesses() {
  const res = await fetch('/processes/')
  if (!res.ok) { notify(await extractError(res), 'error'); return }
  processes.value = await res.json()
}

async function loadProtocols() {
  const res = await fetch('/protocols/')
  if (!res.ok) { notify(await extractError(res), 'error'); return }
  protocols.value = await res.json()
}

async function onProtocolChange(filename: string) {
  selectedFilename.value = filename
  stepSchema.value = null
  selectedStepIdx.value = null
  if (!filename) {
    protocolSteps.value = []
    isModified.value = false
    return
  }
  const res = await fetch(`/protocols/${filename}`)
  if (!res.ok) { notify(await extractError(res), 'error'); return }
  const data = await res.json()
  protocolSteps.value = Object.keys(data).filter(k => k !== 'main_parameter')
  stepValues.value = {}
  for (const [key, val] of Object.entries(data)) {
    stepValues.value[key] = (typeof val === 'object' && val !== null) ? val as Record<string, unknown> : {}
  }
  isModified.value = false
}

function markModified() {
  if (!isModified.value) {
    const stem = selectedFilename.value.replace(/_\d{4}-\d{2}-\d{2}T[\d-]+\.json$/, '')
    newName.value = stem
  }
  isModified.value = true
}

function addProcess() {
  if (!selectedLeftProcess.value) return
  const name = selectedLeftProcess.value.name
  const count = protocolSteps.value.filter(s => s.startsWith(name + '_')).length
  protocolSteps.value.push(`${name}_${count}`)
  markModified()
}

function removeStep() {
  if (selectedStepIdx.value === null) return
  protocolSteps.value.splice(selectedStepIdx.value, 1)
  selectedStepIdx.value = null
  stepSchema.value = null
  stepDiagramSvg.value = null
  if (protocolSteps.value.length === 0) {
    isModified.value = false
  } else {
    markModified()
  }
}

async function selectStep(i: number) {
  selectedStepIdx.value = i
  stepSchema.value = null
  stepDiagramSvg.value = null
  const step = protocolSteps.value[i]
  if (!step) return
  const proc = processes.value.find(p => step.startsWith(p.name + '_'))
  if (!proc) return

  const cachedDiagram = _diagramCache.get(proc.name)
  const diagramPromise = cachedDiagram !== undefined
    ? Promise.resolve(cachedDiagram)
    : fetch(`/processes/${proc.name}/diagram`)
        .then(res => (res.ok ? res.text() : null))
        .then(svg => { _diagramCache.set(proc.name, svg); return svg })
        .catch(() => null)

  const [schemaRes, diagramSvg] = await Promise.all([
    fetch(`/processes/${proc.name}/schema`),
    diagramPromise,
  ])
  if (!schemaRes.ok) { notify(await extractError(schemaRes), 'error'); return }
  stepSchema.value = await schemaRes.json()
  stepDiagramSvg.value = diagramSvg
}

function moveStepUp(i: number) {
  if (i === 0) return
  const steps = [...protocolSteps.value]
  const tmp = steps[i - 1]
  steps[i - 1] = steps[i] ?? ''
  steps[i] = tmp ?? ''
  protocolSteps.value = steps
  selectedStepIdx.value = i - 1
  markModified()
}

function moveStepDown(i: number) {
  if (i >= protocolSteps.value.length - 1) return
  const steps = [...protocolSteps.value]
  const tmp = steps[i + 1]
  steps[i + 1] = steps[i] ?? ''
  steps[i] = tmp ?? ''
  protocolSteps.value = steps
  selectedStepIdx.value = i + 1
  markModified()
}

async function saveProtocol() {
  const name = newName.value.trim()
  if (!name) return
  const data: Record<string, object> = {
    main_parameter: stepValues.value['main_parameter'] ?? {},
  }
  for (const step of protocolSteps.value) {
    data[step] = stepValues.value[step] ?? {}
  }
  const res = await fetch('/protocols/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, data }),
  })
  if (!res.ok) { notify(await extractError(res), 'error'); return }
  notify(`Protocol "${name}" saved.`, 'success')
  await loadProtocols()
  isModified.value = false
}

onMounted(() => {
  loadProcesses()
  loadProtocols()
})
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Method development</p>
        <h1 class="page-title">Protocols</h1>
        <p class="page-description">
          Assemble processes into a repeatable sequence and configure each experimental step.
        </p>
      </div>
      <button
        type="button"
        class="button primary save-header"
        :disabled="!isModified"
        @click="saveProtocol"
      >
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M3 3h11l3 3v11H3V3Z"/>
          <path d="M6 3v5h7V3M6 17v-6h8v6"/>
        </svg>
        Save protocol
      </button>
    </header>

    <section v-if="stepDiagramSvg && selectedStep" class="schema-panel diagram-panel">
      <div class="schema-heading">
        <div>
          <p class="page-eyebrow">Workflow diagram</p>
          <h2>Graph</h2>
          <p>Structure of <strong>{{ selectedStep }}</strong>'s process.</p>
        </div>
      </div>
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="diagram-svg-wrap" v-html="stepDiagramSvg" />
    </section>

    <section v-if="stepSchema && selectedStep" class="schema-panel">
      <div class="schema-heading">
        <div>
          <p class="page-eyebrow">Step configuration</p>
          <h2>Variables</h2>
          <p>Configure the parameters for <strong>{{ selectedStep }}</strong>.</p>
        </div>
        <span class="selected-step-chip">{{ selectedStep }}</span>
      </div>

      <div class="parameter-section">
        <div class="section-label">
          <span>Process parameters</span>
          <span class="section-line"></span>
        </div>
        <SchemaForm
          :properties="((stepSchema as any).config_schema?.properties ?? {})"
          :values="stepValues[selectedStep] ?? {}"
          :readonly="mode === 'view'"
          @update:values="v => { if (selectedStep) stepValues[selectedStep] = v }"
        />
      </div>

      <div v-if="Object.keys(mainParamProperties).length" class="parameter-section">
        <div class="section-label">
          <span>Experiment parameters</span>
          <span class="section-line"></span>
        </div>
        <SchemaForm
          :properties="mainParamProperties as any"
          :values="stepValues['main_parameter'] ?? {}"
          :readonly="mode === 'view'"
          @update:values="v => { stepValues['main_parameter'] = v }"
        />
      </div>
    </section>

    <div class="builder-grid">
      <section class="workspace-panel process-panel">
        <div class="panel-heading">
          <div>
            <span class="panel-index">01</span>
            <h2>Process library</h2>
          </div>
          <span class="count-badge">{{ processes.length }}</span>
        </div>
        <p class="panel-help">Select a process to add it to the protocol sequence.</p>

        <ul class="process-list" aria-label="Available processes">
          <li
            v-for="(p, i) in processes"
            :key="p.name"
            :class="{ active: selectedLeftIdx === i }"
            @click="selectedLeftIdx = i"
          >
            <span class="process-symbol" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <path d="M6 4h12v5H6zM6 15h12v5H6zM12 9v6"/>
              </svg>
            </span>
            <span class="process-copy">
              <strong>{{ p.name }}</strong>
              <small>{{ p.description || 'Process step' }}</small>
            </span>
            <span class="selection-mark" aria-hidden="true">✓</span>
          </li>
          <li v-if="processes.length === 0" class="empty-state">
            <span>No processes found.</span>
          </li>
        </ul>

        <button
          type="button"
          class="button primary add-process"
          :disabled="!selectedLeftProcess"
          title="Add selected process to protocol"
          @click="addProcess"
        >
          Add to protocol
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M4 10h12M11 5l5 5-5 5"/>
          </svg>
        </button>
      </section>

      <section class="workspace-panel sequence-panel">
        <div class="panel-heading sequence-heading">
          <div>
            <span class="panel-index">02</span>
            <h2>Protocol sequence</h2>
          </div>
          <span class="mode-badge" :class="mode">
            <span class="mode-dot"></span>
            {{ mode === 'view' ? 'Read only' : 'Editing' }}
          </span>
        </div>

        <div class="protocol-picker">
          <label :for="isModified ? 'protocol-name' : 'protocol-select'">
            {{ isModified ? 'Protocol name' : 'Saved protocol' }}
          </label>
          <select
            v-if="!isModified"
            id="protocol-select"
            :value="selectedFilename"
            @change="onProtocolChange(($event.target as HTMLSelectElement).value)"
          >
            <option value="">Select a protocol</option>
            <option v-for="p in protocols" :key="p.filename" :value="p.filename">
              {{ p.filename }}
            </option>
          </select>
          <input
            v-else
            id="protocol-name"
            v-model="newName"
            placeholder="Enter a protocol name"
            class="name-input"
          />
        </div>

        <div class="sequence-toolbar">
          <span>{{ protocolSteps.length }} {{ protocolSteps.length === 1 ? 'step' : 'steps' }}</span>
          <div class="step-actions" aria-label="Selected step actions">
            <button
              type="button"
              class="icon-button"
              :disabled="selectedStepIdx === null || selectedStepIdx === 0"
              title="Move selected step up"
              aria-label="Move selected step up"
              @click="moveStepUp(selectedStepIdx!)"
            >
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5 12 5-5 5 5"/></svg>
            </button>
            <button
              type="button"
              class="icon-button"
              :disabled="selectedStepIdx === null || selectedStepIdx === protocolSteps.length - 1"
              title="Move selected step down"
              aria-label="Move selected step down"
              @click="moveStepDown(selectedStepIdx!)"
            >
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5 8 5 5 5-5"/></svg>
            </button>
            <span class="toolbar-divider"></span>
            <button
              type="button"
              class="icon-button danger"
              :disabled="selectedStepIdx === null"
              title="Remove selected step"
              aria-label="Remove selected step"
              @click="removeStep"
            >
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M4 6h12M8 3h4l1 3H7l1-3ZM6 6l1 11h6l1-11M9 9v5M11 9v5"/>
              </svg>
            </button>
          </div>
        </div>

        <ol class="steps" aria-label="Protocol steps">
          <li
            v-for="(step, i) in protocolSteps"
            :key="i"
            :class="{ active: selectedStepIdx === i }"
            @click="selectStep(i)"
          >
            <span class="step-number">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="step-connector" aria-hidden="true"></span>
            <span class="step-name">{{ step }}</span>
            <svg class="step-chevron" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="m8 5 5 5-5 5"/>
            </svg>
          </li>
          <li v-if="protocolSteps.length === 0" class="empty-sequence">
            <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <path d="M8 5h16v7H8zM8 20h16v7H8zM16 12v8"/>
            </svg>
            <strong>No protocol steps</strong>
            <span>Select a process from the library and add it here.</span>
          </li>
        </ol>

        <button
          type="button"
          class="button primary save-mobile"
          :disabled="!isModified"
          @click="saveProtocol"
        >
          Save protocol
        </button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.button {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  padding: 0.62rem 0.95rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-soft);
  color: var(--color-text);
  cursor: pointer;
  font-size: 0.83rem;
  font-weight: 680;
  transition:
    transform 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.button svg {
  width: 17px;
  height: 17px;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.button.primary {
  color: #ffffff;
  border-color: var(--color-primary);
  background: var(--color-primary);
  box-shadow: 0 6px 16px color-mix(in srgb, var(--color-primary) 20%, transparent);
}

.button.primary:hover:not(:disabled) {
  border-color: var(--color-primary-hover);
  background: var(--color-primary-hover);
  transform: translateY(-1px);
}

.button:disabled,
.icon-button:disabled {
  cursor: not-allowed;
  opacity: 0.4;
  box-shadow: none;
}

.save-header {
  flex: 0 0 auto;
}

.builder-grid {
  display: grid;
  grid-template-columns: minmax(270px, 0.82fr) minmax(400px, 1.3fr);
  gap: 1rem;
  align-items: stretch;
  margin-top: 1rem;
}

.workspace-panel,
.schema-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-background-soft);
  box-shadow: var(--shadow-sm);
}

.workspace-panel {
  min-height: 480px;
  display: flex;
  flex-direction: column;
  padding: 1.25rem;
}

.panel-heading,
.schema-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.panel-heading > div {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.panel-heading h2,
.schema-heading h2 {
  margin: 0;
  color: var(--color-heading);
  font-size: 1rem;
  font-weight: 700;
}

.panel-index {
  color: var(--color-primary);
  font-size: 0.68rem;
  font-weight: 780;
  letter-spacing: 0.08em;
}

.count-badge {
  min-width: 28px;
  padding: 0.15rem 0.5rem;
  color: var(--color-text-muted);
  border-radius: 999px;
  background: var(--color-background-mute);
  text-align: center;
  font-size: 0.72rem;
  font-weight: 700;
}

.panel-help {
  margin: 0.55rem 0 1rem;
  color: var(--color-text-muted);
  font-size: 0.8rem;
}

.process-list,
.steps {
  margin: 0;
  padding: 0;
  list-style: none;
}

.process-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.45rem;
}

.process-list > li:not(.empty-state) {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-background-soft);
  cursor: pointer;
  transition:
    border-color 150ms ease,
    background-color 150ms ease,
    transform 150ms ease;
}

.process-list > li:not(.empty-state):hover {
  border-color: var(--color-border-hover);
  background: var(--color-background-mute);
  transform: translateY(-1px);
}

.process-list > li.active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.process-symbol {
  width: 34px;
  height: 34px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  color: var(--color-primary);
  border-radius: 9px;
  background: var(--color-primary-soft);
}

.process-symbol svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.process-copy {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
}

.process-copy strong {
  overflow: hidden;
  color: var(--color-heading);
  font-size: 0.84rem;
  font-weight: 670;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.process-copy small {
  overflow: hidden;
  margin-top: 0.12rem;
  color: var(--color-text-muted);
  font-size: 0.72rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selection-mark {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  color: #ffffff;
  border-radius: 50%;
  background: var(--color-primary);
  font-size: 0.68rem;
  font-weight: 800;
  opacity: 0;
  transform: scale(0.8);
  transition: 150ms ease;
}

.process-list > li.active .selection-mark {
  opacity: 1;
  transform: scale(1);
}

.empty-state,
.empty-sequence {
  color: var(--color-text-muted);
  text-align: center;
}

.empty-state {
  padding: 2rem 1rem;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
}

.add-process {
  width: 100%;
  margin-top: 1rem;
}

.mode-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.28rem 0.55rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 720;
}

.mode-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.mode-badge.view {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.mode-badge.write {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.protocol-picker {
  margin-top: 1.15rem;
}

.protocol-picker label {
  display: block;
  margin-bottom: 0.35rem;
  color: var(--color-text-muted);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.protocol-picker select,
.protocol-picker input {
  width: 100%;
  height: 42px;
  padding: 0 0.75rem;
  color: var(--color-heading);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-soft);
}

.protocol-picker select:hover,
.protocol-picker input:hover {
  border-color: var(--color-border-hover);
}

.protocol-picker input {
  border-color: var(--color-primary);
}

.sequence-toolbar {
  min-height: 43px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1rem;
  padding: 0.4rem 0.45rem 0.4rem 0.75rem;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-mute);
  font-size: 0.74rem;
  font-weight: 650;
}

.step-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.icon-button {
  width: 31px;
  height: 31px;
  display: grid;
  place-items: center;
  padding: 0;
  color: var(--color-text);
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  cursor: pointer;
}

.icon-button:hover:not(:disabled) {
  color: var(--color-heading);
  border-color: var(--color-border);
  background: var(--color-background-soft);
}

.icon-button.danger:hover:not(:disabled) {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 22%, var(--color-border));
  background: var(--color-danger-soft);
}

.icon-button svg,
.step-chevron {
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
  margin: 0 0.15rem;
  background: var(--color-border);
}

.steps {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.42rem;
  margin-top: 0.7rem;
}

.steps > li:not(.empty-sequence) {
  position: relative;
  min-height: 48px;
  display: grid;
  grid-template-columns: 32px 12px minmax(0, 1fr) 20px;
  align-items: center;
  gap: 0.5rem;
  padding: 0.55rem 0.65rem;
  color: var(--color-text);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition:
    border-color 150ms ease,
    background-color 150ms ease;
}

.steps > li:not(.empty-sequence):hover {
  background: var(--color-background-mute);
}

.steps > li.active {
  color: var(--color-heading);
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.step-number {
  color: var(--color-text-muted);
  font-size: 0.68rem;
  font-weight: 760;
  letter-spacing: 0.05em;
}

.step-connector {
  width: 8px;
  height: 8px;
  border: 2px solid var(--color-border-hover);
  border-radius: 50%;
}

.steps > li.active .step-connector {
  border-color: var(--color-primary);
  background: var(--color-primary);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--color-primary) 14%, transparent);
}

.step-name {
  overflow: hidden;
  font-size: 0.82rem;
  font-weight: 620;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-chevron {
  color: var(--color-text-muted);
}

.empty-sequence {
  min-height: 180px;
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  padding: 2rem;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
}

.empty-sequence svg {
  width: 34px;
  height: 34px;
  margin-bottom: 0.75rem;
  color: var(--color-primary);
  stroke: currentColor;
  stroke-width: 1.5;
}

.empty-sequence strong {
  color: var(--color-heading);
  font-size: 0.84rem;
  font-weight: 680;
}

.empty-sequence span {
  max-width: 250px;
  margin-top: 0.25rem;
  font-size: 0.75rem;
}

.save-mobile {
  display: none;
  margin-top: 1rem;
}

.schema-panel {
  padding: 1.35rem;
}

.diagram-svg-wrap {
  margin-top: 0.75rem;
  width: 100%;
  overflow: hidden;
}

.diagram-svg-wrap :deep(svg) {
  display: block;
  width: 100%;
  height: auto;
  max-height: 480px;
}

.schema-heading {
  align-items: flex-start;
  padding-bottom: 1.1rem;
  border-bottom: 1px solid var(--color-border);
}

.schema-heading .page-eyebrow {
  margin-bottom: 0.25rem;
}

.schema-heading h2 {
  font-size: 1.15rem;
}

.schema-heading p:not(.page-eyebrow) {
  margin: 0.3rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.8rem;
}

.schema-heading p strong {
  color: var(--color-heading);
  font-weight: 650;
}

.selected-step-chip {
  max-width: 260px;
  overflow: hidden;
  padding: 0.35rem 0.65rem;
  color: var(--color-primary);
  border-radius: 999px;
  background: var(--color-primary-soft);
  font-size: 0.72rem;
  font-weight: 680;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.parameter-section {
  margin-top: 1.2rem;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  color: var(--color-text-muted);
  font-size: 0.68rem;
  font-weight: 760;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.section-line {
  height: 1px;
  flex: 1;
  background: var(--color-border);
}

@media (max-width: 900px) {
  .builder-grid {
    grid-template-columns: 1fr;
  }

  .workspace-panel {
    min-height: auto;
  }

  .process-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .save-header {
    display: none;
  }

  .workspace-panel,
  .schema-panel {
    padding: 1rem;
    border-radius: var(--radius-md);
  }

  .process-list {
    display: flex;
  }

  .save-mobile {
    display: inline-flex;
    width: 100%;
  }

  .sequence-heading {
    align-items: flex-start;
  }

  .schema-heading {
    flex-direction: column;
  }

  .selected-step-chip {
    max-width: 100%;
  }
}
</style>
