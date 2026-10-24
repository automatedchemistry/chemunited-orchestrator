<script setup lang="ts">
import { computed } from 'vue'
import type { Box } from './liveFormat'

// The status badge of a solenoid valve (open/closed), a 2-way solenoid valve
// (position 1/2) or an MFC (active/idle), drawn as the desktop app draws it.
const props = defineProps<{ kind: string, box: Box, picture: Record<string, unknown> }>()

const shape = computed(() => {
  const [x, y, w, h] = props.box
  const cx = x + w / 2
  const cy = y + h / 2
  const arm = Math.min(w, h) / 3
  if (props.kind === 'mfc') {
    return { tint: props.picture.active ? 'mfc-active' : 'mfc-idle', marks: [] }
  }
  if (props.kind === 'two-way') {
    const first = props.picture.position === 1
    return {
      tint: first ? 'switch-open' : 'switch-other',
      marks: [first
        ? [cx - arm, cy, cx + arm, cy]
        : [cx, cy - arm, cx, cy + arm]],
    }
  }
  const open = props.picture.open === true
  return {
    tint: open ? 'switch-open' : 'switch-closed',
    marks: open
      ? [[cx - arm, cy, cx + arm, cy]]
      : [[cx - arm, cy - arm, cx + arm, cy + arm], [cx - arm, cy + arm, cx + arm, cy - arm]],
  }
})
</script>

<template>
  <g class="switch-badge">
    <rect
      :class="shape.tint"
      :x="box[0]"
      :y="box[1]"
      :width="box[2]"
      :height="box[3]"
      :rx="Math.min(box[2], box[3]) * 0.27"
    />
    <line
      v-for="(mark, index) in shape.marks"
      :key="index"
      :x1="mark[0]"
      :y1="mark[1]"
      :x2="mark[2]"
      :y2="mark[3]"
    />
  </g>
</template>

<style scoped>
.switch-open { fill: #00c853; }
.switch-closed { fill: #e53935; }
.switch-other { fill: #ff9800; }
.mfc-active { fill: rgb(0 200 83 / 47%); }
.mfc-idle { fill: rgb(158 158 158 / 31%); }

.switch-badge line {
  stroke: #fff;
  stroke-width: 2px;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}
</style>
