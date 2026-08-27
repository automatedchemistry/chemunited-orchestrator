import { defineStore } from 'pinia'
import { ref } from 'vue'

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
}

interface RunReport {
  run_id: string
  state: string
  results?: Array<{
    process: string
    errors: Record<string, string>
  }>
}

export const useRunStatusStore = defineStore('runStatus', () => {
  // --- Global run state (shared with nav badge) ---
  const activeRunId = ref<string | null>(null)
  const runState = ref<RunState>('idle')
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
          pendingInputs.value = data.pending_inputs ?? {}
          return
        }
      }
      const reportRes = await fetch('/run/report')
      if (reportRes.status === 200) {
        const report = await reportRes.json() as RunReport | null
        if (report && report.state && report.state !== 'running') {
          activeRunId.value = report.run_id
          runState.value = report.state as RunState
          return
        }
      }
      activeRunId.value = null
      runState.value = 'idle'
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
    } catch { /* ignore */ }
  }

  function setRunState(state: RunState, id?: string | null) {
    runState.value = state
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
    pendingInputs,
    checkActiveRun,
    setRunState,
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
