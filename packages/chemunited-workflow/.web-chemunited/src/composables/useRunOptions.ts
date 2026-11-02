import { effectScope, reactive, watch } from 'vue'
import { customization } from '../extensions/manifest'

export interface RunOptions {
  /** Command timeout as typed, e.g. '5 s'; blank waits indefinitely. */
  timeout: string
  dryRun: boolean
  errorResilient: boolean
  recordMonitoring: boolean
}

const STORAGE_KEY = 'chemunited-run-options'

// RunDefaults from the project's customizations/ui/ui_hook.py; all off without one.
function projectDefaults(): RunOptions {
  const defaults = customization.manifest.run_defaults
  return {
    timeout: defaults.command_timeout,
    dryRun: defaults.dry_run,
    errorResilient: defaults.error_resilient,
    recordMonitoring: defaults.record_monitoring,
  }
}

function load(defaults: RunOptions): RunOptions {
  const options = { ...defaults }
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Record<string, unknown>
    if (typeof saved.timeout === 'string') options.timeout = saved.timeout
    if (typeof saved.dryRun === 'boolean') options.dryRun = saved.dryRun
    if (typeof saved.errorResilient === 'boolean') options.errorResilient = saved.errorResilient
    if (typeof saved.recordMonitoring === 'boolean') options.recordMonitoring = saved.recordMonitoring
  } catch {
    // Unreadable or blocked storage: start from the defaults.
  }
  return options
}

// Only the options this browser changed, so the others keep following the
// project's defaults.
function save(options: RunOptions, defaults: RunOptions) {
  const changed = Object.fromEntries(
    (Object.keys(defaults) as (keyof RunOptions)[])
      .filter(key => options[key] !== defaults[key])
      .map(key => [key, options[key]]),
  )
  try {
    if (Object.keys(changed).length) localStorage.setItem(STORAGE_KEY, JSON.stringify(changed))
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Not remembered, but still used for this visit.
  }
}

let options: RunOptions | null = null

/**
 * The options the next run starts with: set under Configurations → Run
 * control, shown as chips on Run Control, and remembered in this browser.
 * Built on first use, once start-up has loaded the project's defaults.
 */
export function useRunOptions(): RunOptions {
  if (!options) {
    const defaults = projectDefaults()
    const loaded = reactive(load(defaults))
    // Detached, so saving outlives the component that asked first.
    effectScope(true).run(() => {
      watch(loaded, value => save(value, defaults), { deep: true })
    })
    options = loaded
  }
  return options
}
