<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SchemaForm from '../components/SchemaForm.vue'
import ProtocolStepRow from '../components/ProtocolStepRow.vue'
import ProtocolCyclePreview from '../components/ProtocolCyclePreview.vue'
import { useNotification } from '../composables/useNotification'
import { customization } from '../extensions/manifest'
import {
  canGroupItems, canonicalDocument, canonicalRepeatCount, duplicateItem, emptyProtocol,
  groupItems, locateItem, moveItem, newSourceId, normalizeProtocol, protocolErrors, removeItem,
  sourceItems, totalExecutions, ungroupItem,
  type ProcessStep, type ProtocolDocument, type RepeatGroup,
} from '../lib/protocolPlan'

interface ProcessInfo { name: string, description: string, library_visible?: boolean }
interface ProtocolMeta { filename: string, modified: string }
type FormProperties = InstanceType<typeof SchemaForm>['$props']['properties']
interface ProcessSchema {
  config_schema?: { properties?: FormProperties }
  main_parameter_schema?: { properties?: FormProperties }
}

const { notify } = useNotification()
const processes = ref<ProcessInfo[]>([])
const protocols = ref<ProtocolMeta[]>([])
const selectedLeftName = ref('')
const document = ref<ProtocolDocument>(emptyProtocol())
const selectedId = ref<string | null>(null)
const repeatSelection = ref(new Set<string>())
const collapsedGroups = ref(new Set<string>())
const cycleGroups = ref(new Set<string>())
const selectedFilename = ref('')
const newName = ref('')
const isModified = ref(false)
const loadingProtocol = ref(false)
const saving = ref(false)
const saveError = ref('')
const pageError = ref('')
const schemaError = ref('')
const schemaLoading = ref(false)
const stepSchema = ref<ProcessSchema | null>(null)
let loadRequest = 0
let schemaRequest = 0
let disposed = false
const schemaCache = new Map<string, ProcessSchema>()

const ALL = '\u0000all'
const OTHER = '\u0000other'
const activeCategory = ref(ALL)
const categoryPrefixes = computed(() => Object.entries(customization.manifest.protocols.process_categories))
const visibleProcesses = computed(() => processes.value.filter(process => process.library_visible !== false))
const categoryOf = (name: string) => categoryPrefixes.value.find(([prefix]) => name.startsWith(prefix))?.[0] ?? OTHER
const categoryTabs = computed(() => {
  if (!categoryPrefixes.value.length) return []
  const tabs = [{ value: ALL, label: 'All' }, ...categoryPrefixes.value.map(([prefix, label]) => ({ value: prefix, label }))]
  if (visibleProcesses.value.some(process => categoryOf(process.name) === OTHER)) {
    tabs.push({ value: OTHER, label: customization.manifest.protocols.other_label })
  }
  return tabs
})
const filteredProcesses = computed(() => activeCategory.value === ALL ? visibleProcesses.value
  : visibleProcesses.value.filter(process => categoryOf(process.name) === activeCategory.value))
const selectedLeftProcess = computed(() => filteredProcesses.value.find(process => process.name === selectedLeftName.value))
const selectedLocation = computed(() => locateItem(document.value, selectedId.value))
const selectedItem = computed(() => selectedLocation.value?.item ?? null)
const selectedProcess = computed(() => selectedItem.value?.type === 'process' ? selectedItem.value : null)
const selectedGroup = computed(() => selectedLocation.value?.parent
  ?? (selectedItem.value?.type === 'repeat' ? selectedItem.value : null))
const busy = computed(() => loadingProtocol.value || saving.value)
const errors = computed(() => protocolErrors(document.value))
const canGroup = computed(() => canGroupItems(document.value, repeatSelection.value))
const canMoveUp = computed(() => !busy.value && Boolean(selectedLocation.value && selectedLocation.value.index > 0))
const canMoveDown = computed(() => !busy.value && Boolean(selectedLocation.value
  && selectedLocation.value.index < selectedLocation.value.siblings.length - 1))
