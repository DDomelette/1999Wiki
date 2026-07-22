// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const archival = readFileSync(new URL('./archival.css', import.meta.url), 'utf8')
const main = readFileSync(new URL('../main.tsx', import.meta.url), 'utf8')

describe('archival visual primitives', () => {
  it('defines the shared surface, typography, state, and focus primitives', () => {
    for (const selector of [
      '.archive-surface',
      '.archive-kicker',
      '.archive-meta',
      '.archive-error',
      '.archive-empty',
      ':where(a, button, input, [tabindex]):focus-visible',
    ]) {
      expect(archival).toContain(selector)
    }

    expect(archival).toContain('background: var(--archive-panel)')
    expect(archival).toContain('border: 1px solid var(--archive-line)')
    expect(archival).toContain('outline: 2px solid var(--accent-rust)')
  })

  it('does not reintroduce the retired light page fills', () => {
    expect(archival.toLowerCase()).not.toMatch(/#f5ead0|#fff8e8/)
  })

  it('is loaded immediately after the theme tokens', () => {
    expect(main).toMatch(/import '\.\/styles\/themes\.css'\s+import '\.\/styles\/archival\.css'/)
  })
})
