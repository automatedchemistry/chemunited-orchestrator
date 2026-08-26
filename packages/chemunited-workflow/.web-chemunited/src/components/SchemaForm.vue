<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

interface SchemaProperty {
  type?: string
  title?: string
  description?: string
  default?: unknown
  group?: string
  editable?: boolean
  visible?: boolean
  unit?: string
  minimum?: number
  maximum?: number
  minLength?: number
  maxLength?: number
  step?: number
  Options?: unknown[]
  enum?: unknown[]
  multi?: boolean
  on_text?: string
  off_text?: string
  items?: { type?: string }
}

interface FieldEntry {
  key: string
  prop: SchemaProperty
}

interface GroupEntry {
  label: string
  fields: FieldEntry[]
}

const props = defineProps<{
  properties: Record<string, SchemaProperty>
  values: Record<string, unknown>
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:values', v: Record<string, unknown>): void
}>()

const local = reactive<Record<string, unknown>>({})

watch(
  () => props.values,
  (v) => {
    for (const key of Object.keys(local)) delete local[key]
    Object.assign(local, v)
  },
  { immediate: true, deep: true },
)

function update(key: string, val: unknown) {
  local[key] = val
  emit('update:values', { ...local })
}

const groups = computed<GroupEntry[]>(() => {
  const map = new Map<string, FieldEntry[]>()
  for (const [key, prop] of Object.entries(props.properties)) {
    if (prop.visible === false) continue
    const label = prop.group ?? ''
    if (!map.has(label)) map.set(label, [])
    map.get(label)!.push({ key, prop })
  }
  return Array.from(map.entries()).map(([label, fields]) => ({ label, fields }))
})

function fieldType(prop: SchemaProperty): string {
  const opts = prop.Options ?? prop.enum
  if (opts && opts.length > 0) return 'options'
  if (prop.type === 'boolean') return 'boolean'
  if (prop.type === 'integer') return 'integer'
  if (prop.type === 'number') return 'number'
  if (prop.type === 'array') return 'array'
  if (prop.unit) return 'unit-string'
  return 'string'
}

function getValue(key: string, prop: SchemaProperty): unknown {
  return key in local ? local[key] : (prop.default ?? '')
}

function getArray(key: string, prop: SchemaProperty): unknown[] {
  const v = getValue(key, prop)
  return Array.isArray(v) ? v : []
}

function addArrayItem(key: string, prop: SchemaProperty) {
  update(key, [...getArray(key, prop), ''])
}

function updateArrayItem(key: string, prop: SchemaProperty, idx: number, val: string) {
  const arr = [...getArray(key, prop)]
  arr[idx] = val
  update(key, arr)
}

function removeArrayItem(key: string, prop: SchemaProperty, idx: number) {
  const arr = [...getArray(key, prop)]
  arr.splice(idx, 1)
  update(key, arr)
}
</script>

