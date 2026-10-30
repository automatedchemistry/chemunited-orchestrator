<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { HtmlPageSpec } from '../extensions/manifest'

/**
 * A page whose HTML a Python function renders (HtmlPage in ui_hook.py), in a
 * sandboxed frame: its scripts run, but with no access to the dashboard.
 */
const props = defineProps<{ spec: HtmlPageSpec }>()

const version = ref(0)
let timer: number | undefined

function reload() {
  version.value += 1
}

onMounted(() => {
  if (props.spec.refresh_seconds) timer = window.setInterval(reload, props.spec.refresh_seconds * 1000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="page-shell html-page">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Project page</p>
        <h1 class="page-title">{{ spec.label }}</h1>
        <p v-if="spec.refresh_seconds" class="page-description">
          Refreshes every {{ spec.refresh_seconds }} s.
        </p>
      </div>
      <button type="button" class="cu-button" @click="reload">Reload</button>
    </header>
    <iframe
      class="html-frame"
      :src="`${spec.html_url}?v=${version}`"
      :title="spec.label"
      sandbox="allow-scripts"
    />
  </div>
</template>

<style scoped>
.html-frame {
  width: 100%;
  height: calc(100vh - 12rem);
  min-height: 420px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: #fff;
}
</style>
