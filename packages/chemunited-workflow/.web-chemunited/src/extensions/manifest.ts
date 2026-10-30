import { reactive } from 'vue'

/**
 * The project's dashboard customization, as served by GET /ui/manifest from its
 * customizations/ui/ui_hook.py (see chemunited_workflow/ui/models.py).
 */

/** UI API version this dashboard implements; matches the server's UI_API_VERSION. */
export const UI_API_VERSION = 1

export interface FormProperty {
  type?: string
  title?: string
  description?: string
  default?: unknown
  enum?: unknown[]
  minimum?: number
  maximum?: number
  minLength?: number
  maxLength?: number
  placeholder?: string
  items?: { type?: string }
}

export interface BrandSpec {
  title: string | null
  subtitle: string | null
  monogram: string | null
  logo_url: string | null
}

interface PageSpecBase {
  path: string
  label: string
  icon_url: string | null
  after: string | null
  hidden: boolean
  replaces: boolean
}

export interface VuePageSpec extends PageSpecBase {
  kind: 'vue'
  component: string
  component_url: string
}

export interface HtmlPageSpec extends PageSpecBase {
  kind: 'html'
  html_url: string
  refresh_seconds: number | null
}

export type PageSpec = VuePageSpec | HtmlPageSpec

export interface NavSpec {
  path: string
  label: string | null
  hidden: boolean
  order: number | null
  icon_url: string | null
}

export interface ActionSpec {
  id: string
  page: string
  route: string
  label: string
  description: string | null
  icon_url: string | null
  /** Route parameter -> page context key. */
  context: Record<string, string>
  properties: Record<string, FormProperty>
  required: string[]
  remember: string[]
  confirm: string | null
  refresh: boolean
}

export interface WidgetSpec {
  slot: string
  component: string
  component_url: string
  title: string | null
  order: number
}

export interface ManifestError {
  source: string
  line: number | null
  message: string
}

export interface UiManifest {
  ui_api: number
  requires_ui_api: number
  active: boolean
  override_active: boolean
  brand: BrandSpec | null
  theme_css_url: string | null
  pages: PageSpec[]
  nav: NavSpec[]
  actions: ActionSpec[]
  widgets: WidgetSpec[]
  protocols: { process_categories: Record<string, string>, other_label: string }
  slots: Record<string, string>
  errors: ManifestError[]
}

export function emptyManifest(): UiManifest {
  return {
    ui_api: UI_API_VERSION,
    requires_ui_api: UI_API_VERSION,
    active: false,
    override_active: false,
    brand: null,
    theme_css_url: null,
    pages: [],
    nav: [],
    actions: [],
    widgets: [],
    protocols: { process_categories: {}, other_label: 'Other' },
    slots: {},
    errors: [],
  }
}

/** Written once at start-up by bootstrap.ts; read everywhere else. */
export const customization = reactive({
  manifest: emptyManifest(),
  /** Why the manifest couldn't be fetched; the dashboard then runs uncustomized. */
  loadError: '',
})

export async function fetchManifest(): Promise<void> {
  try {
    const response = await fetch('/ui/manifest')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    customization.manifest = { ...emptyManifest(), ...await response.json() as Partial<UiManifest> }
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    customization.loadError = `Could not load the project's dashboard customization (${reason}).`
  }
}
