// The monitoring registration (GET/PUT /monitoring/config) and state, shared
// by the Monitoring page and the config panel under Configurations.

export interface MonitoringVariable {
  component: string
  command: string
  kwargs: Record<string, unknown>
}

export interface MonitoringConfig {
  sample_time: number
  request_timeout: number
  variables: MonitoringVariable[]
}

export interface MonitoringState {
  manual_on: boolean
  run_active: boolean
  recording: boolean
  run_id: string | null
  effective_on: boolean
}

export const DEFAULT_CONFIG: MonitoringConfig = {
  sample_time: 5,
  request_timeout: 5,
  variables: [],
}

export const DEFAULT_STATE: MonitoringState = {
  manual_on: false,
  run_active: false,
  recording: false,
  run_id: null,
  effective_on: false,
}

export const STATE_POLL_INTERVAL_MS = 2000

export function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function normalizeConfig(input: Partial<MonitoringConfig>): MonitoringConfig {
  return {
    sample_time: Number(input.sample_time) > 0 ? Number(input.sample_time) : DEFAULT_CONFIG.sample_time,
    request_timeout: Number(input.request_timeout) > 0
      ? Number(input.request_timeout)
      : DEFAULT_CONFIG.request_timeout,
    variables: Array.isArray(input.variables)
      ? input.variables.map(variable => ({
        component: String(variable.component ?? ''),
        command: String(variable.command ?? ''),
        kwargs: isPlainRecord(variable.kwargs) ? variable.kwargs : {},
      })).filter(variable => variable.component && variable.command)
      : [],
  }
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical)
  if (isPlainRecord(value)) {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
  }
  return value
}

// Matches the work-server's monitoring_key: the parameters as JSON with sorted
// keys and no spaces, and nothing for a variable without parameters.
export function variableParams(variable: MonitoringVariable): string {
  return Object.keys(variable.kwargs).length ? JSON.stringify(canonical(variable.kwargs)) : ''
}

export function variableKey(variable: MonitoringVariable): string {
  const params = variableParams(variable)
  return `${variable.component}::${variable.command}${params ? `::${params}` : ''}`
}
