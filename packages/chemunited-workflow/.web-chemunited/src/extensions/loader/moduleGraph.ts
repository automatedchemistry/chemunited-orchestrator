import type { Component } from 'vue'
import { init, parse } from 'es-module-lexer'
import { ExtensionError, problem, type ExtensionProblem } from '../errors'
import { RUNTIME_GLOBAL } from '../runtime'
import { compileSfc } from './compileSfc'

/**
 * Loads customization files (served by GET /ui/ext/...) as ES modules in the
 * browser, with no build step: .vue files are compiled, then every module's
 * imports are rewritten so that
 *
 *   - `vue`, `vue-router`, `pinia` and `chemunited` resolve to the dashboard's
 *     own instances (through shim modules reading the runtime registry),
 *   - relative .vue/.js imports load the same way, recursively,
 *   - files under a vendor/ folder are imported natively, untouched
 *     (single-file browser builds of third-party libraries),
 *   - a relative .css import adds a stylesheet.
 *
 * Each module becomes a blob: URL. Files are revalidated (ETag) on every load,
 * so an edited file shows on the next page load while unchanged ones are
 * neither re-fetched nor recompiled.
 */

const EXT_PREFIX = '/ui/ext/'
const SHARED = new Set(['vue', 'vue-router', 'pinia', 'chemunited'])

interface CachedModule {
  etag: string
  /** Compiled JS before its imports are rewritten. */
  code: string
  css: string
  /** The rewritten module's source, and the blob: URL it is served from. */
  rewritten: string
  url: string
}

const modules = new Map<string, CachedModule>()
const shims = new Map<string, string>()
let lexerReady: Promise<void> | null = null

/** Path under customizations/ui/ for a /ui/ext/ URL. */
export function extPath(url: string): string {
  const { pathname } = new URL(url, location.origin)
  return pathname.startsWith(EXT_PREFIX) ? decodeURIComponent(pathname.slice(EXT_PREFIX.length)) : pathname
}

function blobUrl(source: string, name: string): string {
  const text = `${source}\n//# sourceURL=${name}\n`
  return URL.createObjectURL(new Blob([text], { type: 'text/javascript' }))
}

