import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const { createPinia, setActivePinia } = require('pinia')
const { createSSRApp } = require('vue')
const { renderToString } = require('@vue/server-renderer')
const { parse, compileScript } = require('@vue/compiler-sfc')
const root = path.resolve(import.meta.dirname, '..')
const cache = new Map()
function loadTs(filename) {
  filename = path.resolve(root, filename)
  if (cache.has(filename)) return cache.get(filename).exports
  const module = { exports: {} }
  cache.set(filename, module)
  const source = fs.readFileSync(filename, 'utf8')
  const code = filename.endsWith('.vue') ? compileScript(parse(source).descriptor, { id: filename, inlineTemplate: true }).content : source
  const { outputText } = ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  const localRequire = id => id.startsWith('.') ? loadTs(path.resolve(path.dirname(filename), /\.(vue|ts)$/.test(id) ? id : `${id}.ts`)) : require(id)
  new Function('require', 'module', 'exports', outputText)(localRequire, module, module.exports)
  return module.exports
}

const { cyclePage, locateProtocolItems, operatorInputKey, protocolFileExists } = loadTs('src/lib/runPresentation.ts')
const { useRunStatusStore } = loadTs('src/stores/runStatus.ts')
const step = (id, process = 'delay') => ({ type: 'process', id, process, parameters: {} })
const plan = {
  document: { schema_version: 2, main_parameter: {}, sequence: [step('before'), { type: 'repeat', id: 'repeat', label: 'Assembly', count: '9007199254740993', steps: [step('inside')] }, step('after')] },
  total_executions: '9007199254740995',
}
assert.deepEqual(cyclePage('9007199254740990', '9007199254740993'), ['9007199254740990', '9007199254740991', '9007199254740992', '9007199254740993'])
assert.equal(cyclePage('1', '9999999999999999999999999999').length, 4)
assert.deepEqual(locateProtocolItems(plan).map(item => item.offset), ['0', '1', '9007199254740994'])
assert.notEqual(operatorInputKey('delay_1', 'check'), operatorInputKey('delay_2', 'check'))
assert.equal(protocolFileExists('saved.json', [{ filename: 'saved.json' }]), true)
assert.equal(protocolFileExists('saved.json', [{ filename: 'another.json' }]), false, 'An accepted snapshot cannot restart or delete its missing saved source')
assert.equal(protocolFileExists('', [{ filename: 'saved.json' }]), false)
setActivePinia(createPinia())
const store = useRunStatusStore()
store.setPlan(plan)
assert.equal(store.processCards.length, 2, 'No future repeated occurrence is eagerly allocated')
const metadata = cycle => ({ execution_key: `delay_${cycle}`, source_id: 'inside', process_name: 'delay', execution_index: cycle, group_id: 'repeat', group_label: 'Assembly', cycle, count: '9007199254740993' })
const event = (cycle, kind, extra = {}) => ({ process: `delay_${cycle}`, occurrence: metadata(cycle), event_type: kind, ...extra })
store.applyEvent(event('1', 'EXECUTION_STARTED'))
store.applyEvent(event('1', 'NODE_INPUT_REQUESTED', { node_key: ['check', 0], state: 'RUNNING', message: 'First cycle?' }))
store.applyEvent(event('2', 'EXECUTION_STARTED'))
store.applyEvent(event('2', 'NODE_INPUT_REQUESTED', { node_key: ['check', 0], state: 'RUNNING', message: 'Second cycle?' }))
assert.equal(store.processCards.filter(card => card.occurrence).length, 2)
assert.equal(store.pendingInputs['delay_1::check'], 'First cycle?')
assert.equal(store.pendingInputs['delay_2::check'], 'Second cycle?')
store.applyEvent(event('1', 'NODE_FAILED', { node_key: ['check', 0], state: 'FAILED', message: 'First cycle failed' }))
assert.equal(store.processCards.find(card => card.stepKey === 'delay_2').nodes[0].inputPrompt, 'Second cycle?')
assert.equal(store.currentOccurrence.cycle, '2', 'Late events must not move the current outer cycle backwards')
store.applyEvent(event('2', 'NODE_COMPLETED', { node_key: ['check', 2], state: 'COMPLETED', percentage: 100 }))
store.applyEvent(event('2', 'NODE_INACTIVE', { node_key: ['check', 3], state: 'INACTIVE' }))
assert.equal(store.processCards.find(card => card.stepKey === 'delay_2').nodes[0].state, 'COMPLETED')
const events = [event('1', 'EXECUTION_STARTED'), event('1', 'EXECUTION_FINISHED')]
globalThis.fetch = async () => ({ ok: true, json: async () => ({ run_id: 'restored', state: 'finished', protocol: 'saved.json', protocol_plan: plan, events, current_occurrence: metadata('1') }) })
await store.restoreRunSnapshot()
assert.equal(store.runState, 'finished')
assert.equal(store.selectedProtocol, 'saved.json')
assert.equal(store.protocolPlan.total_executions, '9007199254740995')
assert.equal(store.processCards.find(card => card.stepKey === 'delay_1').status, 'completed')
assert.equal(store.currentOccurrence.cycle, '1')