const canRemove = computed(() => !busy.value && Boolean(selectedLocation.value
  && (!selectedLocation.value.parent || selectedLocation.value.siblings.length > 1)))
const sourceCount = computed(() => sourceItems(document.value).filter(item => item.type === 'process').length)
const executionTotal = computed(() => Object.keys(errors.value).length ? '—' : totalExecutions(document.value).toLocaleString())
const canSave = computed(() => !busy.value && isModified.value && Boolean(newName.value.trim())
  && sourceCount.value > 0 && !Object.keys(errors.value).length)
const processProperties = computed<FormProperties>(() => stepSchema.value?.config_schema?.properties ?? {})
const mainProperties = computed<FormProperties>(() => stepSchema.value?.main_parameter_schema?.properties ?? {})
const selectedSaveError = computed(() => selectedItem.value && saveError.value
  && (saveError.value.includes(selectedItem.value.id)
    || (selectedProcess.value && saveError.value.includes(selectedProcess.value.process))) ? saveError.value : '')
const mainSaveError = computed(() => saveError.value.includes('main_parameter') ? saveError.value : '')

async function extractError(response: Response): Promise<string> {
  try {
    const body = await response.json() as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return body.detail.map(value => {
      const item = value as { loc?: Array<string | number>, msg?: string }
      return `${item.loc?.join(' / ') ?? ''}${item.loc?.length ? ': ' : ''}${item.msg ?? String(value)}`
    }).join('; ')
    return JSON.stringify(body.detail ?? `HTTP ${response.status}`)
  } catch { return `HTTP ${response.status}` }
}

function stem(filename: string): string {
  return filename.replace(/_\d{4}-\d{2}-\d{2}T[\d-]+\.json$/, '').replace(/\.json$/, '')
}
function markModified() { isModified.value = true; saveError.value = '' }
function selectCategory(value: string) { activeCategory.value = value; selectedLeftName.value = '' }
function selectSource(id: string) { selectedId.value = id }

async function loadLists() {
  pageError.value = ''
  try {
    const [processResponse, protocolResponse] = await Promise.all([fetch('/processes/'), fetch('/protocols/')])
    if (!processResponse.ok) throw new Error(await extractError(processResponse))
    if (!protocolResponse.ok) throw new Error(await extractError(protocolResponse))
    const [processList, protocolList] = await Promise.all([processResponse.json(), protocolResponse.json()])
    if (disposed) return
    processes.value = processList as ProcessInfo[]
    protocols.value = protocolList as ProtocolMeta[]
  } catch (cause) { if (!disposed) pageError.value = cause instanceof Error ? cause.message : String(cause) }
}

async function onProtocolChange(event: Event) {
  const picker = event.target as HTMLSelectElement
  const filename = picker.value
  if (isModified.value && !window.confirm('Discard unsaved protocol changes?')) {
    picker.value = selectedFilename.value
    return
  }
  const request = ++loadRequest
  selectedFilename.value = filename
  loadingProtocol.value = true
  pageError.value = ''
  saveError.value = ''
  selectedId.value = null
  repeatSelection.value = new Set()
  collapsedGroups.value = new Set()
  cycleGroups.value = new Set()
  document.value = emptyProtocol()
  newName.value = stem(filename)
  isModified.value = false
  try {
    if (!filename) return
    const response = await fetch(`/protocols/${encodeURIComponent(filename)}`)
    if (!response.ok) throw new Error(await extractError(response))
    const loaded = normalizeProtocol(await response.json())
    if (!disposed && request === loadRequest) document.value = loaded
  } catch (cause) {
    if (!disposed && request === loadRequest) pageError.value = cause instanceof Error ? cause.message : String(cause)
  } finally { if (!disposed && request === loadRequest) loadingProtocol.value = false }
}

