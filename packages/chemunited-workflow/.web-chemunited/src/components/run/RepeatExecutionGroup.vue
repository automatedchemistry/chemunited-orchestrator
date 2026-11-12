<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { RepeatGroup } from '../../lib/protocolPlan'
import { cyclePage, occurrenceMetadata, type AcceptedProtocolPlan } from '../../lib/runPresentation'
import { makeProcessCard, type NodeCard, type ProcessCard, useRunStatusStore } from '../../stores/runStatus'
import ProcessExecutionCard from './ProcessExecutionCard.vue'

const props = defineProps<{ group: RepeatGroup; offset: string; plan: AcceptedProtocolPlan; nowSeconds: number; drafts: Record<string, string> }>()
const emit = defineEmits<{ reply: [card: ProcessCard, node: NodeCard]; draft: [key: string, value: string] }>()
const store = useRunStatusStore()
const opened = ref(true)
const expandedCycles = ref<Record<string, boolean>>({})
const historyStart = ref('1')
const futureStart = ref('1')
const jumpCycle = ref('')
const jumpError = ref('')
const previewCards = ref<Record<string, ProcessCard[]>>({})
const loading = ref<Record<string, boolean>>({})
const previewErrors = ref<Record<string, string>>({})
const processPages = ref<Record<string, number>>({})
const PAGE_SIZE = 4n
const PROCESS_PAGE_SIZE = 20
const active = computed(() => store.runState === 'running' || store.runState === 'paused')
const stopped = computed(() => ['failed', 'cancelled'].includes(store.runState))
const cards = computed(() => store.processCards.filter(card => card.occurrence?.group_id === props.group.id))
const cycles = computed(() => {
  const result = new Map<string, ProcessCard[]>()
  for (const card of cards.value) {
    const cycle = card.occurrence?.cycle
    if (!cycle) continue
    const list = result.get(cycle) ?? []
    list.push(card)
    result.set(cycle, list)
  }
  return result
})
const completedCycles = computed(() => [...cycles.value.entries()].filter(([, values]) => values.filter(card => !card.interrupted && (card.status === 'completed' || card.status === 'failed')).length === props.group.steps.length))
const completedCount = computed(() => BigInt(completedCycles.value.length).toString())
const completedEnd = computed(() => completedCycles.value.reduce((maximum, [cycle]) => BigInt(cycle) > maximum ? BigInt(cycle) : maximum, 0n))
const currentCycle = computed(() => {
  const running = cards.value.find(card => card.status === 'running')?.occurrence?.cycle
  if (running) return running
  const current = store.currentOccurrence
  if (current?.group_id === props.group.id && current.cycle && !completedCycles.value.some(([cycle]) => cycle === current.cycle)) return current.cycle
  return null
})
const touchedEnd = computed(() => [...cycles.value.keys()].reduce((maximum, cycle) => BigInt(cycle) > maximum ? BigInt(cycle) : maximum, 0n))
const futureMinimum = computed(() => (touchedEnd.value + 1n).toString())
const historyCycles = computed(() => cyclePage(historyStart.value, completedEnd.value.toString()))
const futureCycles = computed(() => cyclePage(futureStart.value, props.group.count))
const failedCount = computed(() => cards.value.filter(card => card.hasFailed).length)
const inputCount = computed(() => cards.value.reduce((total, card) => total + card.nodes.filter(node => node.awaitingInput).length, 0))
const firstError = computed(() => cards.value.find(card => card.hasFailed)?.errorMessage ?? '')
const promptCycles = computed(() => [...new Set(cards.value.filter(card => card.nodes.some(node => node.awaitingInput)).map(card => card.occurrence?.cycle).filter((cycle): cycle is string => Boolean(cycle)))].slice(0, 4))
const groupState = computed(() => inputCount.value ? 'Reply needed' : failedCount.value ? 'Errors' : completedCount.value === props.group.count ? 'Completed' : currentCycle.value ? active.value ? 'Running' : 'Interrupted' : stopped.value && touchedEnd.value === 0n ? 'Not executed' : 'Waiting')

