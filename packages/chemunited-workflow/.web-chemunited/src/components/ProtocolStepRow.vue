<script setup lang="ts">
import type { ProcessStep } from '../lib/protocolPlan'

defineProps<{
  step: ProcessStep
  position?: string
  selected: boolean
  checkable?: boolean
  checked?: boolean
  disabled?: boolean
}>()
defineEmits<{
  select: [id: string]
  check: [id: string, checked: boolean]
}>()
</script>

<template>
  <div class="protocol-step" :class="{ selected }">
    <input
      v-if="checkable"
      type="checkbox"
      :checked="checked"
      :disabled="disabled"
      :aria-label="`Include ${step.process} in repeat selection`"
      @change="$emit('check', step.id, ($event.target as HTMLInputElement).checked)"
    >
    <button type="button" class="step-select" :aria-pressed="selected" @click="$emit('select', step.id)">
      <span v-if="position" class="position">{{ position }}</span>
      <span class="connector" aria-hidden="true"></span>
      <span class="process-name">{{ step.process }}</span>
      <span class="chevron" aria-hidden="true">›</span>
    </button>
  </div>
</template>

<style scoped>
.protocol-step { display: flex; align-items: center; min-width: 0; gap: 0.55rem; padding: 0.25rem 0.5rem; border: 1px solid transparent; border-radius: var(--radius-sm); }
.protocol-step:hover { background: var(--color-background-mute); }
.protocol-step.selected { border-color: var(--color-primary); background: var(--color-primary-soft); }
.protocol-step input { flex-shrink: 0; accent-color: var(--color-primary); }
.step-select { display: flex; align-items: center; flex: 1; min-width: 0; gap: 0.65rem; min-height: 38px; padding: 0.25rem 0; border: 0; color: var(--color-heading); background: transparent; text-align: left; cursor: pointer; }
.position { color: var(--color-text-muted); font-size: 0.68rem; min-width: 1.6rem; max-width: 4.5rem; overflow: hidden; text-overflow: ellipsis; font-variant-numeric: tabular-nums; }
.connector { width: 7px; height: 7px; flex-shrink: 0; border: 2px solid var(--color-border-hover); border-radius: 50%; }
.selected .connector { border-color: var(--color-primary); background: var(--color-primary); }
.process-name { overflow-wrap: anywhere; font-size: 0.81rem; font-weight: 650; }
.chevron { margin-left: auto; color: var(--color-text-muted); font-size: 1.2rem; }
</style>
