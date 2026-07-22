// @vitest-environment node
import { existsSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const detailCss = readFileSync(new URL('./WikiCharacterDetailPage.css', import.meta.url), 'utf8')
const previewCss = readFileSync(new URL('../wiki-preview/KimiWikiPreview.css', import.meta.url), 'utf8')
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
    expect(detailCss).toMatch(/\.character-portrait-stage--desktop \.character-portrait-stage__wardrobe\s*\{[^}]*bottom:\s*-44px[^}]*left:\s*60%[^}]*width:\s*min\(264px,\s*70%\)/s)
    expect(detailCss).toMatch(/\.character-portrait-stage__deploy\s*\{[^}]*display:\s*none/s)
    expect(detailCss).toContain("[data-profile-key='medium']")
    expect(detailCss).toContain("[data-profile-key='damageType']")
    expect(detailCss).toContain("[data-profile-key='birthday']")
    expect(detailCss).toContain("[data-profile-key='position']")
    expect(detailCss).not.toContain('/images/wiki/natural-paper.png')
    expect(detailCss).toContain('repeating-linear-gradient')
    expect(detailCss).not.toMatch(/transform:\s*scale\(/)
  })

  it('defines the approved mobile document flow without horizontal overflow', () => {
    expect(detailCss).toContain('@media (max-width: 760px)')
    expect(detailCss).toMatch(/\.mobile-character-dossier\s*\{[^}]*overflow-x:\s*clip/s)
    expect(detailCss).toMatch(/\.mobile-dossier-tabs\s*\{[^}]*position:\s*fixed/s)
    expect(detailCss).toMatch(/\.mobile-character-dossier__hero\s*\{[^}]*min-height:\s*658px[^}]*padding:\s*28px\s+16px\s+53px\s*!important/s)
    expect(detailCss).toMatch(/\.character-portrait-stage--mobile\s*\{[^}]*height:\s*577px/s)
    expect(detailCss).toMatch(/\.character-portrait-stage--mobile \.character-portrait-stage__images img\s*\{[^}]*scale:\s*1\.0[0-5]/s)
    expect(detailCss).toMatch(/\.character-portrait-stage__identity\s*\{[^}]*width:\s*min\(70%,\s*240px\)/s)
    expect(detailCss).toMatch(/\.character-portrait-stage--mobile \.character-portrait-stage__wardrobe\s*\{[^}]*right:\s*36px/s)
    expect(detailCss).toMatch(/@media \(max-width: 760px\)[\s\S]*\.character-voice-records__scroll\s*\{[^}]*max-height:/s)
    expect(detailCss).toMatch(/\.character-summary__udimo\s*\{[^}]*background:/s)
    expect(detailCss).toMatch(/\.character-summary__udimo img\s*\{[^}]*object-fit:\s*contain/s)
    expect(detailCss).toMatch(/\.mobile-character-dossier \.character-summary__copy > p:last-of-type\s*\{[^}]*display:\s*none/s)
    expect(detailCss).toMatch(/\.mobile-character-dossier__voices \.character-voice-records\s*\{[^}]*height:\s*(?:2[8-9][0-9]|3[0-2][0-9])px/s)
  })

  it('self-hosts the approved fonts and uses code-native paper texture', () => {
    expect(indexHtml).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net/)
    expect(main).toMatch(/import '\.\/styles\/fonts\.css'[\s\S]*import '\.\/styles\/themes\.css'/)
    expect(fontsCss.match(/@font-face/g)).toHaveLength(5)
    expect(fontsCss.match(/font-display:\s*swap/g)).toHaveLength(5)
    expect(fontsCss).toContain("font-family: 'Libre Caslon Text'")
    expect(fontsCss).toContain("font-family: 'JetBrains Mono'")
    expect(fontsCss).toContain("font-family: 'Noto Serif SC'")

    for (const path of [
      'fonts/libre-caslon-text-variable.ttf',
      'fonts/libre-caslon-text-italic-variable.ttf',
      'fonts/jetbrains-mono-variable.ttf',
      'fonts/noto-serif-sc-regular.otf',
      'fonts/noto-serif-sc-bold.otf',
    ]) {
      expect(existsSync(new URL(path, publicUrl)), `missing public/${path}`).toBe(true)
    }
    expect(previewCss).not.toContain('/images/wiki/natural-paper.png')
  })
})
