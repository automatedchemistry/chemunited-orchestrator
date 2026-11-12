import assert from 'node:assert/strict'
import {
  canGroupItems, canonicalDocument, canonicalRepeatCount, copyJson, duplicateItem,
  groupItems, groupOffset, locateItem, moveItem, normalizeProtocol, protocolErrors,
  removeItem, sourceItems, totalExecutions, ungroupItem,
} from '../src/lib/protocolPlan.ts'

const legacy = {
  main_parameter: { volume: '2 ml', nested: { preserve: true } },
  start_process_9: { outside: true },
  wash_3: { volume: '1 ml' },
  coupling_process_12: { chemistry: 'phosphate', values: { vessel: 2 } },
  finish_0: { outside: true },
}
const document = normalizeProtocol(legacy)
assert.deepEqual(document.sequence.map(item => item.id), Object.keys(legacy).slice(1))
assert.deepEqual(document.sequence.map(item => item.process), ['start_process', 'wash', 'coupling_process', 'finish'])
assert.deepEqual(document.main_parameter, legacy.main_parameter)
document.main_parameter.nested.preserve = false
assert.equal(legacy.main_parameter.nested.preserve, true, 'loading must not share mutable parameter dictionaries')

assert.equal(canGroupItems(document, new Set(['wash_3', 'finish_0'])), false, 'gaps cannot be silently grouped')
const originalBody = document.sequence.slice(1, 3)
const group = groupItems(document, new Set(originalBody.map(item => item.id)))
assert.ok(group)
assert.equal(group.count, '2')
assert.deepEqual(group.steps, originalBody)
assert.equal(totalExecutions(document), 6n)
assert.equal(groupItems(document, new Set(group.steps.map(item => item.id))), null, 'grouping children would create unsupported nesting')

const groupId = group.id
assert.equal(moveItem(document, groupId, 1), true)
assert.equal(document.sequence[2].id, groupId)
assert.deepEqual(group.steps.map(item => item.id), ['wash_3', 'coupling_process_12'])
assert.equal(moveItem(document, 'coupling_process_12', -1), true)
assert.deepEqual(group.steps.map(item => item.id), ['coupling_process_12', 'wash_3'])
assert.equal(locateItem(document, 'coupling_process_12').parent.id, groupId)
assert.equal(moveItem(document, 'coupling_process_12', -1), false, 'child moves stay within their parent')

group.count = '100000000000000000000000000000000000001'
assert.equal(totalExecutions(document), BigInt(group.count) * 2n + 2n)
assert.equal(groupOffset(document, groupId), 2n)
const beforePreview = copyJson(document)
groupOffset(document, groupId)
totalExecutions(document)
assert.deepEqual(document, beforePreview, 'display calculations never mutate the saved structure')

const duplicate = duplicateItem(document, groupId)
assert.equal(duplicate.type, 'repeat')
const allIds = sourceItems(document).map(item => item.id)
assert.equal(allIds.length, new Set(allIds).size, 'duplicated groups and their children need fresh globally unique IDs')
assert.deepEqual(duplicate.steps.map(step => step.process), group.steps.map(step => step.process))
duplicate.steps[0].parameters.values.vessel = 6
assert.equal(group.steps[0].parameters.values.vessel, 2, 'a duplicate must not alias the original parameters')

const retainedIds = group.steps.map(item => item.id)
assert.equal(ungroupItem(document, groupId), true)
assert.ok(retainedIds.every(id => document.sequence.some(item => item.id === id)), 'ungroup retains body IDs once')
assert.equal(sourceItems(document).filter(item => retainedIds.includes(item.id)).length, retainedIds.length)
assert.equal(locateItem(document, retainedIds[0]).parent, null)

const remainingGroup = duplicate
assert.equal(removeItem(document, remainingGroup.steps[0].id), true)
assert.equal(removeItem(document, remainingGroup.steps[0].id), false, 'an empty repeat body cannot be created')
remainingGroup.count = '00011'
assert.deepEqual(protocolErrors(document), {})
const saved = canonicalDocument(document)
assert.equal(saved.sequence.find(item => item.id === remainingGroup.id).count, '11')
assert.equal(remainingGroup.count, '00011', 'save normalization must not modify the in-progress editor draft')
assert.deepEqual(normalizeProtocol(JSON.parse(JSON.stringify(saved))), saved, 'saving and reopening preserve all stable IDs and shared values')

for (const value of ['2', '11', '1000', '9007199254740993', '1' + '0'.repeat(100)]) {
  assert.equal(canonicalRepeatCount(value), value)
}
for (const value of ['', '1', '0', '-2', '2.5', '2e3', '+3', 'Infinity', '２']) {
  assert.equal(canonicalRepeatCount(value), null)
}
assert.equal(canonicalRepeatCount('0002'), '2')
assert.throws(() => normalizeProtocol({ ...saved, schema_version: 3 }), /Unsupported/)
assert.throws(() => normalizeProtocol({ main_parameter: {}, malformed: {} }), /process key/)
assert.throws(() => normalizeProtocol({ ...saved, sequence: [saved.sequence[0], saved.sequence[0]] }), /duplicate/)
assert.throws(() => normalizeProtocol({ ...saved, sequence: [{ type: 'repeat', id: 'outer', count: '2', steps: [{ type: 'repeat', id: 'inner', count: '2', steps: [] }] }] }), /nested/)
for (const count of ['1', '0', '0002', '2e3', 3, true, null]) {
  assert.throws(() => normalizeProtocol({ ...saved, sequence: [{ type: 'repeat', id: 'invalid', count, steps: [{ type: 'process', id: 'body', process: 'wash', parameters: {} }] }] }), /count/)
}
console.log('Protocol editor checks passed: legacy/v2 round trips, exact huge counts, sibling grouping, stable IDs through moves/ungroup, fresh duplicate IDs, independent values and invalid-structure rejection.')
