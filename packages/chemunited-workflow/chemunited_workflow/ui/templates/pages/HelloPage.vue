<script setup lang="ts">
import { ref } from 'vue'
import { api, attempt } from 'chemunited'

interface Project {
  project_dir: string | null
}

const projectDir = ref<string | null>(null)

async function load() {
  const project = await attempt(() => api.get<Project>('/project/'), {
    error: 'Could not read the project',
  })
  projectDir.value = project?.project_dir ?? null
}

void load()
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Custom page</p>
        <h1 class="page-title">Hello</h1>
        <p class="page-description">
          customizations/ui/pages/HelloPage.vue, compiled in the browser. Edit it and reload.
        </p>
      </div>
    </header>

    <section class="cu-panel">
      <h2 class="cu-panel-title">Project</h2>
      <p class="cu-muted">{{ projectDir ?? 'Loading…' }}</p>
    </section>
  </div>
</template>
