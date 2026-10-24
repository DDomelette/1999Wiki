// @vitest-environment node
import { existsSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const detailCss = readFileSync(new URL('./WikiCharacterDetailPage.css', import.meta.url), 'utf8')
const indexHtml = readFileSync(new URL('../../../index.html', import.meta.url), 'utf8')
const main = readFileSync(new URL('../../main.tsx', import.meta.url), 'utf8')
const fontsUrl = new URL('../../styles/fonts.css', import.meta.url)
const fontsCss = existsSync(fontsUrl) ? readFileSync(fontsUrl, 'utf8') : ''
const publicUrl = new URL('../../../public/', import.meta.url)

describe('Stitch character dossier visual contract', () => {
  it('defines the desktop single-viewport workbench and explicit rail scroll owners', () => {
    expect(detailCss).toMatch(/\.desktop-character-dossier\s*\{[^}]*grid-template-columns:[^;}]*;/s)
    expect(detailCss).toMatch(/\.desktop-character-dossier\s*\{[^}]*height:\s*calc\(100dvh\s*-\s*64px\)/s)
    expect(detailCss).toMatch(/\.profile-skill-rail\s*\{[^}]*overflow-y:\s*auto/s)
    expect(detailCss).toMatch(/\.inheritance-voice-rail\s*\{[^}]*overflow:\s*hidden/s)
    expect(detailCss).toMatch(/\.character-voice-records__scroll\s*\{[^}]*overflow-y:\s*auto/s)
    expect(detailCss).toMatch(/\.desktop-character-dossier\s*\{[^}]*grid-template-columns:[^;}]*31\.25vw[^;}]*400px/s)
    expect(detailCss).toMatch(/\.character-portrait-stage--desktop \.character-portrait-stage__images img\s*\{[^}]*scale:\s*1\.085[^}]*translate:\s*55px\s+44px/s)
    expect(detailCss).toMatch(/\.character-identity-card\s*\{[^}]*grid-template-columns:\s*58px\s+minmax\(0,\s*1fr\)/s)
    expect(detailCss).toMatch(/\.character-profile-data\s*\{[^}]*min-height:\s*258px/s)
    expect(detailCss).toMatch(/\.character-profile-data\s*\+\s*\.profile-skill-rail__skills\s*\{[^}]*margin-top:\s*53px/s)
    expect(detailCss).toMatch(/\.inheritance-voice-rail\s*\{[^}]*grid-template-rows:\s*220px\s+190px\s+minmax\(0,\s*1fr\)/s)
    expect(detailCss).toMatch(/\.character-portrait-stage--desktop \.character-portrait-stage__wardrobe\s*\{[^}]*bottom:\s*-28px[^}]*left:\s*60%[^}]*width:\s*min\(264px,\s*70%\)/s)
    expect(detailCss).toMatch(/\.character-portrait-stage__wardrobe-group\s*\{[^}]*display:\s*grid[^}]*gap:\s*8px/s)
    expect(detailCss).toMatch(/\.profile-skill-rail\s*\{[^}]*mask-image:\s*linear-gradient\(to bottom/s)
    expect(detailCss).toMatch(/\.character-portrait-stage__deploy\s*\{[^}]*display:\s*none/s)
    expect(detailCss).toContain("[data-profile-key='medium']")
    expect(detailCss).toContain("[data-profile-key='damageType']")
    expect(detailCss).toContain("[data-profile-key='birthday']")
    expect(detailCss).toContain("[data-profile-key='position']")
    expect(detailCss).not.toContain('/images/wiki/natural-paper.png')
    expect(detailCss).toContain('repeating-linear-gradient')
    expect(detailCss).not.toMatch(/transform:\s*scale\(/)
  })

  it('defines responsive dossier flow without nested mobile voice scrolling', () => {
    expect(detailCss).toContain('@media (max-width: 760px)')
    expect(detailCss).toMatch(/\.mobile-character-dossier\s*\{[^}]*overflow-x:\s*clip/s)
    expect(detailCss).toMatch(/\.mobile-dossier-tabs\s*\{[^}]*position:\s*fixed/s)
    expect(detailCss).toMatch(/\.mobile-character-dossier__hero\s*\{[^}]*min-height:\s*0[^}]*padding:\s*24px\s+16px\s+36px\s*!important/s)
    expect(detailCss).toMatch(/\.character-portrait-stage--mobile\s*\{[^}]*height:\s*auto/s)
    expect(detailCss).toMatch(/\.character-portrait-stage--mobile \.character-portrait-stage__visual\s*\{[^}]*position:\s*relative[^}]*height:\s*clamp\(360px,\s*50dvh,\s*480px\)/s)
    expect(detailCss).toMatch(/\.character-portrait-stage--mobile \.character-portrait-stage__images img\s*\{[^}]*scale:\s*1\.0[0-5]/s)
    expect(detailCss).toMatch(/\.character-portrait-stage__identity\s*\{[^}]*width:\s*min\(62%,\s*210px\)[^}]*padding:\s*12px/s)
    expect(detailCss).toMatch(/\.character-portrait-stage--mobile \.character-portrait-stage__wardrobe\s*\{[^}]*position:\s*relative[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s)
    expect(detailCss).toMatch(/@media \(max-width: 760px\)[\s\S]*\.character-voice-records__scroll\s*\{[^}]*max-height:\s*none[^}]*overflow:\s*visible/s)
    expect(detailCss).toMatch(/\.character-summary__udimo\s*\{[^}]*background:/s)
    expect(detailCss).toMatch(/\.character-summary__udimo img\s*\{[^}]*object-fit:\s*contain/s)
    expect(detailCss).toMatch(/\.mobile-character-dossier \.character-summary__copy > p:last-of-type\s*\{[^}]*display:\s*none/s)
    expect(detailCss).toMatch(/\.mobile-character-dossier__voices \.character-voice-records\s*\{[^}]*height:\s*auto/s)
  })

  it('lets the whole desktop rail scroll on short screens instead of collapsing voice records', () => {
    expect(detailCss).toMatch(/@media \(min-width: 761px\) and \(max-height: 760px\)[\s\S]*\.inheritance-voice-rail\s*\{[^}]*display:\s*flex[^}]*overflow-y:\s*auto/s)
    expect(detailCss).toMatch(/@media \(min-width: 761px\) and \(max-height: 760px\)[\s\S]*\.inheritance-voice-rail \.character-voice-records\s*\{[^}]*min-height:\s*320px/s)
  })

  it('uses one soft card shadow while preserving the dossier inset texture', () => {
    expect(detailCss).toContain('--dossier-card-shadow: 7px 9px 16px rgb(0 0 0 / 42%)')
    expect(detailCss).toMatch(/\.wiki-character-detail :is\([\s\S]*?\.character-skill-card,[\s\S]*?\.character-collection-item[\s\S]*?\)\s*,?\s*\.wiki-character-detail \.mobile-character-dossier \.character-progression li\s*\{[^}]*box-shadow:\s*var\(--dossier-card-shadow\)/s)
    expect(detailCss).toMatch(/\.wiki-character-detail :is\(\.character-identity-card, \.character-portrait-stage__wardrobe\)\s*\{[^}]*box-shadow:\s*var\(--dossier-card-shadow\), inset/s)
  })

  it('self-hosts the approved fonts and uses code-native paper texture', () => {
    expect(indexHtml).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net/)
    expect(main).toMatch(/import '\.\/styles\/fonts\.css'[\s\S]*import '\.\/styles\/themes\.css'/)
    expect(fontsCss.match(/@font-face/g)).toHaveLength(5)
    expect(fontsCss.match(/font-display:\s*swap/g)).toHaveLength(3)
    expect(fontsCss.match(/font-display:\s*optional/g)).toHaveLength(2)
    expect(fontsCss).toContain("font-family: 'Libre Caslon Text'")
    expect(fontsCss).toContain("font-family: 'JetBrains Mono'")
    expect(fontsCss).toContain("font-family: 'Noto Serif SC'")

    for (const path of [
      'fonts/libre-caslon-text-variable.ttf',
      'fonts/libre-caslon-text-italic-variable.ttf',
      'fonts/jetbrains-mono-variable.ttf',
      'fonts/noto-serif-sc-regular.woff2',
      'fonts/noto-serif-sc-bold.woff2',
    ]) {
      expect(existsSync(new URL(path, publicUrl)), `missing public/${path}`).toBe(true)
    }
  })
})
