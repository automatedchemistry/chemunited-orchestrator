import type { ProtocolDocument, ProtocolItem } from './protocolPlan'

export interface OccurrenceMetadata {
  execution_key: string
  source_id: string
  process_name: string
  execution_index: string
  group_id: string | null
  group_label: string | null
  cycle: string | null
  count: string | null
}

export interface AcceptedProtocolPlan {
  document: ProtocolDocument
  resolved_document?: ProtocolDocument
  source_document?: Record<string, unknown>
  source_schema_version?: number
  total_executions: string
}

export interface LocatedProtocolItem { item: ProtocolItem; offset: string }

export function locateProtocolItems(plan: AcceptedProtocolPlan): LocatedProtocolItem[] {
  let offset = 0n
  return plan.document.sequence.map(item => {
    const located = { item, offset: offset.toString() }
    offset += item.type === 'repeat' ? BigInt(item.count) * BigInt(item.steps.length) : 1n
    return located
  })
}

export function occurrenceMetadata(raw: unknown): OccurrenceMetadata | null {
  if (!raw || typeof raw !== 'object') return null
  const value = raw as Record<string, unknown>
  if (typeof value.execution_key !== 'string' || typeof value.source_id !== 'string') return null
  return {
    execution_key: value.execution_key, source_id: value.source_id,
    process_name: String(value.process_name ?? value.process ?? ''),
    execution_index: String(value.execution_index ?? '0'),
    group_id: typeof value.group_id === 'string' ? value.group_id : null,
    group_label: typeof (value.group_label ?? value.label) === 'string' ? String(value.group_label ?? value.label) : null,
    cycle: value.cycle == null ? null : String(value.cycle), count: value.count == null ? null : String(value.count),
  }
}

// Allocate only the requested page, even beyond Number.MAX_SAFE_INTEGER.
export function cyclePage(first: string, last: string, size = 4): string[] {
  const result: string[] = []
  const end = BigInt(last)
  for (let value = BigInt(first); value <= end && result.length < size; value++) result.push(value.toString())
  return result
}

export function operatorInputKey(executionKey: string, nodeId: string): string { return `${executionKey}::${nodeId}` }
export function processDisplayName(name: string): string { return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) }
export function protocolFileExists(filename: string, protocols: readonly { filename: string }[]): boolean {
  return Boolean(filename) && protocols.some(protocol => protocol.filename === filename)
}
