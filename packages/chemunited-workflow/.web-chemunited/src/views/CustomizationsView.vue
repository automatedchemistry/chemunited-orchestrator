<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  formatProblem,
  sessionProblems,
  toProblems,
  type ExtensionProblem,
} from '../extensions/errors'
import { customization, UI_API_VERSION } from '../extensions/manifest'

/**
 * Diagnostics for the project's customizations/ui/: problems in ui_hook.py,
 * a compile check of every declared .vue file, and what is applied where.
 */

interface FileCheck {
  state: 'checking' | 'ok' | 'failed'
  problems: ExtensionProblem[]
}

const manifest = computed(() => customization.manifest)
const checks = reactive<Record<string, FileCheck>>({})
const checking = ref(false)

const files = computed(() => {
  const seen = new Map<string, { file: string, url: string, use: string }>()
  for (const page of manifest.value.pages) {
    if (page.kind === 'vue') seen.set(page.component, { file: page.component, url: page.component_url, use: `page ${page.path}` })
  }
  for (const widget of manifest.value.widgets) {
    if (!seen.has(widget.component)) {
      seen.set(widget.component, { file: widget.component, url: widget.component_url, use: `widget in ${widget.slot}` })
    }
  }
  return [...seen.values()]
})

const mode = computed(() => {
  if (manifest.value.override_active) {
    return 'Full override: customizations/ui/dist/ replaces the dashboard, so ui_hook.py is not applied.'
  }
  if (manifest.value.active) return 'Runtime customizations from customizations/ui/ui_hook.py.'
  return 'No customizations: this project has no customizations/ui/ui_hook.py.'
})

// ui_hook.py problems, plus each file failing its check or while running.
const problemCount = computed(() => {
  const failing = new Set(sessionProblems.keys())
  for (const [file, check] of Object.entries(checks)) {
    if (check.state === 'failed') failing.add(file)
  }
  return manifest.value.errors.length + failing.size
})

async function checkAll() {
  if (checking.value) return
  checking.value = true
  try {
    const { loadExtensionComponent } = await import('../extensions/loader/moduleGraph')
    for (const { file, url } of files.value) {
      checks[file] = { state: 'checking', problems: [] }
      try {
        await loadExtensionComponent(url)
        checks[file] = { state: 'ok', problems: [] }
      } catch (error) {
        checks[file] = { state: 'failed', problems: toProblems(error, file) }
      }
    }
  } finally {
    checking.value = false
  }
}

onMounted(checkAll)
</script>

