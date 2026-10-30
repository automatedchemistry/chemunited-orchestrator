import type { Router } from 'vue-router'
import CustomPageView from '../views/CustomPageView.vue'
import HtmlPageView from '../views/HtmlPageView.vue'
import { customization, fetchManifest } from './manifest'
import { installRuntime } from './runtime'

const BUILTIN_ROUTE_NAMES: Record<string, string> = {
  '/': 'dashboard',
  '/run-control': 'run-control',
  '/protocols': 'protocols',
  '/monitoring': 'monitoring',
  '/devices': 'devices',
  '/logs': 'logs',
  '/export': 'export',
}

/**
 * Apply the project's customizations/ui/ui_hook.py before the app mounts:
 * theme, document title, and the routes of its pages. Never throws; if the
 * manifest can't be fetched the dashboard runs uncustomized.
 */
export async function bootstrapCustomizations(router: Router): Promise<void> {
  installRuntime()
  await fetchManifest()
  const { manifest } = customization
  if (manifest.override_active) return

  if (manifest.brand?.title) document.title = manifest.brand.title
  if (manifest.theme_css_url) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = manifest.theme_css_url
    link.dataset.customization = 'theme'
    // Last in <head>, so its tokens win over the dashboard's own.
    document.head.appendChild(link)
  }

  for (const page of manifest.pages) {
    const builtin = BUILTIN_ROUTE_NAMES[page.path]
    if (page.replaces && builtin && router.hasRoute(builtin)) router.removeRoute(builtin)
    router.addRoute({
      path: page.path,
      name: builtin ?? `custom:${page.path}`,
      component: page.kind === 'vue' ? CustomPageView : HtmlPageView,
      props: { spec: page },
    })
  }
}