<template>
  <div class="schema-form">
    <section v-for="group in groups" :key="group.label" class="field-group">
      <div v-if="group.label" class="group-heading">
        <span>{{ group.label }}</span>
        <span class="group-count">{{ group.fields.length }}</span>
      </div>

      <div class="field-grid">
        <div
          v-for="{ key, prop } in group.fields"
          :key="key"
          class="field-card"
          :class="{
            disabled: prop.editable === false,
            readonly: props.readonly,
            wide: fieldType(prop) === 'array',
          }"
        >
          <div class="field-header">
            <label :for="`field-${key}`" class="field-title">{{ prop.title || key }}</label>
            <span class="type-badge">{{ fieldType(prop) }}</span>
          </div>

          <p v-if="prop.description" class="field-desc">{{ prop.description }}</p>

          <select
            v-if="fieldType(prop) === 'options'"
            :id="`field-${key}`"
            :value="String(getValue(key, prop))"
            :disabled="props.readonly || prop.editable === false"
            @change="update(key, ($event.target as HTMLSelectElement).value)"
          >
            <option
              v-for="opt in (prop.Options ?? prop.enum)"
              :key="String(opt)"
              :value="String(opt)"
            >{{ opt }}</option>
          </select>

          <label v-else-if="fieldType(prop) === 'boolean'" class="toggle-row">
            <input
              :id="`field-${key}`"
              type="checkbox"
              :checked="Boolean(getValue(key, prop))"
              :disabled="props.readonly || prop.editable === false"
              @change="update(key, ($event.target as HTMLInputElement).checked)"
            />
            <span class="toggle-track" aria-hidden="true">
              <span class="toggle-thumb"></span>
            </span>
            <span class="toggle-text">
              {{ getValue(key, prop) ? (prop.on_text ?? 'On') : (prop.off_text ?? 'Off') }}
            </span>
          </label>

          <input
            v-else-if="fieldType(prop) === 'integer'"
            :id="`field-${key}`"
            type="number"
            step="1"
            :min="prop.minimum"
            :max="prop.maximum"
            :value="getValue(key, prop)"
            :disabled="props.readonly || prop.editable === false"
            @input="update(key, Number(($event.target as HTMLInputElement).value))"
          />

          <input
            v-else-if="fieldType(prop) === 'number'"
            :id="`field-${key}`"
            type="number"
            :step="prop.step ?? 0.01"
            :min="prop.minimum"
            :max="prop.maximum"
            :value="getValue(key, prop)"
            :disabled="props.readonly || prop.editable === false"
            @input="update(key, Number(($event.target as HTMLInputElement).value))"
          />

          <div v-else-if="fieldType(prop) === 'unit-string'" class="unit-row">
            <input
              :id="`field-${key}`"
              type="text"
              :value="String(getValue(key, prop))"
              :disabled="props.readonly || prop.editable === false"
              @input="update(key, ($event.target as HTMLInputElement).value)"
            />
            <span class="unit-badge">{{ prop.unit }}</span>
          </div>

          <div v-else-if="fieldType(prop) === 'array'" class="array-field">
            <div
              v-for="(item, idx) in getArray(key, prop)"
              :key="idx"
              class="array-row"
            >
              <span class="array-index">{{ idx + 1 }}</span>
              <input
                :id="idx === 0 ? `field-${key}` : undefined"
                type="text"
                :value="String(item)"
                :disabled="props.readonly || prop.editable === false"
                @input="updateArrayItem(key, prop, idx, ($event.target as HTMLInputElement).value)"
              />
              <button
                type="button"
                class="icon-btn"
                :disabled="props.readonly || prop.editable === false"
                :aria-label="`Remove item ${idx + 1}`"
                @click="removeArrayItem(key, prop, idx)"
              >×</button>
            </div>
            <button
              type="button"
              class="add-btn"
              :disabled="props.readonly || prop.editable === false"
              @click="addArrayItem(key, prop)"
            >
              <span>+</span>
              Add item
            </button>
          </div>

          <input
            v-else
            :id="`field-${key}`"
            type="text"
            :value="String(getValue(key, prop))"
            :disabled="props.readonly || prop.editable === false"
            @input="update(key, ($event.target as HTMLInputElement).value)"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.schema-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field-group {
  min-width: 0;
}

.group-heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.15rem 0 0.65rem;
  color: var(--color-heading);
  font-size: 0.76rem;
  font-weight: 680;
  text-transform: capitalize;
}

.group-count {
  min-width: 21px;
  padding: 0.05rem 0.35rem;
  color: var(--color-text-muted);
  border-radius: 999px;
  background: var(--color-background-mute);
  text-align: center;
  font-size: 0.62rem;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 270px), 1fr));
  gap: 0.65rem;
}

.field-card {
  min-width: 0;
  padding: 0.8rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-background-soft);
  transition:
    border-color 150ms ease,
    box-shadow 150ms ease;
}

.field-card:focus-within:not(.readonly) {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 9%, transparent);
}

.field-card.wide {
  grid-column: 1 / -1;
}

