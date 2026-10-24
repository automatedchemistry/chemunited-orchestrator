<script setup lang="ts">
import { computed } from 'vue'
import type { Point } from './liveFormat'

// A relay's channel lights. A channel nothing has switched since the
// work-server started is unknown, drawn as a dashed outline.
const props = defineProps<{ points: Point[], r: number, channels: unknown }>()

const lights = computed(() => {
  const channels = Array.isArray(props.channels) ? props.channels as unknown[] : []
  return props.points.map((point, index) => {
    const value = channels[index]
    return {
      point,
      state: value === true ? 'is-on' : value === false ? 'is-off' : 'is-unknown',
    }
  })
})
</script>

<template>
  <g class="led-badge">
    <circle
      v-for="(light, index) in lights"
      :key="index"
      :class="light.state"
      :cx="light.point[0]"
      :cy="light.point[1]"
      :r="r"
    />
  </g>
</template>

<style scoped>
.led-badge circle {
  stroke-width: 1.5px;
  vector-effect: non-scaling-stroke;
}

.is-on {
  fill: #8bc34a;
  stroke: #558b2f;
}

.is-off {
  fill: #e8f5e9;
  stroke: #9e9e9e;
}

.is-unknown {
  fill: none;
  stroke: #9e9e9e;
  stroke-dasharray: 2 2;
}
</style>
