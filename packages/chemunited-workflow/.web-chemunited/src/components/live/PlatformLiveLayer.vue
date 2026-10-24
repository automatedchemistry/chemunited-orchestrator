<script setup lang="ts">
import { computed } from 'vue'
import type {
  LiveConnection,
  LiveDevice,
  LiveDisplay,
} from '../../composables/usePlatformLive'
import BusyRing from './BusyRing.vue'
import LcdBadge from './LcdBadge.vue'
import LedBadge from './LedBadge.vue'
import RotorBadge from './RotorBadge.vue'
import SwitchBadge from './SwitchBadge.vue'
import {
  boxCenter,
  commandText,
  fitText,
  formatLcdValue,
  type Box,
  type LiveMap,
  type LivePart,
  type Point,
} from './liveFormat'

// Drawn inside the platform <svg> (teleported into a layer next to the click
// boxes), so pan, zoom and Find move it with the drawing. `map` is the
// desktop export's map of the live parts, or null when it is missing or no
// longer matches the SVG: then only running rings and command text are drawn,
// on the device boxes of platform-devices.json.
const props = defineProps<{
  live: boolean
  connection: LiveConnection
  devices: Record<string, LiveDevice>
  displays: Record<string, LiveDisplay>
  flashing: ReadonlySet<string>
  map: LiveMap | null
  boxes: Record<string, Box>
}>()

const stale = computed(() => props.connection === 'disconnected')

function unknownAt(part: LivePart | undefined, box: Box): Point {
  if (part?.rotor) return part.rotor.center
  if (part?.badge) return boxCenter(part.badge.box)
  const lights = part?.lights?.points
  if (lights?.length) return lights[Math.floor(lights.length / 2)]!
  return boxCenter(box)
}

const deviceItems = computed(() => {
  if (!props.live) return []
  return Object.entries(props.devices).flatMap(([name, device]) => {
    const part = props.map?.parts[name]
    const box = part?.figure ?? props.boxes[name]
    if (!box) return []
    const running = device.status === 'running'
    const picture = props.map && device.picture ? device.picture : null
    // "?" where the state isn't known: a failed command, or a device the
    // picture can't be drawn for yet. Devices without a picture show nothing
    // until they fail, to keep the drawing quiet.
    const unknown = !running && (device.status === 'failed' || (device.kind !== null && !picture))
    const textSize = Math.min(Math.max(Math.min(box[2], box[3]) * 0.2, 14), 40)
    return [{
      name,
      box,
      running,
      flash: props.flashing.has(name),
      label: running && device.command
        ? fitText(commandText(device.command), Math.max(box[2] * 2.2, textSize * 12), textSize)
        : '',
      textSize,
      kind: device.kind,
      part,
      picture,
      unknown: unknown ? { at: unknownAt(part, box), r: textSize * 0.7 } : null,
    }]
  })
})

function lcdText(name: string): { value: string, title: string, dim: boolean } {
  const display = props.displays[name]
  if (!props.live) return { value: '--', title: 'The platform view is not live: start monitoring.', dim: true }
  if (stale.value) return { value: '--', title: 'Disconnected from the work-server.', dim: true }
  if (!display) return { value: '--', title: 'No reading yet.', dim: true }
  if (!display.monitored) {
    return { value: 'not monitored', title: 'Add this variable on the Monitoring page.', dim: true }
  }
  if (display.error) return { value: '--', title: `The last reading failed: ${display.error}`, dim: true }
  if (display.value === null) return { value: '--', title: 'No reading yet.', dim: true }
  return { value: formatLcdValue(display.value), title: '', dim: false }
}

const lcdItems = computed(() => Object.entries(props.map?.displays ?? {}).map(
  ([name, display]) => ({ name, box: display.box, ...lcdText(name) }),
))
</script>

<template>
  <g class="platform-live" :class="{ 'is-stale': stale }">
    <g v-for="item in deviceItems" :key="item.name">
      <RotorBadge
        v-if="item.picture && item.kind === 'rotor' && item.part?.rotor"
        :center="item.part.rotor.center"
        :slots="item.part.rotor.slots"
        :links="item.picture.links"
      />
      <SwitchBadge
        v-else-if="item.picture && item.kind && item.part?.badge"
        :kind="item.kind"
        :box="item.part.badge.box"
        :picture="item.picture"
      />
      <LedBadge
        v-else-if="item.picture && item.kind === 'relay' && item.part?.lights"
        :points="item.part.lights.points"
        :r="item.part.lights.r"
        :channels="item.picture.channels"
      />
      <g v-if="item.unknown" class="unknown-mark">
        <circle :cx="item.unknown.at[0]" :cy="item.unknown.at[1]" :r="item.unknown.r" />
        <text
          :x="item.unknown.at[0]"
          :y="item.unknown.at[1]"
          :font-size="item.unknown.r * 1.4"
          text-anchor="middle"
          dominant-baseline="central"
        >?</text>
      </g>
      <BusyRing v-if="item.running" :box="item.box" />
      <BusyRing v-else-if="item.flash" :box="item.box" flash />
      <text
        v-if="item.label"
        class="command-text"
        :x="item.box[0] + item.box[2] / 2"
        :y="item.box[1] - item.textSize * 0.6"
        :font-size="item.textSize"
        text-anchor="middle"
      >
        {{ item.label }}
      </text>
    </g>
    <LcdBadge
      v-for="lcd in lcdItems"
      :key="lcd.name"
      :box="lcd.box"
      :name="lcd.name"
      :value="lcd.value"
      :title="lcd.title"
      :dim="lcd.dim"
    />
  </g>
</template>

<style scoped>
.platform-live.is-stale > g:not(.lcd-badge) {
  filter: grayscale(1);
  opacity: 0.5;
}

.unknown-mark circle {
  fill: #9e9e9e;
  stroke: #fff;
  stroke-width: 1.5px;
  vector-effect: non-scaling-stroke;
}

.unknown-mark text {
  fill: #fff;
  font-weight: 760;
}

.command-text {
  fill: var(--color-primary);
  font-weight: 700;
  paint-order: stroke;
  stroke: var(--color-background-soft, #fff);
  stroke-width: 4px;
  stroke-linejoin: round;
}
</style>
