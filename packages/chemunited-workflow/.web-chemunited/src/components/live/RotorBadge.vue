<script setup lang="ts">
import { computed } from 'vue'
import type { Point } from './liveFormat'

// A rotary valve's rotor channels, as the desktop app draws them: links are
// pairs of rotor slots, 1 being the top slot before the valve's own rotation
// and 0 the hub. The export gives each slot's point, already rotated.
const props = defineProps<{ center: Point, slots: Point[], links: unknown }>()

const segments = computed(() => {
  const links = Array.isArray(props.links) ? props.links as unknown[] : []
  const point = (slot: unknown): Point | undefined =>
    slot === 0 ? props.center : props.slots[Number(slot) - 1]
  return links.flatMap(link => {
    if (!Array.isArray(link) || link.length !== 2) return []
    const from = point(link[0])
    const to = point(link[1])
    return from && to ? [{ from, to }] : []
  })
})
</script>

<template>
  <g class="rotor-badge">
    <line
      v-for="(segment, index) in segments"
      :key="index"
      :x1="segment.from[0]"
      :y1="segment.from[1]"
      :x2="segment.to[0]"
      :y2="segment.to[1]"
    />
  </g>
</template>

<style scoped>
.rotor-badge line {
  stroke: #111;
  stroke-width: 2.5px;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}
</style>