async function loadSchema(processName: string | undefined) {
  const request = ++schemaRequest
  stepSchema.value = null
  schemaError.value = ''
  schemaLoading.value = Boolean(processName)
  if (!processName) { schemaLoading.value = false; return }
  try {
    let schema = schemaCache.get(processName)
    if (!schema) {
      const response = await fetch(`/processes/${encodeURIComponent(processName)}/schema`)
      if (!response.ok) throw new Error(await extractError(response))
      schema = await response.json() as ProcessSchema
      schemaCache.set(processName, schema)
    }
    if (!disposed && request === schemaRequest) stepSchema.value = schema
  } catch (cause) {
    if (!disposed && request === schemaRequest) schemaError.value = cause instanceof Error ? cause.message : String(cause)
  } finally { if (!disposed && request === schemaRequest) schemaLoading.value = false }
}

function checkSource(id: string, checked: boolean) {
  const next = new Set(repeatSelection.value)
  if (checked) next.add(id); else next.delete(id)
  repeatSelection.value = next
}
function repeatSelected() {
  if (busy.value) return
  const group = groupItems(document.value, repeatSelection.value)
  if (!group) return
  selectedId.value = group.id
  repeatSelection.value = new Set()
  markModified()
}
function ungroup(group: RepeatGroup) {
  if (busy.value || !ungroupItem(document.value, group.id)) return
  if (selectedId.value === group.id) selectedId.value = group.steps[0]?.id ?? null
  collapsedGroups.value.delete(group.id)
  cycleGroups.value.delete(group.id)
  repeatSelection.value = new Set()
  markModified()
}
function toggleGroup(id: string) {
  const next = new Set(collapsedGroups.value)
  if (next.has(id)) next.delete(id); else next.add(id)
  collapsedGroups.value = next
}
function toggleCycles(id: string) {
  const next = new Set(cycleGroups.value)
  if (next.has(id)) next.delete(id); else next.add(id)
  cycleGroups.value = next
  collapsedGroups.value.delete(id)
}
function updateCount(group: RepeatGroup, value: string) { group.count = value; markModified() }
function normalizeCount(group: RepeatGroup) {
  const canonical = canonicalRepeatCount(group.count)
  if (canonical && group.count !== canonical) { group.count = canonical; markModified() }
}
function updateLabel(group: RepeatGroup, value: string) { group.label = value; markModified() }
function addProcess(toGroup = false) {
  const process = selectedLeftProcess.value
  if (!process || busy.value) return
  const step: ProcessStep = { type: 'process', id: newSourceId(document.value), process: process.name, parameters: {} }
  if (toGroup && selectedGroup.value) selectedGroup.value.steps.push(step)
  else document.value.sequence.push(step)
  selectedId.value = step.id
  markModified()
}
function moveSelected(delta: -1 | 1) {
  if (busy.value || !selectedId.value || !moveItem(document.value, selectedId.value, delta)) return
  markModified()
}
function duplicateSelected() {
  if (busy.value || !selectedId.value) return
  const duplicate = duplicateItem(document.value, selectedId.value)
  if (!duplicate) return
  selectedId.value = duplicate.id
  repeatSelection.value = new Set()
  markModified()
}
function removeSelected() {
  if (busy.value || !selectedId.value) return
  const location = selectedLocation.value
  if (!removeItem(document.value, selectedId.value)) return
  repeatSelection.value.delete(selectedId.value)
  selectedId.value = location?.parent?.id ?? null
  markModified()
}
function updateProcessValues(values: Record<string, unknown>) {
  if (busy.value || !selectedProcess.value) return
  selectedProcess.value.parameters = values
  markModified()
}
function updateMainValues(values: Record<string, unknown>) {
  if (busy.value) return
  document.value.main_parameter = values
  markModified()
}

