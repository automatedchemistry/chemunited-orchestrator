<script lang="ts">
interface CommandParameter {
  in: string
  required: boolean
  type: string | null
  default?: unknown
}

interface CommandMeta {
  name: string
  type: 'get' | 'put'
  parameters: Record<string, CommandParameter>
}

type DeviceCommand = CommandMeta

// Commands are keyed by name alone in `commands`/`commandInputs`/`sending`,
// but a path can expose both a `get` and a `put` command (e.g. `position`) —
// combine name and verb so those don't collide.
function commandKey(command: DeviceCommand): string {
  return `${command.type}_${command.name}`
}

// Module-level cache — persists across mount/unmount (no re-fetch on device revisit).
// Only successful discoveries are stored, so a failed fetch is retried on the next click.
let _commandsCache = new Map<string, DeviceCommand[]>()

export function clearDeviceCommandsCache(): void {
  _commandsCache = new Map()
}
</script>

<script setup lang="ts">
import { ref, watch } from 'vue'

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

type Reachability = 'online' | 'offline' | 'unknown'

interface ComponentStatus {
  component: string
  url: string
  online: boolean
  status_code: number | null
  latency_ms: number | null
  error: string | null
  reachability: Reachability | null
  reachability_supported: boolean | null
}

interface CommandResult {
  component: string
  command: string
  url: string
  ok: boolean
  status_code: number | null
  latency_ms: number | null
  response: unknown
  error: string | null
}

interface ErrorResponse {
  detail?: string | Array<{ msg?: string }>
}

async function responseError(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json() as ErrorResponse
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map(error => error.msg)
        .filter((value): value is string => Boolean(value))
      if (messages.length) return messages.join(', ')
    }
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail
  } catch {
    // Use the friendly fallback when the response is not JSON.
  }
  return fallback
}

const props = defineProps<{ device: PlatformDevice }>()
defineEmits<{ close: [] }>()

const loading = ref(false)
const notConnected = ref(false)
const error = ref('')
const status = ref<ComponentStatus | null>(null)

const commandsLoading = ref(false)
const commandsError = ref('')
const commands = ref<DeviceCommand[]>([])
const commandInputs = ref<Record<string, Record<string, string>>>({})
const sending = ref<string | null>(null)
const sendError = ref('')
const lastResult = ref<CommandResult | null>(null)

function statusClass(s: ComponentStatus): string {
  if (s.reachability) return s.reachability
  return s.online ? 'online' : 'offline'
}

function statusLabel(s: ComponentStatus): string {
  if (s.reachability === 'online') return 'Online'
  if (s.reachability === 'offline') return 'Offline'
  if (s.reachability === 'unknown') return 'Unknown'
  return s.online ? 'Online' : 'Offline'
}

function statusDetail(s: ComponentStatus): string {
  if (s.online) {
    const parts = []
    if (s.status_code !== null) parts.push(`HTTP ${s.status_code}`)
    if (s.latency_ms !== null) parts.push(`${s.latency_ms} ms`)
    return parts.join(' / ') || 'Reachable'
  }
  return s.error || 'Request failed'
}

async function loadStatus(device: PlatformDevice) {
  loading.value = true
  notConnected.value = false
  error.value = ''
  status.value = null

  if (device.is_electronic === false) {
    notConnected.value = true
    loading.value = false
    return
  }

  try {
    const response = await fetch(`/components/ping/${encodeURIComponent(device.id)}`)
    if (response.status === 404) {
      notConnected.value = true
      return
    }
    if (!response.ok) {
      error.value = 'Could not check connectivity.'
      return
    }
    status.value = await response.json() as ComponentStatus
  } catch {
    error.value = 'Could not check connectivity.'
  } finally {
    loading.value = false
  }
}

function applyCommands(list: DeviceCommand[]) {
  const inputs: Record<string, Record<string, string>> = {}
  for (const command of list) {
    const paramInputs: Record<string, string> = {}
    for (const [paramName, paramMeta] of Object.entries(command.parameters)) {
      if (paramMeta.default !== undefined) {
        paramInputs[paramName] = String(paramMeta.default)
      }
    }
    inputs[commandKey(command)] = paramInputs
  }
  commandInputs.value = inputs
  commands.value = list
}

