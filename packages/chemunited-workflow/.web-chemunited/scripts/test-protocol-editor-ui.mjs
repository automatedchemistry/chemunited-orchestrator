// Compile and render the actual editor without services or device connections.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { parse, compileScript } from '@vue/compiler-sfc'
import { transform } from 'sucrase'
import * as plan from '../src/lib/protocolPlan.ts'

const require = createRequire(import.meta.url)
const Vue = require('vue')
const runtime = { ...Vue, withDirectives(vnode, directives) {
  // Native v-model directives use DOM events. Expose the same model value to
  // this in-memory host; generated onUpdate:modelValue handlers remain real.
  vnode.props = { ...vnode.props, value: directives[0]?.[1] }
  return vnode
} }
const files = new Map()
const notifications = []
function component(relative) {
  if (files.has(relative)) return files.get(relative)
  const filename = path.resolve('src', relative)
  const { descriptor, errors } = parse(fs.readFileSync(filename, 'utf8'), { filename })
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: relative, inlineTemplate: true, genDefaultAs: 'Component' })
  const code = transform(`${script.content}\nmodule.exports = Component`, { transforms: ['typescript', 'imports'] }).code
  const result = { exports: {} }
  const modules = {
    vue: runtime,
    '../lib/protocolPlan': plan,
    '../composables/useNotification': { useNotification: () => ({ notify: (...message) => notifications.push(message) }) },
    '../extensions/manifest': { customization: { manifest: { protocols: { process_categories: {}, other_label: 'Processes' } } } },
  }
  new Function('require', 'module', 'exports', code)(name => {
    if (modules[name]) return modules[name]
    if (name.startsWith('../components/')) return component(`components/${name.split('/').at(-1)}`)
    return require(name)
  }, result, result.exports)
  files.set(relative, result.exports)
  return result.exports
}

const originalFetch = globalThis.fetch
const originalWindow = globalThis.window
const previewRequests = []
const saved = []
let rejectSave = false
const source = { main_parameter: { scale: 2 }, command_delay_sec_0: { duration: '1 s' }, command_delay_sec_1: { duration: '2 s' }, hidden_process_0: {} }
const json = value => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
globalThis.window = { confirm: () => true }
globalThis.fetch = async (url, options = {}) => {
  if (url === '/processes/') return json([{ name: 'command_delay_sec', description: 'Delay' }, { name: 'hidden_process', description: 'Historic only', library_visible: false }])
  if (url === '/protocols/' && options.method !== 'POST') return json([{ filename: 'legacy.json' }, ...saved.map((_, index) => ({ filename: `saved_${index}.json` }))])
  if (url === '/protocols/legacy.json') return json(source)
  if (url.endsWith('/schema')) return json({ config_schema: { properties: { duration: { type: 'string', title: 'Duration', default: '1 s' } } }, main_parameter_schema: { properties: { scale: { type: 'number', default: 1 } } } })
  if (url === '/protocols/' && options.method === 'POST') {
    if (rejectSave) return new Response(JSON.stringify({ detail: 'Repeat group / command_delay_sec [command_delay_sec_1] / duration: invalid unit' }), { status: 422, headers: { 'Content-Type': 'application/json' } })
    saved.push(JSON.parse(options.body)); return json({ filename: `saved_${saved.length - 1}.json` })
  }
  if (url === '/protocols/preview') {
    const request = JSON.parse(options.body)
    previewRequests.push(request)
    const document = plan.canonicalDocument(request.data)
    const occurrences = []
    const total = plan.totalExecutions(document)
    for (let index = BigInt(request.offset); index < total && occurrences.length < request.limit; index++) {
      let remaining = index
      for (const item of document.sequence) {
        const size = plan.itemExecutions(item)
        if (remaining >= size) { remaining -= size; continue }
        const group = item.type === 'repeat' ? item : null
        const step = group ? group.steps[Number(remaining % BigInt(group.steps.length))] : item
        const cycle = group ? (remaining / BigInt(group.steps.length) + 1n).toString() : null
        occurrences.push({ execution_key: `${step.process}_${index}`, execution_index: index.toString(), process_index: index.toString(), source_id: step.id, process: step.process, group_id: group?.id ?? null, cycle, count: group?.count ?? null, label: group?.label ?? null, parameters: step.parameters, main_parameters: document.main_parameter })
        break
      }
    }
    return json({ document, total_executions: total.toString(), offset: request.offset, limit: request.limit, next_offset: null, occurrences })
  }
  throw new Error(`Unexpected test request: ${url}`)
}

