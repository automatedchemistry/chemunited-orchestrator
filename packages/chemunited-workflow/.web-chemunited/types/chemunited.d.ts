/**
 * Types for the `chemunited` module that a project's custom pages and widgets
 * (customizations/ui/) import. Shipped with chemunited-workflow for editors;
 * `chemunited-workflow ui init` copies it into a project. UI API version 1.
 *
 * Checked against src/extensions/publicApi.ts on every dashboard build.
 */
import type { Component, ComputedRef, Ref, ShallowRef } from 'vue'

/** The dashboard's UI API version. */
export declare const version: number

export type NotificationType = 'success' | 'error' | 'info' | 'warning'

/** A request the server answered with an error status, or a custom route that failed. */
export declare class ApiError extends Error {
  readonly status: number
  readonly detail: unknown
  constructor(message: string, status: number, detail?: unknown)
}

/** JSON requests to the dashboard's REST API; failures throw an ApiError. */
export declare const api: {
  get: <T = unknown>(url: string) => Promise<T>
  post: <T = unknown>(url: string, body?: unknown) => Promise<T>
  put: <T = unknown>(url: string, body?: unknown) => Promise<T>
  delete: <T = unknown>(url: string) => Promise<T>
}

/**
 * Call a function from customizations/routers/router_hook.py and return its
 * result. Throws an ApiError when the call fails or the function raises.
 */
export declare function callCustomRoute<T = unknown>(
  name: string,
  kwargs?: Record<string, unknown>,
): Promise<T>

export declare function errorMessage(error: unknown): string

/** Show a message in the dashboard's notification bar. */
export declare function notify(message: string, type?: NotificationType): void

/**
 * Run `work`, notify on success (if `success` is given) and on failure, and
 * never throw: resolves to the result, or undefined when `work` failed.
 */
export declare function attempt<T>(
  work: () => Promise<T>,
  messages?: { success?: string, error?: string },
): Promise<T | undefined>

export type RunState = 'idle' | 'running' | 'paused' | 'finished' | 'failed' | 'cancelled'

/** The active run, as the dashboard tracks it. */
export declare function useRunStatus(): {
  runId: ComputedRef<string | null>
  runState: ComputedRef<RunState>
  stopReason: ComputedRef<string>
  refresh: () => Promise<void>
}

/** URL of a file under customizations/ui/. */
export declare function extUrl(path: string): string

export type DeviceStatus = 'unknown' | 'running' | 'done' | 'failed'

export interface LiveCommand {
  name: string
  params: Record<string, unknown> | null
  at: string
  run: string | null
  node: string | null
}

export interface LiveDevice {
  kind: string | null
  status: DeviceStatus
  command: LiveCommand | null
  picture: Record<string, unknown> | null
  error: string | null
}

export interface LiveDisplay {
  value: string | null
  at: string | null
  error: string | null
  monitored: boolean
}

export type LiveConnection = 'connecting' | 'open' | 'reconnecting' | 'disconnected'

/**
 * Live device and LCD state from GET /platform/stream. Call start() to listen;
 * it stops when the component unmounts. Live only while monitoring is on.
 */
export declare function usePlatformLive(): {
  live: Ref<boolean>
  pictures: Ref<boolean>
  devices: ShallowRef<Record<string, LiveDevice>>
  displays: ShallowRef<Record<string, LiveDisplay>>
  connection: Ref<LiveConnection>
  flashing: ShallowRef<ReadonlySet<string>>
  start: () => void
  stop: () => void
}

/**
 * The dashboard's form for a map of JSON-schema-like `properties`.
 * Props: properties, values, readonly. Emits update:values.
 */
export declare const SchemaForm: Component
