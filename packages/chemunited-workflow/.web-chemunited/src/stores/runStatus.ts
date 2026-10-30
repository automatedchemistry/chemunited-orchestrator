import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

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
  displayName: string
  description: string
  status: 'waiting' | 'running' | 'completed' | 'failed'
  hasFailed: boolean
  errorMessage: string
  nodes: NodeCard[]
}

interface ActiveRunResponse {
  active_run_id: string | null
  state: string | null
  pending_inputs?: Record<string, string>
  protocol?: string | null
}

interface RunReport {
  run_id: string
  state: string
  reason?: string | null
  results?: Array<{
    process: string
    errors: Record<string, string>
  }>
}

export const useRunStatusStore = defineStore('runStatus', () => {
  // --- Global run state (shared with nav badge) ---
  const activeRunId = ref<string | null>(null)
  const runState = ref<RunState>('idle')
  // Why the run was stopped, when it ended 'cancelled' with a reason — a
  // safety interlock calling MonitoringContext.stop_run(reason), say.
  const stopReason = ref('')
  // A run stopped with a reason ends 'cancelled' like a plain cancel, but is
  // shown as an error: badges and dots take the 'failed' style.
  const stoppedWithReason = computed(
    () => runState.value === 'cancelled' && Boolean(stopReason.value),
  )
  const stateStyle = computed<RunState>(() =>
    stoppedWithReason.value ? 'failed' : runState.value,
  )
  const pendingInputs = ref<Record<string, string>>({})

  // --- Run control view state (persisted across navigation) ---
  const selectedProtocol = ref('')
  const processCards = ref<ProcessCard[]>([])
  const formTimeout = ref('')
  const formDryRun = ref(false)
  const formErrorResilient = ref(false)
  const formRecordMonitoring = ref(false)
  const formMessage = ref('')
  const formMessageType = ref<'' | 'error' | 'success' | 'info'>('')

  async function checkActiveRun() {
    try {
      const activeRes = await fetch('/run/active')
      if (activeRes.ok) {
        const data = await activeRes.json() as ActiveRunResponse
        if (data.active_run_id) {
          activeRunId.value = data.active_run_id
          runState.value = data.state === 'paused' ? 'paused' : 'running'
          stopReason.value = ''
          pendingInputs.value = data.pending_inputs ?? {}
          // Lets a viewer who didn't start the run rebuild the process/node
          // view from the same protocol, instead of relying on their own
          // dropdown selection.
          if (data.protocol) selectedProtocol.value = data.protocol
          return
        }
      }
      const reportRes = await fetch('/run/report')
      if (reportRes.status === 200) {
        const report = await reportRes.json() as RunReport | null
        if (report && report.state && report.state !== 'running') {
          activeRunId.value = report.run_id
          runState.value = report.state as RunState
          stopReason.value = report.reason ?? ''
          return
        }
      }
      activeRunId.value = null
      runState.value = 'idle'
      stopReason.value = ''
    } catch {
      // leave unchanged on network error
    }
  }

  async function restoreFromReport() {
    try {
      const res = await fetch('/run/report')
      if (res.status !== 200) return
      const report = await res.json() as RunReport | null
      if (!report?.results) return

      for (const result of report.results) {
        const card = processCards.value.find(c => c.stepKey === result.process)
        if (!card || card.status !== 'running') continue
        card.status = Object.keys(result.errors ?? {}).length > 0 ? 'failed' : 'completed'
      }
      applyStopReason()
    } catch { /* ignore */ }
  }

  // The node a stop interrupted fails with the executor's generic "Run was
  // cancelled." — on a run stopped with a reason, show the reason instead.
  function applyStopReason() {
    if (!stopReason.value) return
    for (const card of processCards.value) {
      if (card.status !== 'failed') continue
      if (!card.errorMessage || card.errorMessage.endsWith('Run was cancelled.')) {
        card.errorMessage = stopReason.value
      }
    }
  }

  function setRunState(state: RunState, id?: string | null, reason = '') {
    runState.value = state
    stopReason.value = reason
    if (id !== undefined) activeRunId.value = id
  }

  function setMessage(text: string, type: '' | 'error' | 'success' | 'info' = '') {
    formMessage.value = text
    formMessageType.value = type
  }

  return {
    // global
    activeRunId,
    runState,
    stopReason,
    stoppedWithReason,
    stateStyle,
    pendingInputs,
    checkActiveRun,
    setRunState,
    applyStopReason,
    // view state
    selectedProtocol,
    processCards,
    formTimeout,
    formDryRun,
    formErrorResilient,
    formRecordMonitoring,
    formMessage,
    formMessageType,
    restoreFromReport,
    setMessage,
  }
})
