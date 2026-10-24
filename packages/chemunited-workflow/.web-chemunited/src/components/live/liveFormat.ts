import type { DeviceStatus, LiveCommand } from '../../composables/usePlatformLive'

// Where the desktop export says each live part sits (draw/platform-live.json,
// served at /project/platform-live), in the SVG's pixels.
export type Point = [number, number]
export type Box = [number, number, number, number]

export interface LivePart {
  figure: Box
  rotor?: { center: Point, slots: Point[] }
  badge?: { box: Box }
  lights?: { points: Point[], r: number }
}

export interface LiveDisplayPart {
  box: Box
  component: string
  command: string
  kwargs: Record<string, unknown>
}

export interface LiveMap {
  svg_sha256: string
  svg_matches: boolean
  parts: Record<string, LivePart>
  displays: Record<string, LiveDisplayPart>
}

const LEADING_NUMBER = /^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)(.*)$/s
// What may follow the number for the rest to count as its unit.
const UNIT_START = /^[\s\p{L}°%µ/]/u
const MAX_SIGNIFICANT = 4

function significantDigits(number: string): number {
  const mantissa = number.replace(/^[-+]/, '').split(/[eE]/)[0] ?? ''
  return Math.max(mantissa.replace('.', '').replace(/^0+/, '').length, 1)
}

// An LCD's value is text. If it starts with a number, the number is shown with
// at most four significant digits, followed by the rest as its unit:
// "24.3456 °C" → "24.35 °C". Anything else is shown as it is.
export function formatLcdValue(text: string): string {
  const match = LEADING_NUMBER.exec(text)
  const number = match?.[1] ?? ''
  const rest = match?.[2] ?? ''
  if (!match || !Number.isFinite(Number(number)) || (rest && !UNIT_START.test(rest))) {
    return text.trim()
  }
  const shown = significantDigits(number) > MAX_SIGNIFICANT
    ? Number(number).toPrecision(MAX_SIGNIFICANT)
    : number.replace(/^\+/, '')
  const unit = rest.trim()
  return unit ? `${shown} ${unit}` : shown
}

// Cut text to the characters that fit a width, at a font size (both in SVG units).
export function fitText(text: string, width: number, fontSize: number): string {
  const max = Math.max(3, Math.floor(width / (fontSize * 0.62)))
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

export function commandText(command: LiveCommand): string {
  const params = Object.entries(command.params ?? {})
    .map(([key, value]) => `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join(', ')
  return params ? `${command.name}(${params})` : command.name
}

export function statusLabel(status: DeviceStatus): string {
  return { running: 'Running', done: 'Done', failed: 'Failed', unknown: 'Unknown' }[status]
}

export function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleTimeString()
}

export function boxCenter(box: Box): Point {
  return [box[0] + box[2] / 2, box[1] + box[3] / 2]
}
