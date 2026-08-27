import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import RunControlView from '../views/RunControlView.vue'
import ProtocolsView from '../views/ProtocolsView.vue'
import MonitoringView from '../views/MonitoringView.vue'
import LogsView from '../views/LogsView.vue'
import DevicesView from '../views/DevicesView.vue'
import ExportView from '../views/ExportView.vue'

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
  ],
})

export default router
