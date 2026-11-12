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
console.log('Run presentation: exact counts, bounded pages and rendered history, progressive cards, scoped prompts, current-cycle expansion, iteration handling and finished reload passed.')