watch(futureMinimum, value => { if (BigInt(futureStart.value) < BigInt(value)) futureStart.value = value }, { immediate: true })
watch(completedEnd, (value, previous) => {
  if (previous === undefined || previous === 0n || BigInt(historyStart.value) + PAGE_SIZE > previous) historyStart.value = (value > 3n ? value - 3n : 1n).toString()
}, { immediate: true })
watch(currentCycle, (cycle, previous) => {
  if (previous && previous !== cycle && completedCycles.value.some(([value]) => value === previous)) expandedCycles.value[previous] = false
  if (!cycle) return
  expandedCycles.value[cycle] = true
  opened.value = true
  void loadCycle(cycle)
}, { immediate: true })

function cycleCards(cycle: string): ProcessCard[] {
  const actual = cycles.value.get(cycle) ?? []
  const preview = previewCards.value[cycle]
  if (!preview) return actual.slice(0, PROCESS_PAGE_SIZE)
  const page = preview.map(card => actual.find(item => item.stepKey === card.stepKey) ?? card)
  // Background prompts and failures remain visible even when their source process
  // is outside the currently inspected process page.
  return [...page, ...actual.filter(card => !page.some(item => item.stepKey === card.stepKey) && (card.status === 'running' || card.nodes.some(node => node.awaitingInput))) ]
}
function cycleErrors(cycle: string): number { return (cycles.value.get(cycle) ?? []).filter(card => card.hasFailed).length }
function cycleInputCount(cycle: string): number { return (cycles.value.get(cycle) ?? []).reduce((total, card) => total + card.nodes.filter(node => node.awaitingInput).length, 0) }
function cycleError(cycle: string): string { return (cycles.value.get(cycle) ?? []).find(card => card.hasFailed)?.errorMessage ?? '' }
function cycleStatus(cycle: string): string {
  if (cycleInputCount(cycle)) return 'Reply needed'
  if (cycle === currentCycle.value && !active.value) return 'Interrupted'
  if (cycleErrors(cycle)) return 'Has errors'
  if (completedCycles.value.some(([value]) => value === cycle)) return 'Completed'
  if (cycle === currentCycle.value) return active.value ? 'Running' : 'Interrupted'
  return stopped.value ? 'Not executed' : 'Waiting'
}
function displayedCycles(): Array<{ cycle: string; section: string }> {
  return [
    ...historyCycles.value.map(cycle => ({ cycle, section: 'history' })),
    ...(currentCycle.value ? [{ cycle: currentCycle.value, section: 'current' }] : []),
    ...futureCycles.value.map(cycle => ({ cycle, section: 'future' })),
  ]
}
async function loadCycle(cycle: string) {
  if (loading.value[cycle]) return
  loading.value[cycle] = true
  previewErrors.value[cycle] = ''
  const firstProcess = (processPages.value[cycle] ?? 0) * PROCESS_PAGE_SIZE
  const offset = BigInt(props.offset) + (BigInt(cycle) - 1n) * BigInt(props.group.steps.length) + BigInt(firstProcess)
  try {
    const response = await fetch('/protocols/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: props.plan.resolved_document ?? props.plan.source_document ?? props.plan.document, offset: offset.toString(), limit: Math.min(PROCESS_PAGE_SIZE, props.group.steps.length - firstProcess) }),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({})) as { detail?: string }
      throw new Error(error.detail ?? 'Could not load cycle steps.')
    }
    const result = await response.json() as { occurrences: Record<string, unknown>[] }
    previewCards.value[cycle] = result.occurrences.map(raw => {
      const occurrence = occurrenceMetadata(raw)
      const step = props.group.steps.find(item => item.id === occurrence?.source_id)
      if (!step || !occurrence) throw new Error('The cycle preview does not match the accepted protocol.')
      return makeProcessCard(step, occurrence.execution_key, store.descriptions[step.process] ?? '', occurrence)
    })
    // Keep only visible page data, never a cache of every inspected future cycle.
    const visible = new Set(displayedCycles().map(item => item.cycle))
    for (const key of Object.keys(previewCards.value)) if (!visible.has(key)) delete previewCards.value[key]
  } catch (error) { previewErrors.value[cycle] = error instanceof Error ? error.message : 'Could not load cycle steps.' }
  finally { loading.value[cycle] = false }
}
function toggleCycle(cycle: string) {
  expandedCycles.value[cycle] = !expandedCycles.value[cycle]
  if (expandedCycles.value[cycle]) void loadCycle(cycle)
}
function pageHistory(direction: number) {
  const next = BigInt(historyStart.value) + BigInt(direction) * PAGE_SIZE
  historyStart.value = (next < 1n ? 1n : next).toString()
}
function pageFuture(direction: number) {
  const next = BigInt(futureStart.value) + BigInt(direction) * PAGE_SIZE
  futureStart.value = (next < BigInt(futureMinimum.value) ? BigInt(futureMinimum.value) : next).toString()
}
function jump() {
  if (!/^[1-9][0-9]*$/.test(jumpCycle.value) || BigInt(jumpCycle.value) > BigInt(props.group.count)) {
    jumpError.value = `Enter a cycle from 1 to ${props.group.count}.`
    return
  }
  jumpError.value = ''
  const cycle = BigInt(jumpCycle.value)
  if (cycle <= completedEnd.value) historyStart.value = cycle.toString()
  else if (cycle >= BigInt(futureMinimum.value)) futureStart.value = cycle.toString()
  if (cycle.toString() === currentCycle.value) expandedCycles.value[cycle.toString()] = true
}
function pageProcesses(cycle: string, direction: number) {
  processPages.value[cycle] = Math.max(0, (processPages.value[cycle] ?? 0) + direction)
  void loadCycle(cycle)
}
function revealPrompt(cycle: string) {
  opened.value = true
  if (BigInt(cycle) <= completedEnd.value) historyStart.value = cycle
  expandedCycles.value[cycle] = true
  void loadCycle(cycle)
}
</script>

