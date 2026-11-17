import type { ProtocolItem } from './protocolPlan'

/**
 * The server's advisory duration estimate for a protocol. Durations are whole
 * milliseconds as decimal strings, so huge repeat counts stay exact.
 */
export interface ProtocolEstimate {
  /** One execution of each source step, or null when it has no estimate. */
  step_ms: Record<string, string | null>
  total_ms: string
  unestimated_executions: string
  /** Why an estimate could not be evaluated, by source step ID. */
  errors?: Record<string, string>
}

export interface RemainingEstimate {
  ms: bigint
  /** Executions still to run (or running) that have no estimate. */
  unestimated: bigint
}

const SECOND = 1000n
const MINUTE = 60n * SECOND
const HOUR = 60n * MINUTE
const DAY = 24n * HOUR
const CENTURY = 36525n * DAY
// The latest instant a Date can represent.
const MAX_DATE_MS = 8_640_000_000_000_000

/** True when at least one step has an estimate: otherwise there is nothing to show. */
export function hasEstimate(estimate: ProtocolEstimate | null | undefined): estimate is ProtocolEstimate {
  return !!estimate && Object.values(estimate.step_ms ?? {}).some(value => value !== null)
}

/** `45 s`, `12 min`, `2 h 30 min`, `3 d 4 h`, or `> 100 years`, from BigInt milliseconds. */
export function formatDuration(ms: bigint): string {
  if (ms < 0n) ms = 0n
  if (ms >= CENTURY) return '> 100 years'
  if (ms < MINUTE) {
    // Round up, so a countdown only reads 0 s once it is over.
    const seconds = (ms + SECOND - 1n) / SECOND
    return seconds === 60n ? '1 min' : `${seconds} s`
  }
  const minutes = (ms + MINUTE / 2n) / MINUTE
  if (minutes < 60n) return `${minutes} min`
  const hours = minutes / 60n
  if (hours < 24n) return minutes % 60n ? `${hours} h ${minutes % 60n} min` : `${hours} h`
  const days = hours / 24n
  return hours % 24n ? `${days} d ${hours % 24n} h` : `${days} d`
}

/** An estimate as people read it: `≈ 2 h 30 min`, or `> 100 years`. */
export function formatEstimate(ms: bigint): string {
  const text = formatDuration(ms)
  return text.startsWith('>') ? text : `≈ ${text}`
}

/** `1 execution not estimated`, or '' when every execution has an estimate. */
export function unestimatedNote(count: bigint): string {
  if (count <= 0n) return ''
  return `${count.toLocaleString()} ${count === 1n ? 'execution' : 'executions'} not estimated`
}

/**
 * Time left in a protocol: every execution that has not started yet, plus
 * what is left of the current one. Works from the compact sequence with
 * BigInt offsets and never iterates repeat cycles.
 *
 * `current` is the execution in progress (null before the run starts),
 * `elapsedMs` how long it has run excluding pauses, and `currentDone` whether
 * it has already finished.
 */
export function remainingEstimate(
  sequence: readonly ProtocolItem[],
  estimate: ProtocolEstimate,
  current: { execution_index: string } | null,
  elapsedMs: number,
  currentDone = false,
): RemainingEstimate {
  const currentIndex = current ? BigInt(current.execution_index) : -1n
  const elapsed = BigInt(Math.max(0, Math.floor(Number.isFinite(elapsedMs) ? elapsedMs : 0)))
  let ms = 0n
  let unestimated = 0n
  const addUpcoming = (id: string, executions: bigint) => {
    if (executions <= 0n) return
    const value = estimate.step_ms[id]
    if (value == null) unestimated += executions
    else ms += BigInt(value) * executions
  }
  const addCurrent = (id: string) => {
    if (currentDone) return
    const value = estimate.step_ms[id]
    if (value == null) { unestimated += 1n; return }
    const left = BigInt(value) - elapsed
    if (left > 0n) ms += left
  }

  let offset = 0n
  for (const item of sequence) {
    if (item.type === 'process') {
      if (offset > currentIndex) addUpcoming(item.id, 1n)
      else if (offset === currentIndex) addCurrent(item.id)
      offset += 1n
      continue
    }
    const count = BigInt(item.count)
    const size = BigInt(item.steps.length)
    if (size === 0n) continue
    item.steps.forEach((step, position) => {
      // This step runs at first, first + size, … for count cycles.
      const first = offset + BigInt(position)
      if (currentIndex < first) { addUpcoming(step.id, count); return }
      const started = (currentIndex - first) / size + 1n
      if (started > count) return
      addUpcoming(step.id, count - started)
      if ((currentIndex - first) % size === 0n) addCurrent(step.id)
    })
    offset += count * size
  }
  return { ms, unestimated }
}

/** Clock time `remainingMs` from now: `14:35` today, `Tue 09:10` this week, else a date. */
export function formatEta(nowMs: number, remainingMs: bigint): string | null {
  if (remainingMs < 0n || remainingMs > BigInt(MAX_DATE_MS)) return null
  const finishMs = nowMs + Number(remainingMs)
  if (!Number.isFinite(finishMs) || Math.abs(finishMs) > MAX_DATE_MS) return null
  const finish = new Date(finishMs)
  const now = new Date(nowMs)
  const time = finish.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (finish.toDateString() === now.toDateString()) return time
  if (finishMs - nowMs < 6 * 86_400_000) return `${finish.toLocaleDateString([], { weekday: 'short' })} ${time}`
  return `${finish.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })} ${time}`
}
