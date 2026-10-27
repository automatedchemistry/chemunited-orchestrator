<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { customization, type ActionSpec, type FormProperty } from './manifest'
import { callCustomRoute, errorMessage, notify } from './publicApi'

/**
 * The project's buttons for a built-in page (PageAction(page=...) in
 * ui_hook.py). Each calls a custom route with the page's context plus the
 * values of its form fields, whose types come from the route's type hints.
 */
const props = defineProps<{
  page: string
  context?: Record<string, unknown>
}>()

const emit = defineEmits<{
  /** An action with refresh=True succeeded: reload the page's data. */
  (e: 'refresh'): void
}>()

const actions = computed(() => customization.manifest.actions.filter(action => action.page === props.page))
const values = reactive<Record<string, Record<string, unknown>>>({})
const busy = ref<string | null>(null)

function storageKey(action: ActionSpec, field: string): string {
  return `chemunited-action:${action.route}:${field}`
}

function readStored(key: string): unknown {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? undefined : JSON.parse(raw)
  } catch {
    return undefined
  }
}

function emptyValue(prop: FormProperty): unknown {
  return prop.type === 'boolean' ? false : ''
}

watch(actions, list => {
  for (const action of list) {
    if (values[action.id]) continue
    const initial: Record<string, unknown> = {}
    for (const [name, prop] of Object.entries(action.properties)) {
      const stored = action.remember.includes(name) ? readStored(storageKey(action, name)) : undefined
      const fallback = prop.type === 'array' && Array.isArray(prop.default) ? prop.default.join(', ') : prop.default
      initial[name] = stored ?? fallback ?? emptyValue(prop)
    }
    values[action.id] = initial
  }
}, { immediate: true })

function contextValue(action: ActionSpec, key: string): unknown {
  return props.context?.[key] ?? null
}

/** The size of the first list the page passes (e.g. the selected runs), shown on the button. */
function count(action: ActionSpec): number | null {
  for (const key of Object.values(action.context)) {
    const value = contextValue(action, key)
    if (Array.isArray(value)) return value.length
  }
  return null
}

function isBlank(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === 'string' && !value.trim())
    || (Array.isArray(value) && value.length === 0)
}

/** Why the action can't run yet, or null. */
function blocked(action: ActionSpec): string | null {
  for (const key of Object.values(action.context)) {
    if (isBlank(contextValue(action, key))) {
      return key === 'selection' ? 'Select at least one row first.' : `Needs ${key.replace('_', ' ')}.`
    }
  }
  for (const name of action.required) {
    if (isBlank(values[action.id]?.[name])) return `Fill in ${action.properties[name]?.title ?? name}.`
  }
  return null
}

function fieldValue(prop: FormProperty, raw: unknown): unknown {
  if (prop.type === 'integer' || prop.type === 'number') {
    if (raw === '' || raw === null) return null
    return Number(raw)
  }
  if (prop.type === 'array') {
    return String(raw ?? '').split(',').map(item => item.trim()).filter(Boolean)
  }
  return raw
}

function kwargs(action: ActionSpec): Record<string, unknown> {
  const args: Record<string, unknown> = {}
  for (const [name, prop] of Object.entries(action.properties)) {
    const value = fieldValue(prop, values[action.id]?.[name])
    if (value === null && !action.required.includes(name)) continue
    args[name] = value
  }
  for (const [param, key] of Object.entries(action.context)) args[param] = contextValue(action, key)
  return args
}

/** A route returning a string, or a dict with a "message", chooses what the user reads. */
function successMessage(action: ActionSpec, result: unknown): string {
  if (typeof result === 'string' && result.trim()) return result
  if (typeof result === 'number' || typeof result === 'boolean') return `${action.label}: ${result}`
  const message = (result as { message?: unknown } | null)?.message
  if (typeof message === 'string' && message.trim()) return message
  return `${action.label}: done.`
}

async function run(action: ActionSpec) {
  if (busy.value || blocked(action)) return
  if (action.confirm && !window.confirm(action.confirm)) return
  busy.value = action.id
  try {
    const result = await callCustomRoute(action.route, kwargs(action))
    for (const name of action.remember) {
      try {
        localStorage.setItem(storageKey(action, name), JSON.stringify(values[action.id]?.[name]))
      } catch {
        // Storage unavailable: nothing to remember.
      }
    }
    notify(successMessage(action, result), 'success')
    if (action.refresh) emit('refresh')
  } catch (error) {
    notify(`${action.label} failed: ${errorMessage(error)}`, 'error')
  } finally {
    busy.value = null
  }
}

function buttonLabel(action: ActionSpec): string {
  if (busy.value === action.id) return `${action.label}…`
  const n = count(action)
  return n === null ? action.label : `${action.label} (${n})`
}

function inputType(prop: FormProperty): string {
  return prop.type === 'integer' || prop.type === 'number' ? 'number' : 'text'
}
</script>

<template>
  <div v-if="actions.length" class="cu-page-actions" :data-page="page">
    <form
      v-for="action in actions"
      :key="action.id"
      class="cu-action"
      @submit.prevent="run(action)"
    >
      <label
        v-for="(prop, name) in action.properties"
        :key="name"
        class="cu-field"
        :class="{ 'cu-field-check': prop.type === 'boolean' }"
        :title="prop.description"
      >
        <span>{{ prop.title ?? name }}</span>
        <select v-if="prop.enum" v-model="values[action.id]![name]" class="cu-input">
          <option v-for="option in prop.enum" :key="String(option)" :value="option">{{ option }}</option>
        </select>
        <input
          v-else-if="prop.type === 'boolean'"
          v-model="values[action.id]![name]"
          type="checkbox"
        >
        <input
          v-else
          v-model="values[action.id]![name]"
          class="cu-input"
          :type="inputType(prop)"
          :step="prop.type === 'integer' ? 1 : 'any'"
          :min="prop.minimum"
          :max="prop.maximum"
          :placeholder="prop.placeholder ?? (prop.type === 'array' ? 'comma-separated' : '')"
        >
      </label>
      <button
        type="submit"
        class="cu-button primary"
        :disabled="busy !== null || blocked(action) !== null"
        :title="blocked(action) ?? action.description ?? undefined"
      >
        <img v-if="action.icon_url" :src="action.icon_url" alt="" class="cu-action-icon">
        <span>{{ buttonLabel(action) }}</span>
      </button>
    </form>
  </div>
</template>
