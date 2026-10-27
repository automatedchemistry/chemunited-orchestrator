<script setup lang="ts">
import { computed } from 'vue'
import ExtensionHost from './ExtensionHost.vue'
import { customization } from './manifest'

/**
 * A place on a built-in page where the project's widgets go (Widget(slot=...)
 * in ui_hook.py). Each widget gets the slot's `context` as a prop.
 */
const props = defineProps<{
  name: string
  context?: Record<string, unknown>
}>()

const widgets = computed(() =>
  customization.manifest.widgets
    .filter(widget => widget.slot === props.name)
    .sort((a, b) => a.order - b.order),
)
</script>

<template>
  <div v-if="widgets.length" class="cu-slot" :data-slot="name">
    <section v-for="widget in widgets" :key="widget.component_url" class="cu-widget">
      <h3 v-if="widget.title" class="cu-widget-title">{{ widget.title }}</h3>
      <ExtensionHost
        :url="widget.component_url"
        :file="widget.component"
        :bind="{ context: context ?? {} }"
      />
    </section>
  </div>
</template>