async function saveProtocol() {
  if (!canSave.value) return
  saving.value = true
  saveError.value = ''
  try {
    const data = canonicalDocument(document.value)
    const response = await fetch('/protocols/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.value.trim(), data }),
    })
    if (!response.ok) throw new Error(await extractError(response))
    const result = await response.json() as { filename: string }
    if (disposed) return
    document.value = data
    selectedFilename.value = result.filename
    newName.value = stem(result.filename)
    isModified.value = false
    notify(`Protocol saved: ${result.filename}`, 'success')
    await loadLists()
  } catch (cause) {
    if (!disposed) {
      saveError.value = cause instanceof Error ? cause.message : String(cause)
      const invalid = sourceItems(document.value).find(item => item.type === 'process'
        && saveError.value.includes(`[${item.id}]`))
      if (invalid) {
        selectedId.value = invalid.id
        const parent = locateItem(document.value, invalid.id)?.parent
        if (parent) collapsedGroups.value.delete(parent.id)
      } else if (mainSaveError.value && !selectedProcess.value) {
        selectedId.value = sourceItems(document.value).find(item => item.type === 'process')?.id ?? null
      }
    }
  } finally { if (!disposed) saving.value = false }
}

watch(() => selectedProcess.value?.process, process => { void loadSchema(process) })
onMounted(() => { void loadLists() })
onBeforeUnmount(() => { disposed = true; ++loadRequest; ++schemaRequest })
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div><p class="page-eyebrow">Method development</p><h1 class="page-title">Protocols</h1><p class="page-description">Assemble processes, repeat consecutive steps, and configure their shared parameters.</p></div>
      <button type="button" class="button primary save-header" :disabled="!canSave" @click="saveProtocol">{{ saving ? 'Saving…' : 'Save protocol' }}</button>
    </header>
    <div v-if="pageError" class="notice error" role="alert"><span>{{ pageError }}</span><button type="button" class="button compact" @click="loadLists">Retry lists</button></div>
    <section v-if="selectedProcess" class="schema-panel" aria-labelledby="variables-title">
      <div class="schema-heading"><div><p class="page-eyebrow">Step configuration</p><h2 id="variables-title">Variables</h2><p>Configure <strong>{{ selectedProcess.process }}</strong>.</p></div><span class="selected-step-chip">{{ selectedGroup ? 'Shared process' : 'Process step' }}</span></div>
      <p v-if="selectedGroup" class="shared-parameters">Shared by every cycle in <strong>{{ selectedGroup.label || 'Repeat group' }}</strong>. Editing these values updates the same source process for all repetitions.</p>
      <p v-if="schemaLoading" class="panel-help" role="status">Loading process parameters…</p>
      <p v-if="schemaError" class="notice error" role="alert">{{ schemaError }}</p>
      <p v-if="selectedSaveError" class="notice error" role="alert">{{ selectedSaveError }}</p>
      <template v-if="stepSchema">
        <div class="parameter-section"><div class="section-label"><span>Process parameters</span><span class="section-line"></span></div><SchemaForm :key="selectedProcess.id" :properties="processProperties" :values="selectedProcess.parameters" :readonly="busy" @update:values="updateProcessValues" /></div>
        <div v-if="Object.keys(mainProperties).length" class="parameter-section"><div class="section-label"><span>Experiment parameters</span><span class="section-line"></span></div><p v-if="mainSaveError" class="notice error" role="alert">{{ mainSaveError }}</p><SchemaForm :properties="mainProperties" :values="document.main_parameter" :readonly="busy" @update:values="updateMainValues" /></div>
      </template>
    </section>
    <div class="builder-grid">
      <section class="workspace-panel process-panel" aria-labelledby="library-title">
        <div class="panel-heading"><div><span class="panel-index">01</span><h2 id="library-title">Process library</h2></div><span class="count-badge">{{ filteredProcesses.length }}</span></div>
        <p class="panel-help">Select a process to add to the protocol or the selected repeat group.</p>
        <div v-if="categoryTabs.length" class="category-tabs" role="tablist" aria-label="Process category"><button v-for="tab in categoryTabs" :key="tab.value" type="button" class="category-tab" :class="{ active: activeCategory === tab.value }" role="tab" :aria-selected="activeCategory === tab.value" @click="selectCategory(tab.value)">{{ tab.label }}</button></div>
        <ul class="process-list" aria-label="Available processes"><li v-for="process in filteredProcesses" :key="process.name"><button type="button" class="library-process" :class="{ active: selectedLeftName === process.name }" :aria-pressed="selectedLeftName === process.name" @click="selectedLeftName = process.name"><span class="process-symbol" aria-hidden="true">▤</span><span class="process-copy"><strong>{{ process.name }}</strong><small>{{ process.description || 'Process step' }}</small></span></button></li><li v-if="!filteredProcesses.length" class="empty-state">No processes found.</li></ul>
        <button type="button" class="button primary add-process" :disabled="!selectedLeftProcess || busy" @click="addProcess()">Add to protocol</button>
        <button v-if="selectedGroup" type="button" class="button add-process" :disabled="!selectedLeftProcess || busy" @click="addProcess(true)">Add to {{ selectedGroup.label || 'repeat group' }}</button>
      </section>
      <section class="workspace-panel sequence-panel" aria-labelledby="sequence-title" :aria-busy="loadingProtocol">
        <div class="panel-heading"><div><span class="panel-index">02</span><h2 id="sequence-title">Protocol sequence</h2></div><span class="mode-badge" :class="{ modified: isModified }">{{ isModified ? 'Editing' : selectedFilename ? 'Saved' : 'New protocol' }}</span></div>
        <label class="protocol-field" for="protocol-select">Saved protocol<select id="protocol-select" :value="selectedFilename" :disabled="busy" @change="onProtocolChange"><option value="">New protocol</option><option v-for="protocol in protocols" :key="protocol.filename" :value="protocol.filename">{{ protocol.filename }}</option></select></label>
        <label class="protocol-field" for="protocol-name">Protocol name<input id="protocol-name" v-model="newName" placeholder="Enter a protocol name" :disabled="busy" @input="markModified"></label>
        <div class="sequence-toolbar"><span><strong>{{ sourceCount }}</strong> source steps · <strong>{{ executionTotal }}</strong> executions</span><div class="step-actions" aria-label="Selected item actions"><button type="button" class="icon-button" :disabled="!canMoveUp" title="Move selected item up" aria-label="Move selected item up" @click="moveSelected(-1)">↑</button><button type="button" class="icon-button" :disabled="!canMoveDown" title="Move selected item down" aria-label="Move selected item down" @click="moveSelected(1)">↓</button><button type="button" class="icon-button" :disabled="!selectedItem || busy" title="Duplicate selected item" aria-label="Duplicate selected item" @click="duplicateSelected">⧉</button><button type="button" class="icon-button danger" :disabled="!canRemove" title="Remove selected item (keep at least one step per repeat group)" aria-label="Remove selected item" @click="removeSelected">×</button></div></div>
        <div class="repeat-toolbar"><button type="button" class="button compact" :disabled="!canGroup || busy" @click="repeatSelected">Repeat selected steps</button><span v-if="repeatSelection.size && !canGroup" class="selection-hint">Select consecutive process steps outside repeat groups.</span><span v-else class="selection-hint">Use the checkboxes to group consecutive processes.</span></div>
        <p v-if="loadingProtocol" class="panel-help" role="status">Loading protocol…</p>
        <p v-if="saveError" class="notice error" role="alert">{{ saveError }}</p>
        <ol class="sequence-tree" aria-label="Protocol steps">
          <li v-for="(item, index) in document.sequence" :key="item.id">
            <ProtocolStepRow v-if="item.type === 'process'" :step="item" :position="String(index + 1).padStart(2, '0')" :selected="selectedId === item.id" checkable :checked="repeatSelection.has(item.id)" :disabled="busy" @select="selectSource" @check="checkSource" />
            <section v-else class="repeat-group" :class="{ selected: selectedId === item.id }" :aria-label="item.label || 'Repeat group'">
              <div class="group-heading"><button type="button" class="group-disclosure" :aria-expanded="!collapsedGroups.has(item.id)" :aria-controls="`group-${item.id}`" :aria-label="`${collapsedGroups.has(item.id) ? 'Open' : 'Collapse'} ${item.label || 'repeat group'}`" @click="toggleGroup(item.id)">{{ collapsedGroups.has(item.id) ? '▸' : '▾' }}</button><button type="button" class="group-select" :aria-pressed="selectedId === item.id" @click="selectSource(item.id)"><strong>{{ item.label || 'Repeat group' }}</strong><small>{{ item.steps.length }} source steps · Repeat {{ item.count || '—' }} times</small></button><span class="repeat-symbol" aria-hidden="true">↻</span></div>
              <div :id="`group-${item.id}`" :hidden="collapsedGroups.has(item.id)" class="group-content">
                <div class="group-fields"><label class="protocol-field" :for="`label-${item.id}`">Group label<input :id="`label-${item.id}`" :value="item.label" :disabled="busy" @input="updateLabel(item, ($event.target as HTMLInputElement).value)"></label><label class="protocol-field repeat-count" :for="`count-${item.id}`">Repeat count<input :id="`count-${item.id}`" type="text" inputmode="numeric" :value="item.count" :disabled="busy" :aria-invalid="Boolean(errors[item.id])" :aria-describedby="`count-hint-${item.id}`" @input="updateCount(item, ($event.target as HTMLInputElement).value)" @blur="normalizeCount(item)"></label></div>
                <p :id="`count-hint-${item.id}`" class="count-hint" :class="{ invalid: errors[item.id] }" :role="errors[item.id] ? 'alert' : undefined">{{ errors[item.id] || 'Whole number greater than 1. Every cycle uses the same parameters.' }}</p>
                <p v-if="saveError.includes(item.id)" class="notice error" role="alert">{{ saveError }}</p>
                <div class="group-actions"><button type="button" class="button compact" :disabled="Boolean(errors[item.id])" :aria-pressed="cycleGroups.has(item.id)" @click="toggleCycles(item.id)">{{ cycleGroups.has(item.id) ? 'Show source steps' : 'Show cycles' }}</button><button type="button" class="button compact" :disabled="busy" @click="ungroup(item)">Ungroup</button></div>
                <ProtocolCyclePreview v-if="cycleGroups.has(item.id) && !errors[item.id]" :document="document" :group-id="item.id" :selected-id="selectedId" @select="selectSource" />
                <ol v-else class="group-steps" :aria-label="`${item.label || 'Repeat group'} source steps`"><li v-for="(step, childIndex) in item.steps" :key="step.id"><ProtocolStepRow :step="step" :position="String(childIndex + 1)" :selected="selectedId === step.id" @select="selectSource" /></li></ol>
              </div>
            </section>
          </li>
          <li v-if="!document.sequence.length && !loadingProtocol" class="empty-sequence"><strong>No protocol steps</strong><span>Select a process in the library and add it here.</span></li>
        </ol>
        <button type="button" class="button primary save-mobile" :disabled="!canSave" @click="saveProtocol">{{ saving ? 'Saving…' : 'Save protocol' }}</button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.button { min-height: 40px; display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; padding: 0.62rem 0.95rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); color: var(--color-text); background: var(--color-background-soft); cursor: pointer; font-size: 0.83rem; font-weight: 680; }
