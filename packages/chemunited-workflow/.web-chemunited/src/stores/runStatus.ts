import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ProcessStep } from '../lib/protocolPlan'
import { type AcceptedProtocolPlan, type OccurrenceMetadata, locateProtocolItems, occurrenceMetadata, operatorInputKey, processDisplayName } from '../lib/runPresentation'

export type RunState = 'idle' | 'running' | 'paused' | 'finished' | 'failed' | 'cancelled'
export interface NodeCard {
  nodeId: string
  iteration: number
  method: string
  state: 'WAITING' | 'RUNNING' | 'COMPLETED' | 'INACTIVE' | 'FAILED'
  percentage: number
  message: string
  waitSeconds: number | null
  waitStartedAt: number | null
  awaitingInput: boolean
  inputPrompt: string
}
export interface ProcessCard {
  stepKey: string
  sourceId: string
  occurrence: OccurrenceMetadata | null
  displayName: string
  description: string
  parameters: Record<string, unknown>
  status: 'waiting' | 'running' | 'completed' | 'failed'
  hasFailed: boolean
  interrupted: boolean
  errorMessage: string
  nodes: NodeCard[]
}
export function makeProcessCard(step: ProcessStep, key: string, description = '', occurrence: OccurrenceMetadata | null = null): ProcessCard {
  return { stepKey: key, sourceId: step.id, occurrence, displayName: processDisplayName(step.process), description, parameters: step.parameters, status: 'waiting', hasFailed: false, interrupted: false, errorMessage: '', nodes: [] }
}
interface RunSnapshot {
  run_id: string
  state: RunState
  reason?: string | null
  protocol?: string
  protocol_filename?: string
  protocol_plan?: AcceptedProtocolPlan | null
  current_occurrence?: unknown
  events?: Record<string, unknown>[]
  pending_inputs?: Record<string, string>
}

