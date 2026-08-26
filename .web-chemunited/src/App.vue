<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useNotification } from './composables/useNotification'
import { useRunStatusStore } from './stores/runStatus'

const { message, type, notify, dismiss } = useNotification()
const runStatusStore = useRunStatusStore()

onMounted(() => { runStatusStore.checkActiveRun() })

const REFRESH_SUCCESS_KEY = 'chemunited-project-refresh-success'

interface ProjectResponse {
  project_dir: string | null
}

interface ErrorResponse {
  detail?: string | Array<{ msg?: string }>
}

type Theme = 'light' | 'dark'

const storedTheme = localStorage.getItem('chemunited-theme') as Theme | null
const theme = ref<Theme>(
  storedTheme ??
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
)
const isRefreshing = ref(false)

const refreshSuccessMessage = sessionStorage.getItem(REFRESH_SUCCESS_KEY)
if (refreshSuccessMessage) {
  sessionStorage.removeItem(REFRESH_SUCCESS_KEY)
  notify(refreshSuccessMessage, 'success')
}

function applyTheme(value: Theme) {
  document.documentElement.dataset.theme = value
  document.querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', value === 'dark' ? '#071525' : '#f3f7fb')
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem('chemunited-theme', theme.value)
  applyTheme(theme.value)
}

async function responseError(res: Response): Promise<string> {
  try {
    const body = await res.json() as ErrorResponse
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map(error => error.msg)
        .filter((value): value is string => Boolean(value))
      if (messages.length) return messages.join(', ')
    }
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail
  } catch {
    // Fall back to a status-specific message.
  }

  if (res.status === 409) {
    return 'The project cannot be refreshed while an experiment is running.'
  }
  if (res.status === 422) {
    return 'The updated project scripts could not be imported.'
  }
  return `Project refresh failed (HTTP ${res.status}).`
}

async function refreshProject() {
  if (isRefreshing.value) return
  if (!window.confirm(
    'Refresh the project from disk? Unsaved dashboard changes will be discarded.',
  )) return

  isRefreshing.value = true
  try {
    const currentProjectResponse = await fetch('/project/')
    if (!currentProjectResponse.ok) {
      notify(await responseError(currentProjectResponse), 'error')
      return
    }

    const currentProject = await currentProjectResponse.json() as ProjectResponse
    if (!currentProject.project_dir) {
      notify('No project is currently loaded. Open a project before refreshing.', 'info')
      return
    }

    const refreshResponse = await fetch('/project/', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_dir: currentProject.project_dir }),
    })
    if (!refreshResponse.ok) {
      notify(await responseError(refreshResponse), 'error')
      return
    }

    sessionStorage.setItem(
      REFRESH_SUCCESS_KEY,
      'Project refreshed. Updated protocol scripts are now loaded.',
    )
    window.location.assign('/')
  } catch {
    notify('Could not reach the project service. Check that the dashboard API is running.', 'error')
  } finally {
    isRefreshing.value = false
  }
}

applyTheme(theme.value)

const navItems = [
  { to: '/', label: 'Dashboard', icon: 'dashboard' },
  { to: '/run-control', label: 'Run Control', icon: 'run' },
  { to: '/protocols', label: 'Protocols', icon: 'protocols' },
  { to: '/monitoring', label: 'Monitoring', icon: 'monitoring' },
  { to: '/devices', label: 'Devices', icon: 'devices' },
  { to: '/logs', label: 'Logs', icon: 'logs' },
  { to: '/export', label: 'Export', icon: 'export' },
]