/** Short, stable id for a file's scoped styles. */
function scopeId(file: string): string {
  let hash = 0x811c9dc5
  for (let i = 0; i < file.length; i++) {
    hash ^= file.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

function lineOf(text: string, index: number): number {
  let line = 1
  for (let i = 0; i < index && i < text.length; i++) if (text.charCodeAt(i) === 10) line++
  return line
}

function shimUrl(specifier: string): string {
  let url = shims.get(specifier)
  if (url) return url
  const registry = (globalThis as Record<string, unknown>)[RUNTIME_GLOBAL] as Record<string, object>
  const names = Object.keys(registry[specifier]!)
    .filter(name => name !== 'default' && /^[A-Za-z_$][\w$]*$/.test(name))
  const source = [
    `const m = globalThis.${RUNTIME_GLOBAL}[${JSON.stringify(specifier)}];`,
    ...names.map(name => `export const ${name} = m[${JSON.stringify(name)}];`),
    'export default (m.default ?? m);',
  ].join('\n')
  url = blobUrl(source, `chemunited:${specifier}`)
  shims.set(specifier, url)
  return url
}

const emptyModule = (() => {
  let url: string | null = null
  return () => (url ??= blobUrl('export {}', 'chemunited:empty'))
})()

function addStylesheet(href: string) {
  if (document.head.querySelector(`link[data-customization-href="${CSS.escape(href)}"]`)) return
  const link = document.createElement('link')
  link.rel = 'stylesheet'
  link.href = href
  link.dataset.customizationHref = href
  document.head.appendChild(link)
}

function setComponentStyle(file: string, css: string) {
  const selector = `style[data-customization-file="${CSS.escape(file)}"]`
  let style = document.head.querySelector<HTMLStyleElement>(selector)
  if (!css) {
    style?.remove()
    return
  }
  if (!style) {
    style = document.createElement('style')
    style.dataset.customizationFile = file
    document.head.appendChild(style)
  }
  if (style.textContent !== css) style.textContent = css
}

type Session = Map<string, Promise<string>>

async function rewriteImports(code: string, source: string, url: string, stack: string[], session: Session): Promise<string> {
  const file = extPath(url)
  let imports
  try {
    [imports] = parse(code)
  } catch (error) {
    throw new ExtensionError([problem(file, `could not read its imports: ${(error as Error).message}`)])
  }
  const problems: ExtensionProblem[] = []
  const where = (specifier: string) => {
    const index = source.indexOf(specifier)
    return index < 0 ? null : lineOf(source, index)
  }

  let out = ''
  let last = 0
  for (const entry of imports) {
    if (entry.type === 'import-meta' || entry.specifier === undefined) continue
    if (entry.type === 'dynamic' && entry.glob) continue
    const specifier = entry.specifier
    let target: string | null = null

    if (SHARED.has(specifier)) {
      target = shimUrl(specifier)
    } else if (/^\.{0,2}\//.test(specifier)) {
      const resolved = new URL(specifier, url)
      const path = resolved.pathname
      if (resolved.origin !== location.origin || !path.startsWith(EXT_PREFIX)) {
        problems.push(problem(file, `imports '${specifier}', which is outside customizations/ui/`, where(specifier)))
      } else if (path.endsWith('.vue')) {
        target = await loadModule(resolved.href, [...stack, url], session)
      } else if (path.endsWith('.js') || path.endsWith('.mjs')) {
        target = path.includes('/vendor/')
          ? resolved.href
          : await loadModule(resolved.href, [...stack, url], session)
      } else if (path.endsWith('.css')) {
        addStylesheet(resolved.href)
        target = emptyModule()
      } else {
        problems.push(problem(file, `can't import '${specifier}': only .vue, .js, .mjs and .css files`, where(specifier)))
      }
    } else {
      problems.push(problem(
        file,
        `imports '${specifier}', which isn't available: only vue, vue-router, pinia and chemunited ` +
        'can be imported by name. Put a single-file browser build under vendor/ and import it by relative path.',
        where(specifier),
      ))
    }
    if (target === null) continue
    const replacement = entry.type === 'dynamic' ? JSON.stringify(target) : target
    out += code.slice(last, entry.start) + replacement
    last = entry.end
  }
  if (problems.length) throw new ExtensionError(problems)
  return out + code.slice(last)
}

async function build(url: string, stack: string[], session: Session): Promise<string> {
  const file = extPath(url)
  if (stack.includes(url)) {
    const loop = [...stack.slice(stack.indexOf(url)), url].map(extPath).join(' → ')
    throw new ExtensionError([problem(file, `imports itself through ${loop}`)])
  }
  let response: Response
  try {
    response = await fetch(url, { cache: 'no-cache' })
  } catch (error) {
    throw new ExtensionError([problem(file, `could not be fetched: ${(error as Error).message}`)])
  }
  if (!response.ok) {
    throw new ExtensionError([problem(file, response.status === 404 ? 'file not found' : `HTTP ${response.status}`)])
  }
  const etag = response.headers.get('etag') ?? ''
  const source = await response.text()

  let cached = modules.get(url)
  if (!cached || !etag || cached.etag !== etag) {
    let code = source
    let css = ''
    if (url.endsWith('.vue')) {
      const compiled = compileSfc(source, file, scopeId(file))
      if (compiled.problems.length) throw new ExtensionError(compiled.problems)
      code = compiled.code
      css = compiled.css
    }
    cached = { etag, code, css, rewritten: '', url: '' }
  }
  const rewritten = await rewriteImports(cached.code, source, url, stack, session)
  if (rewritten !== cached.rewritten) {
    cached.rewritten = rewritten
    cached.url = blobUrl(rewritten, url)
  }
  modules.set(url, cached)
  setComponentStyle(file, cached.css)
  return cached.url
}

function loadModule(url: string, stack: string[], session: Session): Promise<string> {
  // An import cycle would wait on itself; build() reports it instead.
  if (stack.includes(url)) return build(url, stack, session)
  let pending = session.get(url)
  if (!pending) {
    pending = build(url, stack, session)
    session.set(url, pending)
  }
  return pending
}

/** Load a customization file and return the component it exports by default. */
export async function loadExtensionComponent(url: string): Promise<Component> {
  lexerReady ??= init()
  await lexerReady
  const absolute = new URL(url, location.origin).href
  const moduleUrl = await loadModule(absolute, [], new Map())
  let exported: { default?: Component }
  try {
    exported = await import(/* @vite-ignore */ moduleUrl) as { default?: Component }
  } catch (error) {
    throw new ExtensionError([problem(extPath(absolute), `failed to run: ${(error as Error).message}`)])
  }
  if (!exported.default) {
    throw new ExtensionError([problem(extPath(absolute), 'has no default export to use as a component')])
  }
  return exported.default
}