const RepeatGroupView = loadTs('src/components/run/RepeatExecutionGroup.vue').default
const pinia = createPinia()
setActivePinia(pinia)
const historyStore = useRunStatusStore()
historyStore.setPlan(plan)
for (let cycle = 1; cycle <= 500; cycle++) {
  historyStore.applyEvent(event(String(cycle), 'EXECUTION_STARTED'))
  historyStore.applyEvent(event(String(cycle), 'EXECUTION_FINISHED'))
}
historyStore.setRunState('cancelled')
const group = plan.document.sequence[1]
plan.resolved_document = structuredClone(plan.document)
plan.resolved_document.main_parameter.accepted_default = 'frozen default'
const render = () => renderToString(createSSRApp(RepeatGroupView, { group, offset: '1', plan, nowSeconds: 0, drafts: {} }).use(pinia))
let html = await render()
assert.equal((html.match(/class="cycle-card/g) ?? []).length, 8, '500 completed cycles and an enormous future count still render only two bounded pages')
assert.ok(html.includes('Not executed'))
assert.ok(html.includes('500 of 9007199254740993 cycles completed'))
assert.equal((html.match(/class="process-card/g) ?? []).length, 0, 'Completed cycles are initially collapsed')
historyStore.setRunState('running')
historyStore.applyEvent(event('501', 'EXECUTION_STARTED'))
historyStore.applyEvent(event('501', 'NODE_INPUT_REQUESTED', { node_key: ['check', 0], state: 'RUNNING', message: 'Current cycle reply' }))
let previewedDocument
globalThis.fetch = async (_url, options) => {
  previewedDocument = JSON.parse(options.body).data
  return { ok: true, json: async () => ({ occurrences: [{ ...metadata('501'), process: 'delay' }] }) }
}
html = await render()
assert.equal(previewedDocument.main_parameter.accepted_default, 'frozen default', 'Cycle previews must use the accepted resolved defaults snapshot')
assert.equal((html.match(/class="cycle-card/g) ?? []).length, 9)
assert.ok(html.includes('Current cycle reply'), 'The current cycle opens with its operator prompt visible')
assert.ok(html.includes('delay_501%3A%3Acheck'), 'Input element identity includes the execution occurrence')
historyStore.applyEvent(event('501', 'NODE_FAILED', { node_key: ['check', 0], state: 'FAILED', message: 'Node execution failed: Run was cancelled.' }))
historyStore.applyEvent(event('501', 'EXECUTION_FINISHED'))
historyStore.setRunState('cancelled')
html = await render()
assert.ok(html.includes('500 of 9007199254740993 cycles completed'), 'Cancellation in the last process must not count an interrupted cycle as completed')
assert.ok(html.includes('Current cycle'))
assert.ok(html.includes('Interrupted'))
const { formatDuration, formatEstimate, formatEta, hasEstimate, remainingEstimate, unestimatedNote } = loadTs('src/lib/protocolEstimate.ts')
const huge = 9007199254740993n
const estimate = { step_ms: { before: '60000', inside: '1000', after: null }, total_ms: String(60000n + huge * 1000n), unestimated_executions: '1', errors: {} }
const sequence = plan.document.sequence
assert.equal(hasEstimate(estimate), true)
assert.equal(hasEstimate({ ...estimate, step_ms: { before: null } }), false, 'Nothing to show when no step has an estimate')
assert.equal(hasEstimate(undefined), false)
assert.deepEqual(remainingEstimate(sequence, estimate, null, 0), { ms: 60000n + huge * 1000n, unestimated: 1n }, 'Before the run starts, everything remains')
assert.deepEqual(remainingEstimate(sequence, estimate, { execution_index: '0' }, 20000), { ms: 40000n + huge * 1000n, unestimated: 1n })
assert.deepEqual(remainingEstimate(sequence, estimate, { execution_index: '0' }, 90000), { ms: huge * 1000n, unestimated: 1n }, 'A step over its estimate never counts negative')
assert.deepEqual(remainingEstimate(sequence, estimate, { execution_index: '5' }, 400), { ms: (huge - 5n) * 1000n + 600n, unestimated: 1n }, 'Mid-cycle in an enormous group, without iterating cycles')
assert.deepEqual(remainingEstimate(sequence, estimate, { execution_index: '5' }, 400, true), { ms: (huge - 5n) * 1000n, unestimated: 1n }, 'A finished current execution leaves nothing')
assert.deepEqual(remainingEstimate(sequence, estimate, { execution_index: String(huge + 1n) }, 0), { ms: 0n, unestimated: 1n }, 'Only the unestimated last step remains')
const pair = [{ type: 'repeat', id: 'pair', label: 'Pair', count: '3', steps: [step('a'), step('b')] }]
const pairEstimate = { step_ms: { a: '100', b: '200' }, total_ms: '900', unestimated_executions: '0' }
assert.deepEqual(remainingEstimate(pair, pairEstimate, { execution_index: '3' }, 50), { ms: 100n + 200n + 150n, unestimated: 0n }, 'Second cycle, second step: one a and one b left after the current b')
assert.deepEqual(remainingEstimate(pair, pairEstimate, { execution_index: '5' }, 500), { ms: 0n, unestimated: 0n })
assert.equal(formatDuration(0n), '0 s')
assert.equal(formatDuration(1n), '1 s', 'A countdown reads 0 s only once it is over')
assert.equal(formatDuration(45000n), '45 s')
assert.equal(formatDuration(59500n), '1 min')
assert.equal(formatDuration(12n * 60000n), '12 min')
assert.equal(formatDuration(150n * 60000n), '2 h 30 min')
assert.equal(formatDuration(3600000n), '1 h')
assert.equal(formatDuration(76n * 3600000n), '3 d 4 h')
assert.equal(formatDuration(huge * 1000n), '> 100 years')
assert.equal(formatEstimate(150n * 60000n), '≈ 2 h 30 min')
assert.equal(formatEstimate(huge * 1000n), '> 100 years', 'No approximation sign on a bound')
assert.equal(unestimatedNote(0n), '')
assert.equal(unestimatedNote(1n), '1 execution not estimated')
assert.equal(unestimatedNote(2n), '2 executions not estimated')
const noon = new Date(2026, 10, 17, 12, 0).getTime()
assert.equal(formatEta(noon, 90n * 60000n), new Date(noon + 90 * 60000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
assert.ok(formatEta(noon, 2n * 86400000n).startsWith(new Date(noon + 2 * 86400000).toLocaleDateString([], { weekday: 'short' })))
assert.equal(formatEta(noon, huge * 1000n), null, 'No finish time beyond what a Date can represent')
setActivePinia(createPinia())
const timed = useRunStatusStore()
timed.setPlan(plan)
timed.applyEvent(event('1', 'EXECUTION_STARTED', { timestamp: 1000 }))
assert.deepEqual({ ...timed.currentTiming }, { key: 'delay_1', startedAt: 1000, finished: false })
timed.applyEvent(event('1', 'EXECUTION_FINISHED', { timestamp: 1004 }))
assert.equal(timed.currentTiming.finished, true)
timed.applyEvent(event('2', 'EXECUTION_STARTED', { timestamp: 1005 }))
assert.deepEqual({ ...timed.currentTiming }, { key: 'delay_2', startedAt: 1005, finished: false })
timed.applyEvent(event('1', 'EXECUTION_STARTED', { timestamp: 2000 }))
assert.equal(timed.currentTiming.key, 'delay_2', 'A late event from an earlier execution never takes over the timing')
timed.setPlan(plan)
assert.equal(timed.currentTiming, null)
console.log('Run presentation: exact counts, bounded pages and rendered history, progressive cards, scoped prompts, current-cycle expansion, iteration handling, finished reload, and duration estimates passed.')
