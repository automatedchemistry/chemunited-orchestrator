import type { UiManifest } from './manifest'

export interface NavEntry {
  to: string
  label: string
  /** Built-in icon name, drawn inline by App.vue. */
  icon: string
  /** An icon file from customizations/ui/, drawn in the nav's colour. */
  iconUrl: string | null
  custom: boolean
  order: number
  hidden: boolean
  /** 'footer' entries sit under Refresh project instead of in the main list. */
  section: 'main' | 'footer'
}

const BUILTIN_NAV: Pick<NavEntry, 'to' | 'label' | 'icon' | 'section'>[] = [
  { to: '/', label: 'Dashboard', icon: 'dashboard', section: 'main' },
  { to: '/run-control', label: 'Run Control', icon: 'run', section: 'main' },
  { to: '/protocols', label: 'Protocols', icon: 'protocols', section: 'main' },
  { to: '/monitoring', label: 'Monitoring', icon: 'monitoring', section: 'main' },
  { to: '/devices', label: 'Devices', icon: 'devices', section: 'footer' },
  { to: '/logs', label: 'Logs', icon: 'logs', section: 'main' },
  { to: '/export', label: 'Export', icon: 'export', section: 'main' },
  { to: '/configurations', label: 'Configurations', icon: 'configurations', section: 'footer' },
]

/** When the sidebar lists the Customizations (diagnostics) page. */
export interface DiagnosticsNav {
  /** The project customizes the dashboard, or its customization failed to load. */
  diagnostics: boolean
  /** Something is wrong there: the entry shows even when a nav item hides it. */
  problems: boolean
}

/**
 * The sidebar's entries: the built-in pages (orders 10..80) as changed by the
 * manifest's nav items and replaced pages, plus its custom pages, each placed
 * after the entry named by `after` or at the end. Devices and Configurations
 * keep their orders in the footer, so a custom page after one of them lands
 * where that order falls in the main list. The diagnostics page comes last.
 */
export function buildNav(
  manifest: UiManifest,
  { diagnostics, problems }: DiagnosticsNav = { diagnostics: false, problems: false },
): NavEntry[] {
  const entries = new Map<string, NavEntry>()
  BUILTIN_NAV.forEach((item, index) => {
    entries.set(item.to, { ...item, iconUrl: null, custom: false, order: (index + 1) * 10, hidden: false })
  })
  if (diagnostics) {
    entries.set('/customizations', {
      to: '/customizations',
      label: 'Customizations',
      icon: 'customizations',
      iconUrl: null,
      custom: false,
      order: Number.MAX_SAFE_INTEGER,
      hidden: false,
      section: 'main',
    })
  }
  for (const nav of manifest.nav) {
    const entry = entries.get(nav.path)
    if (!entry) continue
    if (nav.label) entry.label = nav.label
    if (nav.icon_url) entry.iconUrl = nav.icon_url
    if (nav.order !== null) entry.order = nav.order
    entry.hidden = nav.hidden
  }
  // A hidden diagnostics entry still shows while there are problems to read.
  const diagnosticsEntry = entries.get('/customizations')
  if (diagnosticsEntry && problems) diagnosticsEntry.hidden = false

  const customPages = manifest.pages.filter(page => !page.replaces)
  for (const page of manifest.pages) {
    const entry = entries.get(page.path)
    if (page.replaces && entry) {
      entry.label = page.label
      entry.iconUrl = page.icon_url ?? entry.iconUrl
      entry.hidden ||= page.hidden
    }
  }
  for (const page of customPages) {
    entries.set(page.path, {
      to: page.path,
      label: page.label,
      icon: 'custom',
      iconUrl: page.icon_url,
      custom: true,
      order: Number.NaN,
      hidden: page.hidden,
      section: 'main',
    })
  }

  // A custom page sits just after its anchor; pages after the same anchor
  // keep their declaration order. Chains of `after` resolve recursively.
  function orderOf(path: string, seen: Set<string>): number {
    const entry = entries.get(path)!
    if (!Number.isNaN(entry.order)) return entry.order
    const index = customPages.findIndex(page => page.path === path)
    const anchor = customPages[index]?.after
    seen.add(path)
    entry.order = anchor && entries.has(anchor) && !seen.has(anchor)
      ? orderOf(anchor, seen) + (index + 1) / 1000
      : 1000 + index
    return entry.order
  }
  for (const page of customPages) orderOf(page.path, new Set())

  return [...entries.values()]
    .filter(entry => !entry.hidden)
    .sort((a, b) => a.order - b.order)
}
