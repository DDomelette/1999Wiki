// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('./SuggestedQuestions.css', import.meta.url), 'utf8')
const component = readFileSync(new URL('./SuggestedQuestions.tsx', import.meta.url), 'utf8')

describe('SuggestedQuestions.css', () => {
  it('keeps recommendation pills on a horizontally scrollable row', () => {
    expect(component).toContain("import './SuggestedQuestions.css'")
    expect(css).toMatch(/\.suggested-questions\s*\{[^}]*display:\s*flex/s)
    expect(css).toMatch(/\.suggested-questions__list\s*\{[^}]*overflow-x:\s*auto/s)
    expect(css).toMatch(/\.suggested-questions__item\s*\{[^}]*white-space:\s*nowrap/s)
    expect(css).toContain('@media (max-width: 640px)')
  })

  it('defines accessible interaction states with theme-derived colors', () => {
    expect(css).toContain('.suggested-questions__item:focus-visible')
    expect(css).toContain('.suggested-questions__item:disabled')
    expect(css).toContain('.suggested-questions__item:hover:not(:disabled)')
    expect(css).toMatch(/var\(--(?:bg|text|accent|border)-/)
    expect(css).toContain('color-mix(')
    expect(css).not.toMatch(/#[0-9a-f]{3,8}\b|rgba?\(/i)
  })
})
