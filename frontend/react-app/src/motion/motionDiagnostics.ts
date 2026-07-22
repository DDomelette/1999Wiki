export interface MotionDiagnostic {
  component: string
  event: 'initialized' | 'fallback' | 'image-failure'
  durationMs?: number
  reason?: string
  recordedAt: number
}

const MAX_ENTRIES = 100
const diagnostics: MotionDiagnostic[] = []

export function recordMotionDiagnostic(entry: Omit<MotionDiagnostic, 'recordedAt'>) {
  diagnostics.push({ ...entry, recordedAt: Date.now() })
  if (diagnostics.length > MAX_ENTRIES) diagnostics.splice(0, diagnostics.length - MAX_ENTRIES)
}

export function readMotionDiagnostics(): readonly MotionDiagnostic[] {
  return diagnostics.slice()
}

export function clearMotionDiagnostics() {
  diagnostics.length = 0
}