function element(type, text = '') { return { type, text, props: {}, children: [], parent: null } }
const renderer = Vue.createRenderer({
  createElement: element, createText: text => element('#text', text), createComment: text => element('#comment', text),
  setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.children = []; node.text = text },
  patchProp: (node, key, previous, value) => { node.props[key] = value },
  insert(node, parent, anchor) {
    if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
    node.parent = parent
    const index = parent.children.indexOf(anchor)
    if (index < 0) parent.children.push(node); else parent.children.splice(index, 0, node)
  },
  remove(node) { if (node.parent) { node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null } },
  parentNode: node => node.parent,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] ?? null,
})
function all(node, predicate) { return [...(predicate(node) ? [node] : []), ...node.children.flatMap(child => all(child, predicate))] }
function text(node) { return node.text + node.children.map(text).join(' ') }
const root = element('root')
const app = renderer.createApp(component('views/ProtocolsView.vue'))
const find = predicate => all(root, predicate)[0]
const button = label => find(node => node.type === 'button' && text(node).trim() === label)
const flush = async () => { await new Promise(setImmediate); await Vue.nextTick() }
try {
  app.mount(root)
  await flush()
  assert.equal(all(root, node => node.type === 'button' && node.props.class?.includes('library-process')).length, 1, 'historic-only processes stay out of the add library')
  find(node => node.props.id === 'protocol-select').props.onChange({ target: { value: 'legacy.json' } })
  await flush()
  const checks = all(root, node => node.type === 'input' && node.props.type === 'checkbox')
  assert.equal(checks.length, 3)
  checks[0].props.onChange({ target: { checked: true } })
  checks[1].props.onChange({ target: { checked: true } })
  await flush()
  assert.equal(button('Repeat selected steps').props.disabled, false)
  button('Repeat selected steps').props.onClick()
  await flush()
  const count = find(node => node.type === 'input' && node.props.id?.startsWith('count-'))
  assert.equal(count.props.value, '2')
  const huge = '9007199254740993'
  count.props.onInput({ target: { value: huge } })
  await flush()
  assert.ok(text(root).includes((BigInt(huge) * 2n + 1n).toLocaleString()))
  button('Show cycles').props.onClick()
  await new Promise(resolve => setTimeout(resolve, 220))
  await flush()
  assert.ok(previewRequests.length)
  assert.equal(previewRequests.at(-1).data.sequence[0].count, huge)
  assert.ok(all(root, node => node.type === 'button' && node.props.class?.includes('preview-step')).length <= 20)
  find(node => node.type === 'button' && node.props.class?.includes('preview-step')).props.onClick()
  await flush()
  const duration = find(node => node.props.id === 'field-duration')
  assert.equal(duration.props.disabled, false, 'cycle inspection keeps shared source parameters editable')
  duration.props.onInput({ target: { value: '7 s' } })
  await flush()
  const name = find(node => node.props.id === 'protocol-name')
  name.props['onUpdate:modelValue']('native_repeat')
  name.props.onInput()
  await flush()
  await button('Save protocol').props.onClick()
  await flush()
  assert.equal(saved.length, 1)
  assert.equal(saved[0].data.schema_version, 2)
  assert.equal(saved[0].data.sequence.length, 2, 'saving preserves the compact tree rather than materializing future cycles')
  assert.equal(saved[0].data.sequence[0].count, huge)
  assert.equal(saved[0].data.sequence[0].steps[0].parameters.duration, '7 s')
  assert.deepEqual(saved[0].data.sequence[0].steps.map(step => step.id), ['command_delay_sec_0', 'command_delay_sec_1'])
  assert.deepEqual(saved[0].data.main_parameter, { scale: 2 })
  assert.equal(button('Save protocol').props.disabled, true)
  button('Show source steps').props.onClick()
  await flush()
  find(node => node.type === 'button' && node.props.class === 'group-disclosure').props.onClick()
  await flush()
  assert.equal(button('Save protocol').props.disabled, true, 'display-only changes never mark the saved tree modified')
  assert.equal(notifications.length, 1)
  find(node => node.type === 'button' && node.props.class === 'step-select' && text(node).includes('hidden_process')).props.onClick()
  await flush()
  assert.equal(find(node => node.props.class === 'selected-step-chip').text, 'hidden_process_0', 'hidden loaded processes retain schema selection')
  name.props['onUpdate:modelValue']('invalid_draft')
  name.props.onInput()
  rejectSave = true
  await flush()
  await button('Save protocol').props.onClick()
  await flush()
  assert.ok(text(root).includes('duration: invalid unit'))
  assert.equal(find(node => node.props.class === 'selected-step-chip').text, 'command_delay_sec_1', 'server validation selects the offending shared source')
  assert.equal(button('Save protocol').props.disabled, false, 'a rejected save preserves the editable draft')
  console.log('Rendered editor checks passed: hidden-library filtering, legacy load, grouping, huge exact count, bounded API preview, shared parameter editing, compact v2 save, display-only state and source-specific validation.')
} finally {
  app.unmount()
  globalThis.fetch = originalFetch
  globalThis.window = originalWindow
}
