/** The saved protocol tree. Counts stay decimal strings across JSON boundaries. */
export interface ProcessStep {
  type: 'process'
  id: string
  process: string
  parameters: Record<string, unknown>
}

export interface RepeatGroup {
  type: 'repeat'
  id: string
  label: string
  count: string
  steps: ProcessStep[]
}

export type ProtocolItem = ProcessStep | RepeatGroup

export interface ProtocolDocument {
  schema_version: 2
  main_parameter: Record<string, unknown>
  sequence: ProtocolItem[]
}

export interface ProtocolOccurrence {
  execution_key: string
  source_id: string
  process: string
  process_index: string
  execution_index: string
  group_id: string | null
  label: string | null
  cycle: string | null
  count: string | null
  parameters: Record<string, unknown>
  main_parameters: Record<string, unknown>
}

export interface ProtocolPreview {
  document: ProtocolDocument
  total_executions: string
  offset: string
  limit: number
  next_offset: string | null
  occurrences: ProtocolOccurrence[]
}

export function emptyProtocol(): ProtocolDocument {
  return { schema_version: 2, main_parameter: {}, sequence: [] }
}

export function copyJson<T>(value: T): T {
  // JSON values can also be reactive Vue proxies, which structuredClone rejects.
  return JSON.parse(JSON.stringify(value)) as T
}

function record(value: unknown, field: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${field}: expected an object`)
  }
  return value as Record<string, unknown>
}

function identifier(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${field}: expected a nonempty string`)
  return value
}

/** For editable input: normalize leading zeros without rounding the count. */
export function canonicalRepeatCount(value: string): string | null {
  if (!/^\d+$/.test(value.trim())) return null
  const count = BigInt(value.trim())
  return count > 1n ? count.toString() : null
}

/** Load either format, preserving insertion order and stable v2 source IDs. */
export function normalizeProtocol(raw: unknown): ProtocolDocument {
  const source = record(raw, 'Protocol')
  const main = copyJson(record(source.main_parameter ?? {}, 'Main parameters'))
  if (!('schema_version' in source)) {
    const sequence: ProcessStep[] = []
    for (const [key, values] of Object.entries(source)) {
      if (key === 'main_parameter') continue
      const match = key.match(/^(.+)_\d+$/)
      if (!match?.[1]) throw new Error(`${key}: expected a process key ending in _<index>`)
      sequence.push({ type: 'process', id: key, process: match[1], parameters: copyJson(record(values, key)) })
    }
    return { schema_version: 2, main_parameter: main, sequence }
  }
  if (source.schema_version !== 2) throw new Error(`Unsupported protocol schema version: ${String(source.schema_version)}`)
  if (!Array.isArray(source.sequence)) throw new Error('Protocol sequence: expected a list')
  const ids = new Set<string>()
  const readId = (item: Record<string, unknown>): string => {
    const id = identifier(item.id, 'Source ID')
    if (ids.has(id)) throw new Error(`${id}: duplicate source ID`)
    ids.add(id)
    return id
  }
  const readProcess = (value: unknown): ProcessStep => {
    const item = record(value, 'Process step')
    if (item.type !== 'process') throw new Error(`${String(item.id ?? 'Group')}: nested repeat groups are not supported`)
    return {
      type: 'process', id: readId(item), process: identifier(item.process, 'Process name'),
      parameters: copyJson(record(item.parameters ?? {}, `${String(item.id)} / parameters`)),
    }
  }
  const sequence = source.sequence.map((value): ProtocolItem => {
    const item = record(value, 'Sequence item')
    if (item.type === 'process') return readProcess(item)
    if (item.type !== 'repeat') throw new Error(`${String(item.id ?? 'Sequence item')}: unsupported item type`)
    const id = readId(item)
    if (typeof item.count !== 'string' || !/^[1-9]\d*$/.test(item.count) || canonicalRepeatCount(item.count) !== item.count) {
      throw new Error(`${id} / count: expected a decimal integer greater than 1`)
    }
    if (!Array.isArray(item.steps) || !item.steps.length) throw new Error(`${id}: repeat group must contain at least one process`)
    return { type: 'repeat', id, label: typeof item.label === 'string' ? item.label : 'Repeat group', count: item.count, steps: item.steps.map(readProcess) }
  })
  return { schema_version: 2, main_parameter: main, sequence }
}

export function sourceItems(document: ProtocolDocument): ProtocolItem[] {
  return document.sequence.flatMap(item => item.type === 'repeat' ? [item, ...item.steps] : [item])
}

