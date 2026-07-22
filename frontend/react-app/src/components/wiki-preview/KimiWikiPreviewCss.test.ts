import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('KimiWikiPreview.css', () => {
  it('keeps the approved desktop geometry, mobile breakpoint and local-only acrylic surface', () => {
    const css = readFileSync(join(process.cwd(), 'src/components/wiki-preview/KimiWikiPreview.css'), 'utf8')

    expect(css).toContain('.wiki-shell--kimi-preview')
    expect(css).toContain('grid-template-columns: 256px 128px minmax(0, 1fr) 400px')
    expect(css).toContain('@media (max-width: 760px)')
    expect(css).toContain('backdrop-filter')
    expect(css).not.toMatch(/https?:\/\//)
  })

  it('keeps the preview navigation full-width and bounds sticky detail media', () => {
    const css = readFileSync(join(process.cwd(), 'src/components/wiki-preview/KimiWikiPreview.css'), 'utf8')

    expect(css).toMatch(/\.wiki-shell--kimi-preview \.card-nav\s*\{[^}]*top:\s*0[^}]*left:\s*0[^}]*width:\s*100%[^}]*transform:\s*none/s)
    expect(css).toMatch(/\.wiki-shell--kimi-preview \.card-nav__bar\s*\{[^}]*box-shadow:/s)
    expect(css).toMatch(/\.kimi-desktop-character-dossier\s*\{[^}]*font-size:\s*1\.08rem/s)
    expect(css).toMatch(/\.kimi-desktop-character-dossier__utility\s*\{[^}]*position:\s*sticky[^}]*bottom:\s*0/s)
    expect(css).toMatch(/\.kimi-desktop-character-dossier__right \.character-summary__udimo\s*\{[^}]*max-width:\s*100%/s)
    expect(css).toMatch(/\.kimi-desktop-character-dossier__right \.character-summary__udimo img\s*\{[^}]*max-width:\s*100%[^}]*object-fit:\s*contain/s)
  })
})
