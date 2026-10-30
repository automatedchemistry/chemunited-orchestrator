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
}

const BUILTIN_NAV: Pick<NavEntry, 'to' | 'label' | 'icon'>[] = [
  { to: '/', label: 'Dashboard', icon: 'dashboard' },
  { to: '/run-control', label: 'Run Control', icon: 'run' },
  { to: '/protocols', label: 'Protocols', icon: 'protocols' },
  { to: '/monitoring', label: 'Monitoring', icon: 'monitoring' },
  { to: '/devices', label: 'Devices', icon: 'devices' },
  { to: '/logs', label: 'Logs', icon: 'logs' },
  { to: '/export', label: 'Export', icon: 'export' },
]

/**
 * The sidebar's entries: the built-in pages (orders 10..70) as changed by the
 * manifest's nav items and replaced pages, plus its custom pages, each placed
 * after the entry named by `after` or at the end.
 */
export function buildNav(manifest: UiManifest): NavEntry[] {
  const entries = new Map<string, NavEntry>()
  BUILTIN_NAV.forEach((item, index) => {
    entries.set(item.to, { ...item, iconUrl: null, custom: false, order: (index + 1) * 10, hidden: false })
  })
  for (const nav of manifest.nav) {
    const entry = entries.get(nav.path)
    if (!entry) continue
    if (nav.label) entry.label = nav.label
    if (nav.icon_url) entry.iconUrl = nav.icon_url
    if (nav.order !== null) entry.order = nav.order
    entry.hidden = nav.hidden
  }

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