export function newSourceId(document: ProtocolDocument, prefix = 'step'): string {
  const existing = new Set(sourceItems(document).map(item => item.id))
  let id: string
  do {
    const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
    id = `${prefix}-${random}`
  } while (existing.has(id))
  return id
}

export function locateItem(document: ProtocolDocument, id: string | null) {
  for (const [index, item] of document.sequence.entries()) {
    if (item.id === id) return { item, parent: null, siblings: document.sequence, index }
    if (item.type === 'repeat') {
      const childIndex = item.steps.findIndex(child => child.id === id)
      const child = item.steps[childIndex]
      if (child) return { item: child, parent: item, siblings: item.steps as ProtocolItem[], index: childIndex }
    }
  }
  return null
}

/** Consecutive top-level processes only: grouping children would introduce nesting. */
export function canGroupItems(document: ProtocolDocument, ids: ReadonlySet<string>): boolean {
  if (!ids.size) return false
  const indices = document.sequence.flatMap((item, index) => ids.has(item.id) && item.type === 'process' ? [index] : [])
  return indices.length === ids.size && indices.every((index, offset) => index === indices[0]! + offset)
}

export function groupItems(document: ProtocolDocument, ids: ReadonlySet<string>): RepeatGroup | null {
  if (!canGroupItems(document, ids)) return null
  const first = document.sequence.findIndex(item => ids.has(item.id))
  const steps = document.sequence.slice(first, first + ids.size) as ProcessStep[]
  const group: RepeatGroup = { type: 'repeat', id: newSourceId(document, 'repeat'), label: 'Repeat group', count: '2', steps }
  document.sequence.splice(first, steps.length, group)
  return group
}

export function ungroupItem(document: ProtocolDocument, id: string): boolean {
  const index = document.sequence.findIndex(item => item.id === id)
  const group = document.sequence[index]
  if (group?.type !== 'repeat') return false
  document.sequence.splice(index, 1, ...group.steps)
  return true
}

export function moveItem(document: ProtocolDocument, id: string, delta: -1 | 1): boolean {
  const location = locateItem(document, id)
  if (!location) return false
  const next = location.index + delta
  const other = location.siblings[next]
  if (!other) return false
  location.siblings[next] = location.item
  location.siblings[location.index] = other
  return true
}

export function duplicateItem(document: ProtocolDocument, id: string): ProtocolItem | null {
  const location = locateItem(document, id)
  if (!location) return null
  const duplicate = copyJson(location.item)
  duplicate.id = newSourceId(document, duplicate.type === 'repeat' ? 'repeat' : 'step')
  if (duplicate.type === 'repeat') {
    // Reserve each new ID before generating the next one, including fallback IDs.
    const reserved = { ...document, sequence: [...document.sequence, duplicate] }
    duplicate.steps.forEach(step => { step.id = newSourceId(reserved) })
  }
  location.siblings.splice(location.index + 1, 0, duplicate)
  return duplicate
}

export function removeItem(document: ProtocolDocument, id: string): boolean {
  const location = locateItem(document, id)
  if (!location || (location.parent && location.siblings.length === 1)) return false
  location.siblings.splice(location.index, 1)
  return true
}

export function protocolErrors(document: ProtocolDocument): Record<string, string> {
  const errors: Record<string, string> = {}
  for (const item of document.sequence) {
    if (item.type !== 'repeat') continue
    if (!canonicalRepeatCount(item.count)) errors[item.id] = 'Enter a whole repeat count greater than 1.'
    else if (!item.steps.length) errors[item.id] = 'A repeat group needs at least one process.'
  }
  return errors
}

export function canonicalDocument(document: ProtocolDocument): ProtocolDocument {
  const normalized = copyJson(document)
  for (const item of normalized.sequence) {
    if (item.type !== 'repeat') continue
    const count = canonicalRepeatCount(item.count)
    if (!count) throw new Error(`${item.label || item.id} / count: enter a whole number greater than 1`)
    item.count = count
  }
  return normalizeProtocol(normalized)
}

export function itemExecutions(item: ProtocolItem): bigint {
  if (item.type === 'process') return 1n
  const count = canonicalRepeatCount(item.count)
  return count ? BigInt(count) * BigInt(item.steps.length) : 0n
}

export function totalExecutions(document: ProtocolDocument): bigint {
  return document.sequence.reduce((total, item) => total + itemExecutions(item), 0n)
}

export function groupOffset(document: ProtocolDocument, groupId: string): bigint {
  let offset = 0n
  for (const item of document.sequence) {
    if (item.id === groupId) return offset
    offset += itemExecutions(item)
  }
  throw new Error('Repeat group is no longer in the protocol')
}
