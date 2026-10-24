<script setup lang="ts">
import { computed } from 'vue'
import { fitText, type Box } from './liveFormat'

// An LCD placed in the desktop app: always black, with green text. `value`
// is the text to show ("24.35 °C", "--", "not monitored"); `title` says why
// when it shows no reading.
const props = defineProps<{ box: Box, name: string, value: string, title: string, dim?: boolean }>()

const layout = computed(() => {
  const [x, y, w, h] = props.box
  const nameSize = h * 0.19
  const inset = h * 0.15
  // The value shrinks to fit the LCD, and is only cut below a readable size.
  const fitted = (w - 2 * inset) / (Math.max(props.value.length, 1) * 0.62)
  const valueSize = Math.max(Math.min(h * 0.42, fitted), h * 0.22)
  return {
    nameX: x + inset,
    nameY: y + inset + nameSize * 0.8,
    nameSize,
    valueX: x + w / 2,
    valueY: y + h * 0.66,
    valueSize,
    name: fitText(props.name, w - 2 * inset, nameSize),
    value: fitText(props.value, w - 2 * inset, valueSize),
  }
})
</script>

<template>
  <g class="lcd-badge" :class="{ 'is-dim': dim }">
    <title>{{ title ? `${name}: ${title}` : name }}</title>
    <rect :x="box[0]" :y="box[1]" :width="box[2]" :height="box[3]" :rx="box[3] * 0.12" />
    <text class="lcd-name" :x="layout.nameX" :y="layout.nameY" :font-size="layout.nameSize">
      {{ layout.name }}
    </text>
    <text
      class="lcd-value"
      :x="layout.valueX"
      :y="layout.valueY"
      :font-size="layout.valueSize"
      text-anchor="middle"
      dominant-baseline="middle"
    >
      {{ layout.value }}
    </text>
  </g>
</template>

<style scoped>
.lcd-badge {
  pointer-events: auto;
}

.lcd-badge rect {
  fill: #000;
}

.lcd-badge text {
  fill: #39ff6a;
}

.lcd-name {
  font-family: inherit;
}

.lcd-value {
  font-family: Consolas, 'SFMono-Regular', Menlo, monospace;
  font-weight: 700;
}

.is-dim .lcd-value {
  opacity: 0.6;
}
</style>
