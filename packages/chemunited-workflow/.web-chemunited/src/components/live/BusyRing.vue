<script setup lang="ts">
import { computed } from 'vue'
import type { Box } from './liveFormat'

// A ring around a device's figure: turning while it runs a command, or a
// short flash for a command that came back at once (its device doesn't
// report when it finishes).
const props = defineProps<{ box: Box, flash?: boolean }>()

const ring = computed(() => {
  const [x, y, w, h] = props.box
  const pad = Math.max(4, Math.min(w, h) * 0.08)
  return {
    x: x - pad,
    y: y - pad,
    width: w + 2 * pad,
    height: h + 2 * pad,
    rx: Math.min(w, h) * 0.12,
  }
})
</script>

<template>
  <rect
    class="busy-ring"
    :class="flash ? 'is-flash' : 'is-running'"
    :x="ring.x"
    :y="ring.y"
    :width="ring.width"
    :height="ring.height"
    :rx="ring.rx"
  />
</template>

<style scoped>
.busy-ring {
  fill: none;
  stroke: var(--color-primary);
  stroke-width: 3px;
  vector-effect: non-scaling-stroke;
}

.is-running {
  stroke-dasharray: 10 7;
  animation: busy-ring-turn 900ms linear infinite;
}

.is-flash {
  animation: busy-ring-flash 1500ms ease-out forwards;
}

@keyframes busy-ring-turn {
  to { stroke-dashoffset: -34; }
}

@keyframes busy-ring-flash {
  from { opacity: 1; }
  to { opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .is-running,
  .is-flash {
    animation: none;
  }
}
</style>