</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">
          <img src="/chemunited.ico" alt="" width="30" height="30" />
        </div>
        <div class="brand-copy">
          <strong>Chemunited-Workflow</strong>
          <span>Protocol Execution Layers</span>
        </div>
      </div>

      <nav class="primary-nav" aria-label="Primary navigation">
        <span
          v-for="item in navItems"
          :key="item.to"
        >
        <RouterLink
          :to="item.to"
          :title="item.label"
        >
          <svg v-if="item.icon === 'dashboard'" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="3" y="3" width="7" height="7" rx="2"/>
            <rect x="14" y="3" width="7" height="7" rx="2"/>
            <rect x="3" y="14" width="7" height="7" rx="2"/>
            <rect x="14" y="14" width="7" height="7" rx="2"/>
          </svg>
          <svg v-else-if="item.icon === 'run'" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="9"/>
            <path d="m10 8 6 4-6 4V8Z"/>
          </svg>
          <svg v-else-if="item.icon === 'protocols'" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M7 3h10v4H7zM7 17h10v4H7zM5 12h14M12 7v10"/>
          </svg>
          <svg v-else-if="item.icon === 'monitoring'" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M3 12h4l2-5 4 10 2-5h6"/>
          </svg>
          <svg v-else-if="item.icon === 'devices'" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M7 7h10v10H7z"/>
            <path d="M4 10H2M4 14H2M22 10h-2M22 14h-2M10 4V2M14 4V2M10 22v-2M14 22v-2"/>
          </svg>
          <svg v-else-if="item.icon === 'export'" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 3v12m0 0-4-4m4 4 4-4"/>
            <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/>
            <path d="M8 8h8M8 12h8M8 16h5"/>
          </svg>
          <span>{{ item.label }}</span>
          <span
            v-if="item.icon === 'run' && runStatusStore.runState !== 'idle'"
            :class="['nav-run-dot', runStatusStore.runState]"
            :aria-label="`Run ${runStatusStore.runState}`"
          />
        </RouterLink>
        </span>
      </nav>

      <div class="sidebar-footer">
        <button
          type="button"
          class="refresh-button"
          :class="{ loading: isRefreshing }"
          :disabled="isRefreshing"
          :title="isRefreshing ? 'Refreshing project' : 'Refresh project'"
          :aria-label="isRefreshing ? 'Refreshing project' : 'Refresh project'"
          @click="refreshProject"
        >
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M20 7v5h-5"/>
            <path d="M19 12a7 7 0 1 0-2.05 4.95"/>
          </svg>
          <span>{{ isRefreshing ? 'Refreshing…' : 'Refresh project' }}</span>
        </button>
        <a href="/docs" target="_blank" rel="noopener" class="utility-link" title="API Docs">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M14 3h7v7M21 3l-9 9"/>
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
          </svg>
          <span>API Docs</span>
        </a>
        <button
          type="button"
          class="theme-toggle"
          :title="`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`"
          :aria-label="`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`"
          @click="toggleTheme"
        >
          <svg v-if="theme === 'dark'" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="4"/>
            <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M20.2 15.3A8.5 8.5 0 0 1 8.7 3.8 8.5 8.5 0 1 0 20.2 15.3Z"/>
          </svg>
          <span>{{ theme === 'dark' ? 'Light theme' : 'Dark theme' }}</span>
        </button>
      </div>
    </aside>

    <main class="main-content">
      <div v-if="message" class="notif-bar" :class="type" role="status">
        <span class="notif-icon" aria-hidden="true">
          {{ type === 'success' ? '✓' : type === 'error' ? '!' : type === 'warning' ? '⚠' : 'i' }}
        </span>
        <span class="notif-message">{{ message }}</span>
        <button type="button" class="dismiss" aria-label="Dismiss notification" @click="dismiss">×</button>
      </div>

      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 232px minmax(0, 1fr);
}

.sidebar {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 1.25rem 0.9rem;
  color: #dbe8f2;
  background:
    radial-gradient(circle at 25% 0%, rgba(39, 139, 202, 0.18), transparent 28%),
    var(--color-sidebar);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.brand {
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0 0.55rem;
  margin-bottom: 1.65rem;
}

.brand-mark {
  width: 38px;
  height: 38px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  color: #62c7de;
  border: 1px solid rgba(98, 199, 222, 0.28);
  border-radius: 11px;
  background: rgba(98, 199, 222, 0.08);
}

.brand-mark svg {
  width: 30px;
  height: 30px;
}

.brand-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.brand-copy strong {
  color: #ffffff;
  font-size: 1.05rem;
  font-weight: 750;
  letter-spacing: 0.12em;
}

.brand-copy span {
  margin-top: 0.22rem;
  color: var(--color-sidebar-muted);
  font-size: 0.67rem;
  white-space: nowrap;
}

.primary-nav {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.3rem;
}

.primary-nav a,
.nav-disabled,
.utility-link,
.refresh-button,
.theme-toggle {
  width: 100%;
  min-height: 43px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 0.75rem;
  color: var(--color-sidebar-muted);
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  transition:
    color 160ms ease,
    background-color 160ms ease,
    border-color 160ms ease;
}

.primary-nav a:hover,
.utility-link:hover,
.refresh-button:hover:not(:disabled),
.theme-toggle:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.06);
}

.primary-nav a {
  position: relative;
}

.primary-nav > span {
  display: contents;
}

.nav-disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.primary-nav a.router-link-active {
  color: #ffffff;
  border-color: rgba(92, 189, 225, 0.18);
  background: linear-gradient(90deg, rgba(37, 132, 190, 0.28), rgba(37, 132, 190, 0.1));
}

.primary-nav a.router-link-active::before {
  position: absolute;
  left: -0.9rem;
  width: 3px;
  height: 22px;
  content: '';
  border-radius: 0 3px 3px 0;
  background: #53bdd7;
}

