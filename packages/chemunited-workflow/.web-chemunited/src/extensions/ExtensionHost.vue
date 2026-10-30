<script setup lang="ts">
import { markRaw, onErrorCaptured, onMounted, ref, shallowRef, watch, type Component } from 'vue'
import { RouterLink } from 'vue-router'
import {
  clearProblems,
  formatProblem,
  reportProblems,
  toProblems,
  type ExtensionProblem,
} from './errors'

/**
 * Loads one customization file (a custom page or widget) and renders it inside
 * an error boundary: if it fails to compile, load or run, an error card takes
 * its place and the rest of the dashboard keeps working.
 */
const props = defineProps<{
  /** /ui/ext/... URL of the .vue file. */
  url: string
  /** Its path under customizations/ui/, for messages. */
  file: string
  /** Props passed to the component. */
  bind?: Record<string, unknown>
}>()

const component = shallowRef<Component | null>(null)
const problems = ref<ExtensionProblem[]>([])
const loading = ref(false)

function fail(error: unknown) {
  component.value = null
  problems.value = toProblems(error, props.file)
  reportProblems(props.file, problems.value)
}

async function load() {
  loading.value = true
  problems.value = []
  component.value = null
  try {
    const { loadExtensionComponent } = await import('./loader/moduleGraph')
    component.value = markRaw(await loadExtensionComponent(props.url))
    clearProblems(props.file)
  } catch (error) {
    fail(error)
  } finally {
    loading.value = false
  }
}

onErrorCaptured(error => {
  fail(error)
  return false
})

watch(() => props.url, load)
onMounted(load)
</script>

<template>
  <div v-if="problems.length" class="cu-error-card" role="alert">
    <strong>This customization failed to load</strong>
    <ul>
      <li v-for="p in problems" :key="formatProblem(p)"><code>{{ formatProblem(p) }}</code></li>
    </ul>
    <div class="cu-error-actions">
      <button type="button" class="cu-button" @click="load">Try again</button>
      <RouterLink to="/customizations">Open diagnostics</RouterLink>
    </div>
  </div>
  <p v-else-if="loading" class="cu-loading" aria-live="polite">Loading {{ file }}…</p>
  <component :is="component" v-else-if="component" v-bind="bind ?? {}" />
</template>
