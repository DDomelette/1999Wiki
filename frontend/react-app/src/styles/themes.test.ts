// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const themes = readFileSync(new URL('./themes.css', import.meta.url), 'utf8')

describe('theme tokens', () => {
  it.each(['storm-dark', 'manuscript-gold', 'cold-archive'])('defines complete %s semantic tokens', (theme) => {
    const block = themes.split(`[data-theme="${theme}"] {`)[1]?.split('}')[0] ?? ''
    for (const token of ['--bg-base', '--bg-elevated', '--bg-overlay', '--text-primary', '--text-secondary', '--accent-gold', '--accent-rust', '--border-subtle']) expect(block).toContain(token)
  })

  it('does not retain legacy theme selectors', () => {
    expect(themes).not.toMatch(/data-theme="(?:dark-warm|parchment|mystic-purple)"/)
  })

  it('uses the approved Archival Noir seeds and complete semantic roles', () => {
    const dark = themes.split('[data-theme="storm-dark"] {')[1]?.split('}')[0] ?? ''

    for (const seed of ['#1c110b', '#e2610b', '#ed6916', '#f6ded4']) {
      expect(dark).toContain(seed)
    }
    for (const token of [
      '--archive-panel',
      '--archive-line',
      '--link-accent',
      '--status-success',
      '--status-warning',
      '--status-error',
    ]) {
      expect(dark).toContain(token)
    }
  })

  it('uses archival typography roles without viewport-sized type', () => {
    const shared = themes.split('[data-theme] {')[1]?.split('}')[0] ?? ''

    expect(shared).toContain("--font-display: 'Libre Caslon Text'")
    expect(shared).toContain("--font-mono: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace")
    expect(shared).not.toMatch(/(?:vw|cqw)/)
  })
})