.primary-nav svg,
.nav-disabled svg,
.utility-link svg,
.refresh-button svg,
.theme-toggle svg {
  width: 19px;
  height: 19px;
  flex: 0 0 auto;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.primary-nav a span,
.nav-disabled span,
.utility-link span,
.refresh-button span,
.theme-toggle span {
  font-size: 0.84rem;
  font-weight: 580;
}

.sidebar-footer {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding-top: 1rem;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.refresh-button,
.theme-toggle {
  text-align: left;
}

.refresh-button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.refresh-button.loading svg {
  animation: refresh-spin 800ms linear infinite;
}

@keyframes refresh-spin {
  to {
    transform: rotate(360deg);
  }
}

.main-content {
  min-width: 0;
  padding: clamp(1.35rem, 3vw, 2.75rem);
}

.notif-bar {
  position: sticky;
  top: 1rem;
  z-index: 20;
  max-width: 1480px;
  display: flex;
  align-items: flex-start;
  gap: 0.7rem;
  margin: 0 auto 1rem;
  padding: 0.75rem 0.85rem;
  font-size: 0.875rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  box-shadow: var(--shadow-md);
}

.notif-icon {
  width: 22px;
  height: 22px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 800;
}

.notif-message {
  white-space: pre-line;
  max-height: 40vh;
  overflow-y: auto;
}

.notif-bar.error {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 24%, var(--color-border));
  background: var(--color-danger-soft);
}

.notif-bar.error .notif-icon {
  color: #ffffff;
  background: var(--color-danger);
}

.notif-bar.success {
  color: var(--color-success);
  border-color: color-mix(in srgb, var(--color-success) 24%, var(--color-border));
  background: var(--color-success-soft);
}

.notif-bar.success .notif-icon {
  color: #ffffff;
  background: var(--color-success);
}

.notif-bar.info {
  color: var(--color-text);
}

.notif-bar.info .notif-icon {
  color: #ffffff;
  background: var(--color-primary);
}

.notif-bar.warning {
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 24%, var(--color-border));
  background: var(--color-warning-soft);
}

.notif-bar.warning .notif-icon {
  color: #ffffff;
  background: var(--color-warning);
}

.dismiss {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  margin-left: auto;
  padding: 0;
  color: currentColor;
  border: 0;
  border-radius: 7px;
  background: transparent;
  cursor: pointer;
  font-size: 1.25rem;
  opacity: 0.6;
}

.dismiss:hover {
  opacity: 1;
  background: color-mix(in srgb, currentColor 8%, transparent);
}

@media (max-width: 960px) {
  .app-shell {
    grid-template-columns: 72px minmax(0, 1fr);
  }

  .sidebar {
    padding-inline: 0.65rem;
  }

  .brand {
    justify-content: center;
    padding: 0;
  }

  .brand-copy,
  .primary-nav a span,
  .nav-disabled span,
  .utility-link span,
  .refresh-button span,
  .theme-toggle span {
    display: none;
  }

  .primary-nav a,
  .utility-link,
  .refresh-button,
  .theme-toggle {
    justify-content: center;
    padding-inline: 0;
  }

  .primary-nav a.router-link-active::before {
    left: -0.65rem;
  }
}

@media (max-width: 640px) {
  .app-shell {
    display: block;
    padding-bottom: 68px;
  }

  .sidebar {
    position: fixed;
    top: auto;
    right: 0;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 68px;
    display: grid;
    grid-template-columns: 1fr auto;
    padding: 0.45rem 0.6rem;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    border-right: 0;
  }

  .brand,
  .utility-link {
    display: none;
  }

  .primary-nav {
    min-width: 0;
    display: grid;
    grid-template-columns: repeat(7, minmax(40px, 1fr));
    gap: 0.15rem;
  }

  .primary-nav a,
  .nav-disabled {
    min-height: 54px;
    flex-direction: column;
    justify-content: center;
    gap: 0.15rem;
    padding: 0.25rem;
  }

  .primary-nav a.router-link-active::before {
    top: -0.45rem;
    left: 50%;
    width: 24px;
    height: 3px;
    transform: translateX(-50%);
    border-radius: 0 0 3px 3px;
  }

  .primary-nav a span,
  .nav-disabled span {
    display: block;
    font-size: 0.58rem;
  }

  .primary-nav svg,
  .nav-disabled svg {
    width: 18px;
    height: 18px;
  }

  .sidebar-footer {
    display: flex;
    flex-direction: row;
    gap: 0.15rem;
    padding: 0;
    border: 0;
  }

  .refresh-button,
  .theme-toggle {
    width: 40px;
    height: 54px;
    min-height: 54px;
  }

  .main-content {
    padding: 1.15rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .refresh-button.loading svg {
    animation: none;
  }

  .nav-run-dot.running {
    animation: none;
  }
}

/* ── Nav run-status dot ─────────────────────────────── */
.nav-run-dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  margin-left: auto;
  border-radius: 50%;
}

.nav-run-dot.running   { background: #53bdd7; animation: nav-dot-pulse 1.5s ease-in-out infinite; }
.nav-run-dot.paused    { background: var(--color-warning); }
.nav-run-dot.finished  { background: #4fd2a1; }
.nav-run-dot.failed    { background: #ff8893; }
.nav-run-dot.cancelled { background: #8fa5ba; }

@keyframes nav-dot-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}

/* At collapsed width spans are hidden — override for the dot only */
@media (max-width: 960px) {
  .primary-nav a span.nav-run-dot {
    display: block;
    position: absolute;
    top: 7px;
    right: 7px;
    margin-left: 0;
  }
}

/* Bottom nav: dot above icon, centred */
@media (max-width: 640px) {
  .primary-nav a span.nav-run-dot {
    top: 5px;
    right: 6px;
  }
}
</style>
