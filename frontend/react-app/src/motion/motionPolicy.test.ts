import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearMotionDiagnostics, readMotionDiagnostics, recordMotionDiagnostic } from './motionDiagnostics'
import { getMotionPolicy } from './motionPolicy'

describe('motion policy and local diagnostics', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    clearMotionDiagnostics()
  })

  it('disables animation for reduced motion', () => {
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: vi.fn().mockReturnValue({ matches: true }) })
    expect(getMotionPolicy()).toMatchObject({ enabled: false, blur: false, reason: 'reduced-motion' })
  })

  it('removes blur and caps resources for save-data', () => {
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: vi.fn().mockReturnValue({ matches: false }) })
    Object.defineProperty(navigator, 'connection', { configurable: true, value: { saveData: true } })
    expect(getMotionPolicy()).toMatchObject({ enabled: true, blur: false, dpr: 1, textureBudget: 3, reason: 'save-data' })
  })

  it('keeps only bounded in-memory diagnostics', () => {
    for (let index = 0; index < 105; index += 1) recordMotionDiagnostic({ component: 'test', event: 'initialized', durationMs: index })
    const entries = readMotionDiagnostics()
    expect(entries).toHaveLength(100)
    expect(entries[0].durationMs).toBe(5)
  })
})