<template>
  <section class="repeat-run-group" :class="{ current: currentCycle && active, 'has-errors': failedCount }">
    <button class="repeat-heading" type="button" :aria-expanded="opened" :aria-controls="`repeat-content-${group.id}`" @click="opened = !opened">
      <span class="chevron" aria-hidden="true">{{ opened ? '▾' : '▸' }}</span>
      <span class="repeat-title">{{ group.label || 'Repeat group' }}<small>Repeat {{ group.count }} times · {{ group.steps.length }} processes per cycle</small></span>
      <span class="group-state">{{ groupState }}</span>
    </button>
    <div class="group-progress" aria-live="polite">
      <strong v-if="currentCycle">Cycle {{ currentCycle }} of {{ group.count }}</strong>
      <span>{{ completedCount }} of {{ group.count }} cycles completed</span>
      <span v-if="failedCount" class="error-summary">{{ failedCount }} process {{ failedCount === 1 ? 'error' : 'errors' }}</span>
      <span v-if="inputCount" class="input-summary">{{ inputCount }} {{ inputCount === 1 ? 'reply' : 'replies' }} needed</span>
      <button v-for="cycle in promptCycles" :key="cycle" type="button" class="prompt-link" @click="revealPrompt(cycle)">Reply in cycle {{ cycle }}</button>
    </div>
    <p v-if="!opened && firstError" class="error-detail">{{ firstError }}</p>
    <div v-if="opened" :id="`repeat-content-${group.id}`" class="group-content">
      <div v-if="completedEnd > 0n" class="cycle-section-heading">
        <strong>Completed cycles</strong>
        <span class="pager">
          <button type="button" :disabled="historyStart === '1'" @click="pageHistory(-1)">Previous</button>
          <span>{{ historyStart }}–{{ historyCycles.at(-1) }}</span>
          <button type="button" :disabled="BigInt(historyStart) + PAGE_SIZE > completedEnd" @click="pageHistory(1)">Next</button>
        </span>
      </div>
      <template v-for="entry in displayedCycles()" :key="entry.cycle">
        <div v-if="entry.section === 'current'" class="cycle-section-heading"><strong>Current cycle</strong></div>
        <div v-if="entry.section === 'future' && entry.cycle === futureCycles[0]" class="cycle-section-heading">
          <strong>{{ stopped ? 'Cycles not executed' : 'Upcoming cycles' }}</strong>
          <span class="pager">
            <button type="button" :disabled="futureStart === futureMinimum" @click="pageFuture(-1)">Previous</button>
            <span>{{ futureStart }}–{{ futureCycles.at(-1) }}</span>
            <button type="button" :disabled="BigInt(futureStart) + PAGE_SIZE > BigInt(group.count)" @click="pageFuture(1)">Next</button>
          </span>
        </div>
        <div class="cycle-card" :class="{ 'current-cycle': entry.section === 'current', 'failed-cycle': cycleErrors(entry.cycle) }">
          <button type="button" class="cycle-heading" :aria-expanded="!!expandedCycles[entry.cycle]" :aria-controls="`cycle-content-${group.id}-${entry.cycle}`" @click="toggleCycle(entry.cycle)">
            <span aria-hidden="true">{{ expandedCycles[entry.cycle] ? '▾' : '▸' }}</span>
            <strong>Cycle {{ entry.cycle }} <span class="cycle-total">of {{ group.count }}</span></strong>
            <span>{{ cycleStatus(entry.cycle) }}</span>
            <span v-if="cycleErrors(entry.cycle)" class="error-summary">{{ cycleErrors(entry.cycle) }} errors</span>
          </button>
          <p v-if="!expandedCycles[entry.cycle] && cycleError(entry.cycle)" class="error-detail">{{ cycleError(entry.cycle) }}</p>
          <p v-if="!expandedCycles[entry.cycle] && cycleInputCount(entry.cycle)" class="input-summary collapsed-prompt">Operator reply needed. Open this cycle to respond.</p>
          <div v-if="expandedCycles[entry.cycle]" :id="`cycle-content-${group.id}-${entry.cycle}`" class="cycle-body" role="region" :aria-label="`Cycle ${entry.cycle} processes`">
            <p v-if="loading[entry.cycle]" class="preview-message" role="status">Loading cycle steps…</p>
            <p v-if="previewErrors[entry.cycle]" class="error-detail" role="alert">{{ previewErrors[entry.cycle] }} <button type="button" @click="loadCycle(entry.cycle)">Retry</button></p>
            <div class="process-grid">
              <ProcessExecutionCard v-for="card in cycleCards(entry.cycle)" :key="card.stepKey" :card="card" :now-seconds="nowSeconds" :drafts="drafts" :not-executed="stopped" @reply="(card, node) => emit('reply', card, node)" @draft="(key, value) => emit('draft', key, value)" />
            </div>
            <div v-if="group.steps.length > PROCESS_PAGE_SIZE" class="pager process-pager">
              <button type="button" :disabled="!processPages[entry.cycle]" @click="pageProcesses(entry.cycle, -1)">Previous processes</button>
              <span>Processes {{ (processPages[entry.cycle] ?? 0) * PROCESS_PAGE_SIZE + 1 }}–{{ Math.min(((processPages[entry.cycle] ?? 0) + 1) * PROCESS_PAGE_SIZE, group.steps.length) }} of {{ group.steps.length }}</span>
              <button type="button" :disabled="((processPages[entry.cycle] ?? 0) + 1) * PROCESS_PAGE_SIZE >= group.steps.length" @click="pageProcesses(entry.cycle, 1)">Next processes</button>
            </div>
          </div>
        </div>
      </template>
      <form v-if="BigInt(group.count) > PAGE_SIZE" class="cycle-jump" @submit.prevent="jump">
        <label :for="`cycle-jump-${group.id}`">Go to cycle</label>
        <input :id="`cycle-jump-${group.id}`" v-model="jumpCycle" inputmode="numeric" pattern="[0-9]+" placeholder="Cycle number">
        <button type="submit">Go</button>
        <span v-if="jumpError" class="error-summary" role="alert">{{ jumpError }}</span>
      </form>
    </div>
  </section>