export const useRunStatusStore = defineStore('runStatus', () => {
  const activeRunId = ref<string | null>(null)
  const runState = ref<RunState>('idle')
  const stopReason = ref('')
  const stoppedWithReason = computed(() => runState.value === 'cancelled' && Boolean(stopReason.value))
  const stateStyle = computed<RunState>(() => stoppedWithReason.value ? 'failed' : runState.value)
  const pendingInputs = ref<Record<string, string>>({})
  const selectedProtocol = ref('')
  const processCards = ref<ProcessCard[]>([])
  const protocolPlan = ref<AcceptedProtocolPlan | null>(null)
  const currentOccurrence = ref<OccurrenceMetadata | null>(null)
  const descriptions = ref<Record<string, string>>({})
  const formMessage = ref('')
  const formMessageType = ref<'' | 'error' | 'success' | 'info'>('')
  const totalExecutions = computed(() => protocolPlan.value?.total_executions ?? '0')
  const locatedItems = computed(() => protocolPlan.value ? locateProtocolItems(protocolPlan.value) : [])

  function setPlan(plan: AcceptedProtocolPlan | null, reset = true) {
    protocolPlan.value = plan
    if (!reset) return
    processCards.value = []
    currentOccurrence.value = null
    pendingInputs.value = {}
    if (!plan) return
    for (const { item, offset } of locateProtocolItems(plan)) {
      if (item.type !== 'process') continue
      const key = plan.source_schema_version === 1 ? item.id : `${item.process}_${offset}`
      processCards.value.push(makeProcessCard(item, key, descriptions.value[item.process] ?? ''))
    }
  }

  function ensureOccurrence(key: string, metadata: OccurrenceMetadata | null): ProcessCard {
    let card = processCards.value.find(c => c.stepKey === key)
    if (!card && metadata && !metadata.group_id) card = processCards.value.find(c => c.sourceId === metadata.source_id && !c.occurrence?.group_id)
    if (!card) {
      const sequence = protocolPlan.value?.document.sequence ?? []
      const steps = sequence.flatMap(item => item.type === 'repeat' ? item.steps : [item])
      const step = steps.find(item => item.id === metadata?.source_id)
        ?? { type: 'process' as const, id: metadata?.source_id ?? key, process: metadata?.process_name || key.replace(/_\d+$/, ''), parameters: {} }
      card = makeProcessCard(step, key, descriptions.value[step.process] ?? '', metadata)
      processCards.value.push(card)
    }
    card.stepKey = key
    if (metadata) card.occurrence = metadata
    return card
  }

  function applyEvent(data: Record<string, unknown>) {
    const eventType = String(data.event_type ?? '')
    const metadata = occurrenceMetadata(data.occurrence)
    const key = metadata?.execution_key ?? (typeof data.process === 'string' ? data.process : null)
    if (!key) return
    const card = ensureOccurrence(key, metadata)
    if (eventType === 'EXECUTION_STARTED') {
      if (card.status === 'waiting') card.status = 'running'
      if (metadata && (!currentOccurrence.value || BigInt(metadata.execution_index) >= BigInt(currentOccurrence.value.execution_index))) currentOccurrence.value = metadata
    } else if (eventType === 'NODE_FAILED') {
      card.hasFailed = true
      if (typeof data.message === 'string' && data.message.includes('Run was cancelled.')) card.interrupted = true
      if (data.message && !card.errorMessage) card.errorMessage = String(data.message)
    } else if (eventType === 'EXECUTION_FINISHED') card.status = card.hasFailed ? 'failed' : 'completed'
    const nodeKey = data.node_key as [string, number] | null
    if (!nodeKey) return
    const [nodeId, iteration] = nodeKey
    let node = card.nodes.find(n => n.nodeId === nodeId)
    if (!node) {
      node = { nodeId, iteration, method: '', state: 'WAITING', percentage: 0, message: '', waitSeconds: null, waitStartedAt: null, awaitingInput: false, inputPrompt: '' }
      card.nodes.push(node)
    }
    // An INACTIVE-only sweep from a later internal loop must not erase a completed node.
    if (iteration < node.iteration || (iteration > node.iteration && data.state === 'INACTIVE')) return
    node.iteration = iteration
    if (data.state) node.state = data.state as NodeCard['state']
    if (data.method) node.method = String(data.method)
    if (typeof data.percentage === 'number') node.percentage = data.percentage
    if (typeof data.message === 'string') node.message = data.message
    node.waitSeconds = typeof data.wait_seconds === 'number' && data.wait_seconds > 0 ? data.wait_seconds : null
    node.waitStartedAt = node.waitSeconds === null ? null : typeof data.timestamp === 'number' ? data.timestamp : Date.now() / 1000
    node.awaitingInput = eventType === 'NODE_INPUT_REQUESTED'
    node.inputPrompt = node.awaitingInput && typeof data.message === 'string' ? data.message : ''
    const inputKey = operatorInputKey(card.stepKey, node.nodeId)
    if (node.awaitingInput) pendingInputs.value[inputKey] = node.inputPrompt
    else delete pendingInputs.value[inputKey]
  }

  function applyPendingInputs() {
    for (const [key, message] of Object.entries(pendingInputs.value)) {
      const separator = key.indexOf('::')
      const processKey = separator < 0 ? currentOccurrence.value?.execution_key : key.slice(0, separator)
      const nodeId = separator < 0 ? key : key.slice(separator + 2)
      if (!processKey) continue
      const card = ensureOccurrence(processKey, currentOccurrence.value?.execution_key === processKey ? currentOccurrence.value : null)
      let node = card.nodes.find(n => n.nodeId === nodeId)
      if (!node) {
        node = { nodeId, iteration: 0, method: '', state: 'RUNNING', percentage: 0, message, waitSeconds: null, waitStartedAt: null, awaitingInput: true, inputPrompt: message }
        card.nodes.push(node)
      }
      node.awaitingInput = true
      node.inputPrompt = message
    }
  }

  async function restoreRunSnapshot() {
    try {
      const res = await fetch('/run/status')
      if (!res.ok) return false
      const snapshot = await res.json() as RunSnapshot
      const changedRun = activeRunId.value !== snapshot.run_id
      if (snapshot.protocol_plan && (changedRun || !protocolPlan.value)) setPlan(snapshot.protocol_plan)
      else if (changedRun) setPlan(null)
      activeRunId.value = snapshot.run_id
      runState.value = snapshot.state
      stopReason.value = snapshot.reason ?? ''
      if (snapshot.protocol ?? snapshot.protocol_filename) selectedProtocol.value = snapshot.protocol ?? snapshot.protocol_filename ?? ''
      for (const event of snapshot.events ?? []) applyEvent(event)
      currentOccurrence.value = occurrenceMetadata(snapshot.current_occurrence) ?? currentOccurrence.value
      if (snapshot.pending_inputs) pendingInputs.value = snapshot.pending_inputs
      applyPendingInputs()
      markInterrupted(snapshot.state)
      applyStopReason()
      return true
    } catch { return false }
  }

  async function checkActiveRun() {
    if (await restoreRunSnapshot()) return
    try {
      const res = await fetch('/run/active')
      if (!res.ok) return
      const data = await res.json() as { active_run_id: string | null; state: RunState; protocol?: string; pending_inputs?: Record<string, string> }
      activeRunId.value = data.active_run_id
      runState.value = data.active_run_id ? data.state : 'idle'
      if (data.protocol) selectedProtocol.value = data.protocol
      pendingInputs.value = data.pending_inputs ?? {}
    } catch { /* Preserve the last known state while disconnected. */ }
  }

  async function restoreFromReport() { await restoreRunSnapshot() }
  function markInterrupted(state: RunState) {
    if (state !== 'cancelled') return
    for (const card of processCards.value) if (card.status === 'running') card.interrupted = true
  }
  function applyStopReason() {
    if (!stopReason.value) return
    for (const card of processCards.value) {
      if (card.status === 'failed' && (!card.errorMessage || card.errorMessage.endsWith('Run was cancelled.'))) card.errorMessage = stopReason.value
    }
  }
  function setRunState(state: RunState, id?: string | null, reason = '') {
    markInterrupted(state)
    runState.value = state
    stopReason.value = reason
    if (id !== undefined) activeRunId.value = id
  }
  function setMessage(text: string, type: '' | 'error' | 'success' | 'info' = '') { formMessage.value = text; formMessageType.value = type }

  return {
    activeRunId, runState, stopReason, stoppedWithReason, stateStyle, pendingInputs,
    selectedProtocol, processCards, protocolPlan, currentOccurrence, descriptions, totalExecutions, locatedItems,
    formMessage, formMessageType, checkActiveRun, setRunState, applyStopReason, restoreFromReport,
    restoreRunSnapshot, setMessage, setPlan, applyEvent, applyPendingInputs,
  }
})
