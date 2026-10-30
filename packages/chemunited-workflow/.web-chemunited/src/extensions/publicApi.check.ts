/**
 * Type-only check, never bundled: `vue-tsc` fails if types/chemunited.d.ts
 * (what customizers' editors see) drifts from publicApi.ts (what their pages
 * actually import as `chemunited`).
 */
import * as actual from './publicApi'
import type * as Declared from '../../types/chemunited'

// Every export has the declared type...
export const publicApiMatchesDeclaration: typeof Declared = actual

// ...and every export is declared (an undeclared one shows up by name here).
type Undeclared = Exclude<keyof typeof actual, keyof typeof Declared>
export const everyExportIsDeclared: [Undeclared] extends [never] ? true : Undeclared = true
