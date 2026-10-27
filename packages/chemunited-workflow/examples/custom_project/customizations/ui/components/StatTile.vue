<script setup lang="ts">
defineProps<{ label: string, value: string }>()
</script>

<template>
  <div class="cu-panel">
    <p class="label">{{ label }}</p>
    <p class="value">{{ value }}</p>
  </div>
</template>

<style scoped>
.label {
  margin: 0 0 0.35rem;
  color: var(--color-text-muted);
  font-size: 0.72rem;
  font-weight: 750;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.value {
  margin: 0;
  color: var(--color-heading);
  font-size: 1.4rem;
  font-weight: 720;
}
</style>
