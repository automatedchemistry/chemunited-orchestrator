<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  canonicalDocument, groupOffset, type ProtocolDocument, type ProtocolOccurrence, type ProtocolPreview,
} from '../lib/protocolPlan'

const props = defineProps<{ document: ProtocolDocument, groupId: string, selectedId: string | null }>()
defineEmits<{ select: [id: string] }>()

const PAGE_SIZE = 20
const offset = ref(0n)
const occurrences = ref<ProtocolOccurrence[]>([])
const loading = ref(false)
const error = ref('')
const jumpInput = ref('1')
let requestId = 0
let controller: AbortController | null = null
let refreshTimer: ReturnType<typeof setTimeout> | null = null
let disposed = false

const group = computed(() => props.document.sequence.find(item => item.id === props.groupId && item.type === 'repeat'))
const groupTotal = computed(() => group.value?.type === 'repeat' && /^\d+$/.test(group.value.count)
  ? BigInt(group.value.count) * BigInt(group.value.steps.length) : 0n)
const hasNext = computed(() => offset.value + BigInt(PAGE_SIZE) < groupTotal.value)
const cycles = computed(() => {
  const groups: Array<{ number: string, steps: ProtocolOccurrence[] }> = []
  for (const occurrence of occurrences.value) {
    const number = occurrence.cycle ?? '1'
    let current = groups[groups.length - 1]
    if (!current || current.number !== number) {
      current = { number, steps: [] }
      groups.push(current)
    }
    current.steps.push(occurrence)
  }
  return groups
})
const pageEnd = computed(() => offset.value + BigInt(occurrences.value.length))

function exact(value: string | bigint): string { return BigInt(value).toLocaleString() }

async function loadPage() {
  const request = ++requestId
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  error.value = ''
  occurrences.value = []
  try {
    const data = canonicalDocument(props.document)
    if (offset.value >= groupTotal.value) offset.value = 0n
    const start = groupOffset(data, props.groupId) + offset.value
    const response = await fetch('/protocols/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({ data, offset: start.toString(), limit: PAGE_SIZE }),
    })
    if (!response.ok) {
      const body = await response.json() as { detail?: unknown }
      throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? `HTTP ${response.status}`))
    }
    const result = await response.json() as ProtocolPreview
    if (disposed || request !== requestId) return
    occurrences.value = result.occurrences.filter(item => item.group_id === props.groupId)
  } catch (cause) {
    if (!disposed && request === requestId && !(cause instanceof DOMException && cause.name === 'AbortError')) {
      error.value = cause instanceof Error ? cause.message : String(cause)
    }
  } finally {
    if (!disposed && request === requestId) loading.value = false
  }
}

function page(next: bigint) {
  offset.value = next < 0n ? 0n : next
  void loadPage()
}

function jumpToCycle() {
  const text = jumpInput.value.trim()
  const current = group.value
  if (current?.type !== 'repeat' || !/^\d+$/.test(text) || BigInt(text) < 1n || BigInt(text) > BigInt(current.count)) {
    error.value = 'Enter a cycle number within this repeat group.'
    return
  }
  page((BigInt(text) - 1n) * BigInt(current.steps.length))
}

watch(() => [props.document, props.groupId], () => {
  ++requestId
  controller?.abort()
  occurrences.value = []
  loading.value = true
  if (refreshTimer) clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => { void loadPage() }, 180)
}, { deep: true, immediate: true })

onBeforeUnmount(() => {
  disposed = true
  ++requestId
  controller?.abort()
  if (refreshTimer) clearTimeout(refreshTimer)
})
</script>

<template>
  <div class="cycle-preview" aria-label="Cycle execution preview" :aria-busy="loading">
    <p class="preview-note">Display only. Selecting a step opens its shared parameters for every cycle.</p>
    <p v-if="loading" class="preview-note" role="status">Loading cycle preview…</p>
    <p v-if="error" class="preview-error" role="alert">{{ error }}</p>
    <details v-for="cycle in cycles" :key="cycle.number" open class="cycle-group">
      <summary>Cycle {{ exact(cycle.number) }} <span v-if="group?.type === 'repeat'">of {{ exact(group.count) }}</span></summary>
      <button
        v-for="occurrence in cycle.steps" :key="occurrence.execution_key" type="button"
        class="preview-step" :class="{ selected: occurrence.source_id === selectedId }"
        :aria-pressed="occurrence.source_id === selectedId" @click="$emit('select', occurrence.source_id)"
      >
        <span class="execution-index" :title="exact(BigInt(occurrence.execution_index) + 1n)">{{ exact(BigInt(occurrence.execution_index) + 1n) }}</span>
        <span>{{ occurrence.process }}</span>
      </button>
    </details>
    <div class="preview-pagination">
      <span v-if="occurrences.length">Executions {{ exact(offset + 1n) }}–{{ exact(pageEnd) }} of {{ exact(groupTotal) }} in this group</span>
      <div class="page-buttons">
        <button type="button" class="cu-button" :disabled="loading || offset === 0n" @click="page(0n)">First</button>
        <button type="button" class="cu-button" :disabled="loading || offset === 0n" @click="page(offset - BigInt(PAGE_SIZE))">Previous</button>
        <button type="button" class="cu-button" :disabled="loading || !hasNext" @click="page(offset + BigInt(PAGE_SIZE))">Next</button>
        <button type="button" class="cu-button" :disabled="loading || !hasNext" @click="page(((groupTotal - 1n) / BigInt(PAGE_SIZE)) * BigInt(PAGE_SIZE))">Last</button>
      </div>
      <form class="jump-form" @submit.prevent="jumpToCycle">
        <label :for="`cycle-jump-${groupId}`">Go to cycle</label>
        <input :id="`cycle-jump-${groupId}`" v-model="jumpInput" type="text" inputmode="numeric" class="cu-input" :disabled="loading">
        <button type="submit" class="cu-button" :disabled="loading">Go</button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.cycle-preview { min-width: 0; }
.preview-note { margin: 0 0 0.8rem; color: var(--color-text-muted); font-size: 0.76rem; }
.preview-error { color: var(--color-danger); overflow-wrap: anywhere; font-size: 0.8rem; }
.cycle-group { margin: 0.5rem 0; padding: 0.45rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-background-soft); }
.cycle-group summary { cursor: pointer; color: var(--color-heading); font-size: 0.8rem; font-weight: 700; overflow-wrap: anywhere; }
.cycle-group summary span { color: var(--color-text-muted); font-weight: 450; }
.preview-step { display: flex; align-items: center; gap: 0.65rem; width: 100%; min-width: 0; padding: 0.6rem 0.4rem; margin-top: 0.3rem; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--color-heading); font-size: 0.78rem; text-align: left; cursor: pointer; overflow-wrap: anywhere; }
.preview-step:hover { background: var(--color-background-mute); }
.preview-step.selected { border-color: var(--color-primary); background: var(--color-primary-soft); }
.execution-index { max-width: 4rem; overflow: hidden; text-overflow: ellipsis; color: var(--color-text-muted); font-size: 0.65rem; }
.preview-pagination { display: grid; gap: 0.65rem; margin: 0.8rem 0 0.2rem; font-size: 0.71rem; color: var(--color-text-muted); overflow-wrap: anywhere; }
.page-buttons, .jump-form { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; }
.page-buttons .cu-button, .jump-form .cu-button { min-height: 30px; padding: 0.3rem 0.5rem; font-size: 0.7rem; }
.jump-form .cu-input { width: 7rem; }
</style>