async function loadCommands(device: PlatformDevice) {
  commandsError.value = ''
  sendError.value = ''
  lastResult.value = null

  if (device.is_electronic === false) {
    commands.value = []
    commandInputs.value = {}
    return
  }

  const cached = _commandsCache.get(device.id)
  if (cached) {
    applyCommands(cached)
    return
  }

  commandsLoading.value = true
  commands.value = []
  try {
    const response = await fetch(`/components/commands/${encodeURIComponent(device.id)}`)
    if (!response.ok) {
      commandsError.value = await responseError(response, 'Could not load commands.')
      return
    }
    const data = await response.json() as Record<string, CommandMeta>
    const list = Object.values(data)
    _commandsCache.set(device.id, list)
    applyCommands(list)
  } catch {
    commandsError.value = 'Could not reach the API.'
  } finally {
    commandsLoading.value = false
  }
}

async function sendCommand(command: DeviceCommand) {
  sending.value = commandKey(command)
  sendError.value = ''
  lastResult.value = null

  const inputs = commandInputs.value[commandKey(command)] ?? {}
  const params: Record<string, string> = {}
  let body: unknown = null

  for (const [paramName, paramMeta] of Object.entries(command.parameters)) {
    const raw = inputs[paramName]
    if (paramMeta.in === 'body') {
      if (raw && raw.trim()) {
        try {
          body = JSON.parse(raw)
        } catch {
          sendError.value = `Parameter "${paramName}" must be valid JSON.`
          sending.value = null
          return
        }
      }
    } else if (raw !== undefined && raw !== '') {
      params[paramName] = raw
    }
  }

  try {
    const response = await fetch(
      `/components/commands/${encodeURIComponent(props.device.id)}/${command.name}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ verb: command.type, params, body }),
      },
    )
    if (!response.ok) {
      sendError.value = await responseError(response, 'Command failed.')
      return
    }
    lastResult.value = await response.json() as CommandResult
  } catch {
    sendError.value = 'Could not reach the API.'
  } finally {
    sending.value = null
  }
}

watch(() => props.device, device => {
  void loadStatus(device)
  void loadCommands(device)
}, { immediate: true })
</script>

<template>
  <div class="device-panel">
    <div class="device-panel-header">
      <div>
        <p v-if="device.figure" class="device-panel-eyebrow">{{ device.figure }}</p>
        <h3 class="device-panel-title">{{ device.label }}</h3>
      </div>
      <button type="button" class="close-button" aria-label="Close" @click="$emit('close')">
        &times;
      </button>
    </div>

    <div class="device-panel-body">
      <p v-if="loading" class="muted">Checking connectivity…</p>
      <p v-else-if="notConnected" class="muted">No connectivity info for this component.</p>
      <p v-else-if="error" class="error-text">{{ error }}</p>
      <div v-else-if="status" class="status-stack">
        <span class="status-badge" :class="statusClass(status)">
          <span class="status-dot" aria-hidden="true"></span>
          {{ statusLabel(status) }}
        </span>
        <small>{{ statusDetail(status) }}</small>
      </div>

      <div v-if="!notConnected" class="commands-section">
        <p v-if="commandsLoading" class="muted">Loading commands…</p>
        <p v-else-if="commandsError" class="error-text">{{ commandsError }}</p>
        <p v-else-if="!commands.length" class="muted">No commands available.</p>
        <div v-else class="commands-stack">
          <div v-for="command in commands" :key="commandKey(command)" class="command-block">
            <div class="command-block-header">
              <span class="verb-badge" :class="command.type">{{ command.type.toUpperCase() }}</span>
              <span class="command-name">{{ command.name }}</span>
            </div>
            <div v-if="Object.keys(command.parameters).length" class="command-params">
              <label
                v-for="(paramMeta, paramName) in command.parameters"
                :key="paramName"
                class="param-field"
              >
                <span>{{ paramName }}<span v-if="paramMeta.required">*</span></span>
                <textarea
                  v-if="paramMeta.in === 'body'"
                  v-model="commandInputs[commandKey(command)]![paramName]"
                  rows="2"
                  placeholder="JSON body"
                />
                <input
                  v-else
                  type="text"
                  v-model="commandInputs[commandKey(command)]![paramName]"
                  :placeholder="paramMeta.default !== undefined ? String(paramMeta.default) : paramMeta.type ?? ''"
                />
              </label>
            </div>
            <button
              type="button"
              class="send-button"
              :disabled="sending === commandKey(command)"
              @click="sendCommand(command)"
            >
              {{ sending === commandKey(command) ? 'Sending…' : 'Send' }}
            </button>
          </div>
        </div>

        <div v-if="lastResult || sendError" class="feedback-box">
          <p v-if="sendError" class="error-text">{{ sendError }}</p>
          <template v-else-if="lastResult">
            <span class="status-badge" :class="lastResult.ok ? 'online' : 'offline'">
              <span class="status-dot" aria-hidden="true"></span>
              {{ lastResult.ok ? 'OK' : 'Error' }}
            </span>
            <small>
              {{ lastResult.command }} · HTTP {{ lastResult.status_code ?? '—' }}
              · {{ lastResult.latency_ms ?? '—' }} ms
              <template v-if="lastResult.error"> · {{ lastResult.error }}</template>
            </small>
            <pre>{{ JSON.stringify(lastResult.response, null, 2) }}</pre>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.device-panel {
  margin-top: 0.9rem;
  padding: 1rem 1.1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-background-mute);
}

.device-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.device-panel-eyebrow {
  margin: 0 0 0.15rem;
  color: var(--color-primary);
  font-size: 0.68rem;
  font-weight: 760;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.device-panel-title {
  margin: 0;
  color: var(--color-heading);
  font-size: 1rem;
  font-weight: 720;
}

.close-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: 50%;
  background: var(--color-background-soft);
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
}

.close-button:hover {
  color: var(--color-heading);
  border-color: var(--color-border-hover);
}

.device-panel-body {
  margin-top: 0.75rem;
}

.muted {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.85rem;
}

.error-text {
  margin: 0;
  color: var(--color-danger);
  font-size: 0.85rem;
}

.status-stack {
  display: inline-flex;
  flex-direction: column;
  gap: 0.28rem;
}

.status-stack small {
  color: var(--color-text-muted);
  font-size: 0.78rem;
}

.status-badge {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.28rem 0.55rem;
  border-radius: 999px;
  background: var(--color-background-mute);
  font-size: 0.78rem;
  font-weight: 760;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.status-badge.online {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.status-badge.offline {
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.status-badge.unknown {
  color: var(--color-text-muted);
  background: var(--color-background-mute);
}

.commands-section {
  margin-top: 1rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--color-border);
}

.commands-stack {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.command-block {
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-soft);
}

.command-block-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.4rem;
}

.command-name {
  font-size: 0.85rem;
  font-weight: 720;
  color: var(--color-heading);
}

.verb-badge {
  padding: 0.12rem 0.4rem;
  border-radius: 6px;
  font-size: 0.68rem;
  font-weight: 760;
  letter-spacing: 0.03em;
}

.verb-badge.get {
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.verb-badge.put {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.command-params {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-bottom: 0.5rem;
}

.param-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.param-field input,
.param-field textarea {
  font: inherit;
  font-size: 0.8rem;
  color: var(--color-text);
  padding: 0.32rem 0.45rem;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-background);
  resize: vertical;
}

.send-button {
  padding: 0.32rem 0.75rem;
  border: 1px solid var(--color-primary);
  border-radius: 999px;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: 0.78rem;
  font-weight: 760;
  cursor: pointer;
}

.send-button:hover:not(:disabled) {
  background: var(--color-primary);
  color: var(--color-background-soft);
}

.send-button:disabled {
  opacity: 0.6;
  cursor: default;
}

.feedback-box {
  margin-top: 0.7rem;
  padding: 0.7rem 0.8rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-mute);
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.feedback-box small {
  color: var(--color-text-muted);
  font-size: 0.75rem;
}

.feedback-box pre {
  margin: 0;
  padding: 0.5rem;
  border-radius: 6px;
  background: var(--color-background-soft);
  color: var(--color-text);
  font-size: 0.72rem;
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
