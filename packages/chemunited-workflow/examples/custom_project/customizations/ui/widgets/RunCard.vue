<script setup lang="ts">
import { computed } from 'vue'

// Every widget gets its slot's context; dashboard.cards passes these.
const props = defineProps<{
  context: { project_dir?: string | null, run_id?: string | null, run_state?: string | null }
}>()

const text = computed(() =>
  props.context.run_id
    ? `${props.context.run_state ?? 'running'} · ${props.context.run_id.slice(0, 8)}`
    : 'No run active',
)
</script>

<template>
  <div class="cu-panel">
    <p class="cu-muted">widgets/RunCard.vue in the dashboard.cards slot</p>
    <p class="value">{{ text }}</p>
  </div>
</template>

<style scoped>
.value {
  margin: 0.3rem 0 0;
  color: var(--color-heading);
  font-size: 1.2rem;
  font-weight: 700;
}
</style>