</template>

<style scoped>
.repeat-run-group { min-width: 0; max-width: 100%; overflow-wrap: anywhere; border: 1px solid var(--color-border); border-left: 3px solid var(--color-primary); border-radius: var(--radius-md); overflow: hidden; background: var(--color-background-soft); }
.repeat-run-group.current { border-color: color-mix(in srgb, var(--color-primary) 55%, var(--color-border)); }
.repeat-heading, .cycle-heading { width: 100%; display: flex; align-items: center; text-align: left; gap: .65rem; border: 0; color: var(--color-heading); cursor: pointer; background: transparent; }
.repeat-heading { padding: 1rem 1.1rem .6rem; }
.repeat-title { flex: 1; min-width: 0; font-size: .95rem; font-weight: 700; overflow-wrap: anywhere; }
.repeat-title small { display: block; color: var(--color-text-muted); font-size: .76rem; font-weight: 500; margin-top: .25rem; }
.group-state { font-size: .72rem; font-weight: 700; color: var(--color-primary); }
.group-progress { display: flex; flex-wrap: wrap; gap: .4rem 1rem; padding: 0 1.1rem 1rem 2.35rem; font-size: .77rem; color: var(--color-text-muted); }
.group-progress strong { color: var(--color-primary); }
.group-content { border-top: 1px solid var(--color-border); padding: .8rem 1rem 1rem; }
.cycle-section-heading { display: flex; align-items: center; justify-content: space-between; gap: .7rem; padding: .7rem 0; font-size: .76rem; color: var(--color-text-muted); }
.cycle-card { margin-bottom: .55rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-background); }
.cycle-card.current-cycle { border-color: color-mix(in srgb, var(--color-primary) 40%, var(--color-border)); }
.cycle-heading { flex-wrap: wrap; padding: .75rem; font-size: .78rem; }
.cycle-heading strong { flex: 1; min-width: 0; }
.cycle-heading > span:last-child { font-size: .73rem; color: var(--color-text-muted); }
.cycle-total { font-weight: 400; color: var(--color-text-muted); }
.cycle-body { padding: 0 .75rem .75rem; }
.process-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(270px, 100%), 1fr)); gap: .75rem; }
.error-summary, .cycle-heading > .error-summary { color: var(--color-danger); font-weight: 650; }
.error-detail { margin: 0 .8rem .7rem; color: var(--color-danger); font-size: .76rem; overflow-wrap: anywhere; }
.input-summary { color: var(--color-warning); font-weight: 650; }
.prompt-link { padding: 0; border: 0; background: transparent; color: var(--color-primary); font: inherit; text-decoration: underline; cursor: pointer; }
.collapsed-prompt { margin: 0 .8rem .7rem; font-size: .76rem; }
.pager { display: inline-flex; min-width: 0; max-width: 100%; flex-wrap: wrap; align-items: center; gap: .45rem; font-size: .72rem; }
.pager > span { min-width: 0; overflow-wrap: anywhere; }
button:disabled { opacity: .4; cursor: not-allowed; }
.pager button, .cycle-jump button, .error-detail button { padding: .25rem .5rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); color: var(--color-heading); background: var(--color-background-soft); cursor: pointer; font-size: .73rem; }
.process-pager { display: flex; justify-content: space-between; margin-top: .7rem; }
.cycle-jump { display: flex; align-items: center; flex-wrap: wrap; gap: .5rem; margin-top: .9rem; font-size: .75rem; color: var(--color-text-muted); }
.cycle-jump input { min-width: 0; width: 10rem; padding: .35rem .5rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-background); color: var(--color-text); }
.preview-message { font-size: .76rem; color: var(--color-text-muted); }
@media (max-width: 600px) { .repeat-heading { align-items: flex-start; } .group-content { padding: .55rem; } .cycle-section-heading { flex-wrap: wrap; } .group-progress { padding-left: 1rem; } .process-pager { flex-wrap: wrap; } }
</style>
