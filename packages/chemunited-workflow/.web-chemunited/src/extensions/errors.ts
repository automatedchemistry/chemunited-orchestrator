import { reactive } from 'vue'

/** One thing wrong with a customization file, located as precisely as known. */
export interface ExtensionProblem {
  /** Path under customizations/ui/, e.g. "pages/Sensors.vue". */
  file: string
  line: number | null
  column: number | null
  message: string
}

/** Thrown when a customization file can't be compiled or loaded. */
export class ExtensionError extends Error {
  readonly problems: ExtensionProblem[]

  constructor(problems: ExtensionProblem[]) {
    super(problems.map(formatProblem).join('\n'))
    this.name = 'ExtensionError'
    this.problems = problems
  }
}

export function problem(
  file: string,
  message: string,
  line: number | null = null,
  column: number | null = null,
): ExtensionProblem {
  return { file, line, column, message }
}

export function formatProblem(p: ExtensionProblem): string {
  if (p.line === null) return `${p.file}: ${p.message}`
  const column = p.column === null ? '' : `:${p.column}`
  return `${p.file}:${p.line}${column}: ${p.message}`
}

export function toProblems(error: unknown, file: string): ExtensionProblem[] {
  if (error instanceof ExtensionError) return error.problems
  const message = error instanceof Error ? `${error.name}: ${error.message}` : String(error)
  return [problem(file, message)]
}

/** Problems hit while running customizations in this browser session, by file. */
export const sessionProblems = reactive(new Map<string, ExtensionProblem[]>())

export function reportProblems(file: string, problems: ExtensionProblem[]) {
  sessionProblems.set(file, problems)
  for (const p of problems) console.error(`[customization] ${formatProblem(p)}`)
}

export function clearProblems(file: string) {
  sessionProblems.delete(file)
}