.field-card.disabled {
  opacity: 0.55;
}

.field-card.readonly {
  background: color-mix(in srgb, var(--color-background-mute) 50%, var(--color-background-soft));
}

.field-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  margin-bottom: 0.35rem;
}

.field-title {
  overflow: hidden;
  color: var(--color-heading);
  font-size: 0.79rem;
  font-weight: 680;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.type-badge {
  flex: 0 0 auto;
  padding: 0.14rem 0.4rem;
  color: var(--color-text-muted);
  border-radius: 5px;
  background: var(--color-background-mute);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.58rem;
  letter-spacing: 0.02em;
}

.field-desc {
  margin: -0.05rem 0 0.55rem;
  color: var(--color-text-muted);
  font-size: 0.7rem;
  line-height: 1.45;
}

input[type='text'],
input[type='number'],
select {
  width: 100%;
  height: 38px;
  padding: 0 0.65rem;
  color: var(--color-heading);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background);
  font-size: 0.8rem;
  transition:
    border-color 150ms ease,
    background-color 150ms ease;
}

input:hover:not(:disabled),
select:hover:not(:disabled) {
  border-color: var(--color-border-hover);
}

input:focus,
select:focus {
  border-color: var(--color-primary);
}

input:disabled,
select:disabled {
  cursor: not-allowed;
  color: var(--color-text-muted);
}

.toggle-row {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  cursor: pointer;
}

.toggle-row input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  opacity: 0;
}

.toggle-track {
  width: 38px;
  height: 21px;
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  padding: 2px;
  border-radius: 999px;
  background: var(--color-border-hover);
  transition: background-color 160ms ease;
}

.toggle-thumb {
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 42, 67, 0.25);
  transition: transform 160ms ease;
}

.toggle-row input:checked + .toggle-track {
  background: var(--color-primary);
}

.toggle-row input:checked + .toggle-track .toggle-thumb {
  transform: translateX(17px);
}

.toggle-row input:focus-visible + .toggle-track {
  outline: 3px solid color-mix(in srgb, var(--color-primary) 30%, transparent);
  outline-offset: 2px;
}

.toggle-row input:disabled + .toggle-track,
.toggle-row input:disabled ~ .toggle-text {
  cursor: not-allowed;
  opacity: 0.55;
}

.toggle-text {
  color: var(--color-text);
  font-size: 0.8rem;
  font-weight: 620;
}

.unit-row {
  display: flex;
  align-items: stretch;
}

.unit-row input {
  min-width: 0;
  border-radius: var(--radius-sm) 0 0 var(--radius-sm);
}

.unit-badge {
  min-width: 48px;
  display: grid;
  place-items: center;
  padding: 0 0.55rem;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-left: 0;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: var(--color-background-mute);
  font-size: 0.7rem;
  font-weight: 680;
  white-space: nowrap;
}

.array-field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.array-row {
  display: grid;
  grid-template-columns: 25px minmax(0, 1fr) 34px;
  align-items: center;
  gap: 0.4rem;
}

.array-index {
  color: var(--color-text-muted);
  text-align: center;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.65rem;
}

.icon-btn {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  padding: 0;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background);
  cursor: pointer;
  font-size: 1rem;
}

.icon-btn:hover:not(:disabled) {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 25%, var(--color-border));
  background: var(--color-danger-soft);
}

.add-btn {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 0.4rem;
  margin-left: 2.05rem;
  padding: 0.35rem 0.65rem;
  color: var(--color-primary);
  border: 1px dashed color-mix(in srgb, var(--color-primary) 45%, var(--color-border));
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  font-size: 0.72rem;
  font-weight: 670;
}

.add-btn span {
  font-size: 1rem;
  line-height: 0;
}

.add-btn:hover:not(:disabled) {
  background: var(--color-primary-soft);
}

.add-btn:disabled,
.icon-btn:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

@media (max-width: 520px) {
  .field-grid {
    grid-template-columns: 1fr;
  }
}
</style>
