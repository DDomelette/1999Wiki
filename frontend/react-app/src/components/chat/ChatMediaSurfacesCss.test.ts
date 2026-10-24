// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const galleryCss = readFileSync(
  new URL('../animations/reactbits/CircularGallery.css', import.meta.url),
  'utf8',
)
const voiceCss = readFileSync(new URL('./VoicePanel.css', import.meta.url), 'utf8')

describe('chat media surface contract', () => {
  it('rounds and softens gallery navigation and full-size controls', () => {
    expect(galleryCss).toMatch(/\.circular-gallery__previous,\s*\.circular-gallery__next\s*\{[^}]*border-radius:\s*14px[^}]*box-shadow:/s)
    expect(galleryCss).toMatch(/\.circular-gallery__open\s*\{[^}]*border-radius:\s*12px[^}]*box-shadow:/s)
  })

  it('gives mobile voice lines a separate language row with overflow for extra variants', () => {
    expect(voiceCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.voice-line\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) auto/s)
    expect(voiceCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.voice-line__languages\s*\{[^}]*grid-column:\s*1 \/ -1[^}]*flex-wrap:\s*nowrap[^}]*width:\s*100%[^}]*overflow-x:\s*auto/s)
    expect(voiceCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.voice-line__language\s*\{[^}]*flex:\s*1 0 auto[^}]*min-width:\s*44px[^}]*white-space:\s*nowrap/s)
    expect(voiceCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.voice-line__play\s*\{[^}]*grid-column:\s*2[^}]*grid-row:\s*1/s)
  })
})
