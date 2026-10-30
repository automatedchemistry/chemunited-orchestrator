import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import RunControlView from '../views/RunControlView.vue'
import ProtocolsView from '../views/ProtocolsView.vue'
import MonitoringView from '../views/MonitoringView.vue'
import LogsView from '../views/LogsView.vue'
import DevicesView from '../views/DevicesView.vue'
import ExportView from '../views/ExportView.vue'
import NotFoundView from '../views/NotFoundView.vue'

// The project's custom pages are added at start-up (extensions/bootstrap.ts).
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/',           name: 'dashboard',   component: DashboardView },
    { path: '/run-control',name: 'run-control', component: RunControlView },
    { path: '/protocols',  name: 'protocols',   component: ProtocolsView },
    { path: '/monitoring', name: 'monitoring',  component: MonitoringView },
    { path: '/devices',    name: 'devices',     component: DevicesView },
    { path: '/logs',       name: 'logs',        component: LogsView },
    { path: '/export',     name: 'export',      component: ExportView },
    {
      path: '/customizations',
      name: 'customizations',
      component: () => import('../views/CustomizationsView.vue'),
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundView },
  ],
})

export default router
