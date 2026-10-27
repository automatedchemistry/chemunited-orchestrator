import {
  compileScript,
  compileStyle,
  compileTemplate,
  parse,
  type SFCBlock,
  type SFCDescriptor,
} from 'vue/compiler-sfc'
import { transform } from 'sucrase'
import { problem, type ExtensionProblem } from '../errors'

/**
 * Compile a .vue file in the browser with Vue's own compiler (the same version
 * as the dashboard's runtime), the way the official Vue SFC Playground does.
 * TypeScript is stripped, not checked.
 */

const COMPONENT = '__sfc__'

export interface CompiledSfc {
  /** An ES module whose default export is the component. */
  code: string
  css: string
  problems: ExtensionProblem[]
}

interface LocatedError {
  message?: string
  loc?: { line?: number, column?: number, start?: { line: number, column: number } }
  line?: number
  column?: number
  reason?: string
}

/** First line of a compiler message, without the compiler's own prefix. */
function firstLine(message: string): string {
  return message.split('\n')[0]!.replace(/^\[@?vue\/compiler-sfc\]\s*/, '').trim()
}

/** A file line from a line counted inside `block` (1 = the block tag's line). */
function inBlock(block: SFCBlock | null | undefined, line: number | undefined): number | null {
  if (!block || line === undefined) return null
  return block.loc.start.line + line - 1
}

function unsupported(descriptor: SFCDescriptor, file: string): ExtensionProblem[] {
  const found: ExtensionProblem[] = []
  const script = descriptor.scriptSetup ?? descriptor.script
  if (script?.lang && script.lang !== 'ts' && script.lang !== 'js') {
    found.push(problem(file, `<script lang="${script.lang}"> isn't supported; use TypeScript or plain JavaScript`, script.loc.start.line))
  }
  if (descriptor.template?.lang) {
    found.push(problem(file, `<template lang="${descriptor.template.lang}"> isn't supported; use plain HTML`, descriptor.template.loc.start.line))
  }
  if (descriptor.template?.src || script?.src) {
    found.push(problem(file, 'src="..." blocks aren\'t supported; keep the code in the .vue file'))
  }
  for (const style of descriptor.styles) {
    const line = style.loc.start.line
    if (style.lang) found.push(problem(file, `<style lang="${style.lang}"> needs a build step; use plain CSS`, line))
    if (style.module) found.push(problem(file, '<style module> isn\'t supported; use <style scoped>', line))
    if (style.src) found.push(problem(file, '<style src="..."> isn\'t supported; import the .css file instead', line))
  }
  return found
}

export function compileSfc(source: string, file: string, id: string): CompiledSfc {
  const failed = (problems: ExtensionProblem[]): CompiledSfc => ({ code: '', css: '', problems })

  const { descriptor, errors } = parse(source, { filename: file, sourceMap: false })
  if (errors.length) {
    return failed(errors.map(error => {
      const located = error as LocatedError
      return problem(file, firstLine(error.message), located.loc?.start?.line ?? null, located.loc?.start?.column ?? null)
    }))
  }
  const blocked = unsupported(descriptor, file)
  if (blocked.length) return failed(blocked)

  const script = descriptor.scriptSetup ?? descriptor.script
  const isTs = script?.lang === 'ts'
  const scoped = descriptor.styles.some(style => style.scoped)
  const expressionPlugins = isTs ? (['typescript'] as const) : undefined
  const scopeId = `data-v-${id}`

  let code: string
  try {
    let bindings
    if (script) {
      const compiled = compileScript(descriptor, {
        id,
        isProd: true,
        inlineTemplate: true,
        genDefaultAs: COMPONENT,
        templateOptions: { compilerOptions: { expressionPlugins: expressionPlugins ? [...expressionPlugins] : undefined } },
      })
      code = compiled.content
      bindings = compiled.bindings
    } else {
      code = `const ${COMPONENT} = {}`
    }

    // <script setup> inlines its template; anything else compiles it apart.
    if (descriptor.template && !descriptor.scriptSetup) {
      const template = compileTemplate({
        source: descriptor.template.content,
        filename: file,
        id,
        scoped,
        slotted: descriptor.slotted,
        isProd: true,
        compilerOptions: {
          bindingMetadata: bindings,
          expressionPlugins: expressionPlugins ? [...expressionPlugins] : undefined,
        },
      })
      if (template.errors.length) {
        return failed(template.errors.map(error => {
          if (typeof error === 'string') return problem(file, error)
          return problem(
            file,
            firstLine(error.message),
            inBlock(descriptor.template, error.loc?.start.line),
            error.loc?.start.column ?? null,
          )
        }))
      }
      code += `\n${template.code.replace(/\nexport (function|const) render/, '\n$1 render')}`
      code += `\n${COMPONENT}.render = render`
    }
    if (scoped) code += `\n${COMPONENT}.__scopeId = ${JSON.stringify(scopeId)}`
    code += `\n${COMPONENT}.__file = ${JSON.stringify(file)}\nexport default ${COMPONENT}\n`
    if (isTs) code = transform(code, { transforms: ['typescript'], disableESTransforms: true }).code
  } catch (error) {
    const located = error as LocatedError
    const message = firstLine(located.message ?? String(error))
    return failed([problem(file, message, inBlock(script, located.loc?.line), located.loc?.column ?? null)])
  }

  const css: string[] = []
  const styleProblems: ExtensionProblem[] = []
  for (const style of descriptor.styles) {
    const compiled = compileStyle({
      source: style.content,
      filename: file,
      id: scopeId,
      scoped: style.scoped,
      isProd: true,
    })
    for (const error of compiled.errors as LocatedError[]) {
      styleProblems.push(problem(file, error.reason ?? firstLine(error.message ?? 'CSS error'), inBlock(style, error.line), error.column ?? null))
    }
    css.push(compiled.code)
  }
  if (styleProblems.length) return failed(styleProblems)
  return { code, css: css.join('\n'), problems: [] }
}
