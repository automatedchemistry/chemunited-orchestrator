<script setup lang="ts">
import { computed, ref } from 'vue'
import { attempt, callCustomRoute, useRunStatus } from 'chemunited'
import StatTile from '../components/StatTile.vue'

const flow = ref(0.5)
const volume = ref(10)
const minutes = ref<number | null>(null)
const { runId, runState } = useRunStatus()

const run = computed(() => (runId.value ? `${runState.value} · ${runId.value.slice(0, 8)}` : 'idle'))

async function calculate() {
  const result = await attempt(
    () => callCustomRoute<number>('residence_time_min', {
      flow_rate_ml_min: flow.value,
      reactor_volume_ml: volume.value,
    }),
    { error: 'Could not calculate the residence time' },
  )
  minutes.value = result ?? null
}
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Example custom page</p>
        <h1 class="page-title">Reactor</h1>
        <p class="page-description">
          A .vue file from customizations/ui/pages/, compiled in the browser. It calls a
          Python function from customizations/routers/router_hook.py.
        </p>
      </div>
    </header>

    <div class="tiles">
      <StatTile label="Run" :value="run" />
      <StatTile
        label="Residence time"
        :value="minutes === null ? '—' : `${minutes.toFixed(1)} min`"
      />
    </div>

    <form class="cu-panel calc" @submit.prevent="calculate">
      <h2 class="cu-panel-title">Residence time</h2>
      <label>
        Flow rate (mL/min)
        <input v-model.number="flow" class="cu-input" type="number" step="any" min="0.001">
      </label>
      <label>
        Reactor volume (mL)
        <input v-model.number="volume" class="cu-input" type="number" step="any" min="0">
      </label>
      <button class="cu-button primary" type="submit">Calculate</button>
    </form>
  </div>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}

.calc {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 1rem;
}

.calc .cu-panel-title {
  flex-basis: 100%;
}

.calc label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  color: var(--color-text-muted);
  font-size: 0.8rem;
  font-weight: 650;
}
</style>