<template>
  <div class="page-shell customizations">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Project</p>
        <h1 class="page-title">Customizations</h1>
        <p class="page-description">{{ mode }}</p>
      </div>
      <button type="button" class="cu-button" :disabled="checking" @click="checkAll">
        {{ checking ? 'Checking…' : 'Check again' }}
      </button>
    </header>

    <section class="cu-panel">
      <h2 class="cu-panel-title">Status</h2>
      <p class="cu-muted">
        Dashboard UI API {{ UI_API_VERSION }} · ui_hook.py asks for {{ manifest.requires_ui_api }} ·
        {{ problemCount }} {{ problemCount === 1 ? 'problem' : 'problems' }}
      </p>
      <p v-if="customization.loadError" class="bad">{{ customization.loadError }}</p>
    </section>

    <section v-if="manifest.errors.length" class="cu-panel">
      <h2 class="cu-panel-title">ui_hook.py</h2>
      <ul class="list">
        <li v-for="(error, index) in manifest.errors" :key="index" class="bad">
          <code>{{ error.line ? `${error.source}:${error.line}` : error.source }}</code> {{ error.message }}
        </li>
      </ul>
    </section>

    <section class="cu-panel">
      <h2 class="cu-panel-title">Files</h2>
      <p v-if="!files.length" class="cu-muted">No .vue pages or widgets are declared.</p>
      <ul v-else class="list">
        <li v-for="entry in files" :key="entry.file">
          <span
            class="state"
            :class="checks[entry.file]?.state ?? 'checking'"
            :aria-label="checks[entry.file]?.state ?? 'checking'"
          >{{ checks[entry.file]?.state === 'ok' ? '✓' : checks[entry.file]?.state === 'failed' ? '✗' : '…' }}</span>
          <code>{{ entry.file }}</code> <span class="cu-muted">{{ entry.use }}</span>
          <ul v-if="checks[entry.file]?.problems.length" class="list nested">
            <li v-for="p in checks[entry.file]!.problems" :key="formatProblem(p)" class="bad">
              <code>{{ formatProblem(p) }}</code>
            </li>
          </ul>
        </li>
      </ul>
    </section>

    <section v-if="sessionProblems.size" class="cu-panel">
      <h2 class="cu-panel-title">Problems while running, this session</h2>
      <ul class="list">
        <template v-for="[file, problems] in sessionProblems" :key="file">
          <li v-for="p in problems" :key="formatProblem(p)" class="bad"><code>{{ formatProblem(p) }}</code></li>
        </template>
      </ul>
    </section>

    <section class="cu-panel">
      <h2 class="cu-panel-title">Applied</h2>
      <dl class="applied">
        <dt>Pages</dt>
        <dd>
          <span v-if="!manifest.pages.length" class="cu-muted">none</span>
          <span v-for="page in manifest.pages" :key="page.path" class="chip">
            <RouterLink :to="page.path">{{ page.label }}</RouterLink>
            <span class="cu-muted"> {{ page.path }}{{ page.replaces ? ' (replaces built-in)' : '' }}</span>
          </span>
        </dd>
        <dt>Actions</dt>
        <dd>
          <span v-if="!manifest.actions.length" class="cu-muted">none</span>
          <span v-for="action in manifest.actions" :key="action.id" class="chip">
            {{ action.label }} <span class="cu-muted">→ {{ action.route }}() on {{ action.page }}</span>
          </span>
        </dd>
        <dt>Widgets</dt>
        <dd>
          <span v-if="!manifest.widgets.length" class="cu-muted">none</span>
          <span v-for="widget in manifest.widgets" :key="widget.component_url" class="chip">
            <code>{{ widget.component }}</code> <span class="cu-muted">in {{ widget.slot }}</span>
          </span>
        </dd>
        <dt>Theme</dt>
        <dd><code v-if="manifest.theme_css_url">{{ manifest.theme_css_url }}</code><span v-else class="cu-muted">none</span></dd>
      </dl>
    </section>

    <section class="cu-panel">
      <h2 class="cu-panel-title">Slots</h2>
      <dl class="applied">
        <template v-for="(description, name) in manifest.slots" :key="name">
          <dt><code>{{ name }}</code></dt>
          <dd class="cu-muted">{{ description }}</dd>
        </template>
      </dl>
    </section>

    <section class="cu-panel">
      <h2 class="cu-panel-title">Tips</h2>
      <ul class="list cu-muted">
        <li>Edit files under <code>customizations/ui/</code> and reload the page; nothing needs building.</li>
        <li>Lint with <code>pip install "chemunited-workflow[ui-lint]"</code> and <code>chemunited-workflow ui check &lt;project&gt;</code>.</li>
        <li>Types are stripped, not checked: a page only fails when it runs, so open each page after a change.</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.customizations .cu-panel {
  margin-bottom: 1rem;
}

.list {
  margin: 0;
  padding-left: 1.1rem;
  display: grid;
  gap: 0.4rem;
}

.list.nested {
  margin-top: 0.3rem;
}

.bad {
  color: var(--color-danger);
}

.state {
  display: inline-block;
  width: 1.2rem;
  font-weight: 800;
}

.state.ok {
  color: var(--color-success);
}

.state.failed {
  color: var(--color-danger);
}

.state.checking {
  color: var(--color-text-muted);
}

.applied {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 0.5rem 1rem;
  margin: 0;
}

.applied dt {
  color: var(--color-heading);
  font-weight: 650;
}

.applied dd {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1rem;
  margin: 0;
}

.chip a {
  color: var(--color-primary);
  font-weight: 600;
}

code {
  font-size: 0.82rem;
}
</style>
