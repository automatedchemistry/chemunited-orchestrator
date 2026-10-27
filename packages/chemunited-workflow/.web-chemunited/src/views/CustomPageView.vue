<script setup lang="ts">
import ExtensionHost from '../extensions/ExtensionHost.vue'
import type { VuePageSpec } from '../extensions/manifest'

/** A page from the project's customizations/ui/ (VuePage in ui_hook.py). */
defineProps<{ spec: VuePageSpec }>()
</script>

<template>
  <ExtensionHost :key="spec.component_url" :url="spec.component_url" :file="spec.component" />
</template>