.button.primary { color: #fff; border-color: var(--color-primary); background: var(--color-primary); }
.button.primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.button.compact { min-height: 31px; padding: 0.35rem 0.6rem; font-size: 0.72rem; }
.button:disabled, .icon-button:disabled { cursor: not-allowed; opacity: 0.45; }
.builder-grid { display: grid; grid-template-columns: minmax(260px, 0.8fr) minmax(390px, 1.4fr); gap: 1rem; align-items: start; margin-top: 1rem; }
.workspace-panel, .schema-panel { min-width: 0; padding: 1.25rem; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-background-soft); box-shadow: var(--shadow-sm); }
.workspace-panel { min-height: 480px; display: flex; flex-direction: column; }
.panel-heading, .schema-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.panel-heading > div { display: flex; align-items: center; gap: 0.65rem; }
.panel-heading h2, .schema-heading h2 { margin: 0; color: var(--color-heading); font-size: 1rem; font-weight: 700; }
.panel-index { color: var(--color-primary); font-size: 0.68rem; font-weight: 780; letter-spacing: 0.08em; }
.count-badge { min-width: 28px; padding: 0.15rem 0.5rem; color: var(--color-text-muted); border-radius: 999px; background: var(--color-background-mute); text-align: center; font-size: 0.72rem; font-weight: 700; }
.panel-help { margin: 0.55rem 0 1rem; color: var(--color-text-muted); font-size: 0.8rem; }
.category-tabs { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.85rem; }
.category-tab { padding: 0.28rem 0.65rem; color: var(--color-text-muted); border: 1px solid var(--color-border); border-radius: 999px; background: var(--color-background-mute); font-size: 0.72rem; cursor: pointer; }
.category-tab.active { color: var(--color-primary); border-color: var(--color-primary); background: var(--color-primary-soft); }
.process-list, .sequence-tree, .group-steps { list-style: none; padding: 0; margin: 0; }
.process-list { display: grid; gap: 0.45rem; }
.library-process { width: 100%; display: flex; align-items: center; gap: 0.7rem; padding: 0.7rem; text-align: left; border: 1px solid transparent; border-radius: var(--radius-sm); background: var(--color-background-soft); cursor: pointer; }
.library-process:hover { background: var(--color-background-mute); }
.library-process.active { border-color: var(--color-primary); background: var(--color-primary-soft); }
.process-symbol { width: 32px; height: 32px; display: grid; place-items: center; flex-shrink: 0; color: var(--color-primary); border-radius: 9px; background: var(--color-primary-soft); font-size: 1.1rem; }
.process-copy { min-width: 0; display: flex; flex: 1; flex-direction: column; }
.process-copy strong { overflow-wrap: anywhere; color: var(--color-heading); font-size: 0.81rem; font-weight: 670; }
.process-copy small { overflow: hidden; margin-top: 0.15rem; color: var(--color-text-muted); font-size: 0.71rem; text-overflow: ellipsis; white-space: nowrap; }
.add-process { width: 100%; margin-top: 0.8rem; }
.mode-badge { display: inline-flex; padding: 0.28rem 0.55rem; color: var(--color-success); border-radius: 999px; background: var(--color-success-soft); font-size: 0.68rem; font-weight: 720; white-space: nowrap; }
.mode-badge.modified { color: var(--color-warning); background: var(--color-warning-soft); }
.protocol-field { min-width: 0; display: flex; flex-direction: column; gap: 0.35rem; margin-top: 1rem; color: var(--color-text-muted); font-size: 0.72rem; font-weight: 650; }
.protocol-field select, .protocol-field input { width: 100%; min-width: 0; height: 39px; padding: 0 0.7rem; color: var(--color-heading); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-background-soft); font-size: 0.82rem; }
.protocol-field [aria-invalid="true"] { border-color: var(--color-danger); }
.sequence-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem; margin-top: 1rem; padding: 0.4rem 0.45rem 0.4rem 0.7rem; color: var(--color-text-muted); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-background-mute); font-size: 0.72rem; overflow-wrap: anywhere; }
.step-actions { display: flex; align-items: center; gap: 0.15rem; }
.icon-button { width: 31px; height: 31px; display: grid; place-items: center; padding: 0; color: var(--color-text); border: 1px solid transparent; border-radius: 7px; background: transparent; cursor: pointer; font-size: 1rem; }
.icon-button:hover:not(:disabled) { color: var(--color-heading); border-color: var(--color-border); background: var(--color-background-soft); }
.icon-button.danger:hover:not(:disabled) { color: var(--color-danger); }
.repeat-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem; margin: 0.75rem 0; }
.selection-hint { color: var(--color-text-muted); font-size: 0.7rem; flex: 1 1 150px; }
.sequence-tree { display: grid; gap: 0.45rem; margin-top: 0.15rem; }
.sequence-tree > li { min-width: 0; }
.repeat-group { min-width: 0; border: 1px solid color-mix(in srgb, var(--color-primary) 32%, var(--color-border)); border-radius: var(--radius-sm); background: color-mix(in srgb, var(--color-primary-soft) 40%, var(--color-background-soft)); }
.repeat-group.selected { border-color: var(--color-primary); }
.group-heading { display: flex; align-items: center; gap: 0.4rem; padding: 0.7rem; background: var(--color-primary-soft); border-radius: var(--radius-sm); }
.group-disclosure { width: 27px; height: 30px; color: var(--color-primary); border: 0; background: transparent; cursor: pointer; font-size: 1.1rem; }
.group-select { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 0.2rem; padding: 0.1rem; text-align: left; color: var(--color-primary); border: 0; background: transparent; cursor: pointer; overflow-wrap: anywhere; }
.group-select strong { font-size: 0.83rem; }
.group-select small { color: var(--color-text-muted); font-size: 0.71rem; }
.repeat-symbol { color: var(--color-primary); font-size: 1.5rem; }
.group-content { padding: 0 0.75rem 0.75rem; }
.group-fields { display: grid; grid-template-columns: minmax(0, 1.8fr) minmax(110px, 1fr); gap: 0.7rem; }
.count-hint { margin: 0.45rem 0 0.65rem; color: var(--color-text-muted); font-size: 0.7rem; }
.count-hint.invalid { color: var(--color-danger); }
.group-actions { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.65rem; }
.group-steps { display: grid; gap: 0.2rem; margin-left: 0.4rem; padding-left: 0.5rem; border-left: 1px solid color-mix(in srgb, var(--color-primary) 25%, var(--color-border)); }
.empty-state, .empty-sequence { color: var(--color-text-muted); text-align: center; padding: 2rem 1rem; border: 1px dashed var(--color-border); border-radius: var(--radius-md); font-size: 0.8rem; }
.empty-sequence { display: flex; flex-direction: column; gap: 0.4rem; }
.empty-sequence strong { color: var(--color-heading); }
.save-mobile { display: none; width: 100%; margin-top: 1rem; }
.schema-heading { align-items: flex-start; padding-bottom: 1rem; border-bottom: 1px solid var(--color-border); }
.schema-heading h2 { font-size: 1.15rem; }
.schema-heading p:not(.page-eyebrow) { margin: 0.3rem 0 0; color: var(--color-text-muted); font-size: 0.8rem; }
.selected-step-chip { max-width: 280px; padding: 0.35rem 0.65rem; color: var(--color-primary); border-radius: var(--radius-sm); background: var(--color-primary-soft); font-size: 0.7rem; overflow-wrap: anywhere; }
.shared-parameters { margin: 1rem 0 0; padding: 0.7rem 0.8rem; color: var(--color-primary); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-primary-soft); font-size: 0.8rem; }
.parameter-section { margin-top: 1.2rem; }
.section-label { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; color: var(--color-text-muted); font-size: 0.68rem; font-weight: 760; letter-spacing: 0.09em; text-transform: uppercase; }
.section-line { height: 1px; flex: 1; background: var(--color-border); }
.notice { display: flex; flex-wrap: wrap; gap: 0.7rem; align-items: center; justify-content: space-between; margin: 0.75rem 0; padding: 0.75rem; font-size: 0.8rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow-wrap: anywhere; }
.notice.error { color: var(--color-danger); background: var(--color-danger-soft); }
@media(max-width: 900px) { .builder-grid { grid-template-columns: 1fr; } .workspace-panel { min-height: auto; } .process-list { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media(max-width: 640px) { .save-header { display: none; } .save-mobile { display: inline-flex; } .workspace-panel, .schema-panel { padding: 1rem; border-radius: var(--radius-md); } .process-list { grid-template-columns: 1fr; } .schema-heading { flex-direction: column; } .selected-step-chip { max-width: 100%; } .group-fields { grid-template-columns: minmax(0, 1fr); gap: 0; } }
</style>
