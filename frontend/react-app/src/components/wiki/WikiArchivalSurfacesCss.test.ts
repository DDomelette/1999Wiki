// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const selectionCss = readFileSync(new URL('./WikiCharacterSelectionPage.css', import.meta.url), 'utf8')
const readerCss = readFileSync(new URL('./WikiReader.css', import.meta.url), 'utf8')
const indexCss = readFileSync(new URL('./PageIndex.css', import.meta.url), 'utf8')

describe('Wiki archival surface contract', () => {
  it('uses shared soft textured panels for selection index, preview, and summary', () => {
    expect(selectionCss).toMatch(/\.wiki-character-selection__index,\s*\.wiki-character-selection__preview,\s*\.wiki-character-selection__summary\s*\{[^}]*border-radius:\s*16px[^}]*background-image:\s*var\(--archive-texture\)/s)
    expect(selectionCss).toMatch(/@media \(max-width: 720px\)[\s\S]*grid-template-areas:\s*"index" "preview" "summary"/s)
  })

  it('scopes generic dossier surfaces without altering the character detail dossier', () => {
    expect(readerCss).toMatch(/\.wiki-generic-detail\s*\{[^}]*display:\s*grid/s)
    expect(readerCss).toMatch(/\.wiki-generic-detail > \.wiki-content\s*\{[^}]*width:\s*100%/s)
    expect(readerCss).toContain('.wiki-generic-detail > .wiki-dossier-info')
    expect(readerCss).toContain('background-image: var(--archive-texture)')
    expect(readerCss).not.toContain('.wiki-character-detail')
  })

  it('keeps index controls and selected records rounded without hard inset bars', () => {
    expect(indexCss).toMatch(/\.wiki-page-index__search input\s*\{[^}]*border-radius:\s*9px/s)
    expect(indexCss).toMatch(/\.wiki-index-item\s*\{[^}]*border-radius:\s*12px/s)
    expect(indexCss).toMatch(/\.wiki-index-item\[aria-pressed='true'\]\s*\{[^}]*box-shadow:\s*inset 0 0 0 1px/s)
    expect(indexCss).not.toContain('box-shadow: inset 3px 0 0')
  })
})
