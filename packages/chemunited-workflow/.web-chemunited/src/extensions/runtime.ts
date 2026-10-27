import * as Vue from 'vue'
import * as VueRouter from 'vue-router'
import * as Pinia from 'pinia'
import * as chemunited from './publicApi'

/**
 * The modules a customization file may import by name. Compiled files import
 * them through small shim modules that read this registry, so they share the
 * dashboard's own Vue, router, store and API rather than loading copies.
 */
export const RUNTIME_GLOBAL = '__CHEMUNITED_RUNTIME__'

export function installRuntime(): void {
  const modules: Record<string, object> = {
    vue: Vue,
    'vue-router': VueRouter,
    pinia: Pinia,
    chemunited,
  }
  ;(globalThis as Record<string, unknown>)[RUNTIME_GLOBAL] = modules
}
