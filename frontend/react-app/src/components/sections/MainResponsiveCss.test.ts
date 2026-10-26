// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const globalCss = readFileSync(new URL('../../styles/global.css', import.meta.url), 'utf8')
const navCss = readFileSync(new URL('../animations/reactbits/CardNav.css', import.meta.url), 'utf8')
const homeCss = readFileSync(new URL('./HomeSection.css', import.meta.url), 'utf8')
const dataCss = readFileSync(new URL('./DataSection.css', import.meta.url), 'utf8')
const chatCss = readFileSync(new URL('./ChatSection.css', import.meta.url), 'utf8')
const indexHtml = readFileSync(new URL('../../../index.html', import.meta.url), 'utf8')

describe('main page responsive CSS contract', () => {
  it('uses dynamic viewport units and mobile-safe snap behavior', () => {
    expect(indexHtml).toMatch(/name="viewport"[^>]*content="[^"]*viewport-fit=cover[^"]*"/)
    expect(globalCss).toContain('--main-nav-mobile-offset: 64px')
    expect(globalCss).toContain('--main-page-bottom-safe: env(safe-area-inset-bottom, 0px)')
    expect(globalCss).toMatch(/\.snap-container\s*\{[^}]*height:\s*100vh[^}]*height:\s*100dvh/s)
    expect(globalCss).toMatch(/\.snap-section\s*\{[^}]*height:\s*100vh[^}]*height:\s*100dvh/s)
    expect(globalCss).toMatch(/\.snap-container\s*\{[^}]*scroll-snap-type:\s*y mandatory/s)
    expect(globalCss).toMatch(/\.snap-section\s*\{[^}]*scroll-snap-stop:\s*always/s)
    expect(globalCss).not.toMatch(/@media \(max-width: 720px\)[\s\S]*scroll-snap-type:\s*y proximity/)
    expect(globalCss).not.toContain('scroll-behavior: smooth')
    expect(dataCss).not.toMatch(/\.data-section__scroll\s*\{[^}]*overflow-y:\s*(?:scroll|auto)/s)
    expect(dataCss).not.toMatch(/\.data-section__scroll\s*\{[^}]*scroll-snap-type:/s)
  })

  it('compacts only the main Card Nav on phones', () => {
    expect(navCss).toMatch(/\.card-nav__bar\s*\{[^}]*border-radius:\s*14px/s)
    expect(navCss).toMatch(/\.card-nav__toggle, \.theme-toggle\s*\{[^}]*border-radius:\s*9px/s)
    expect(navCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.card-nav--main \.card-nav__bar/)
    expect(navCss).toMatch(/\.card-nav--main\s*\{[^}]*top:\s*calc\(env\(safe-area-inset-top, 0px\) \+ 6px\)/s)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__bar\s*\{[^}]*min-height:\s*52px/s)
    expect(navCss).toMatch(/\.card-nav__toggle, \.theme-toggle\s*\{[^}]*width:\s*44px[^}]*height:\s*44px[^}]*flex:\s*none/s)
    expect(navCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.card-nav__brand\s*\{[^}]*min-width:\s*0/s)
    expect(navCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.card-nav__actions\s*\{[^}]*flex:\s*none[^}]*gap:\s*2px/s)
    expect(navCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.card-nav__primary\s*\{[^}]*min-width:\s*58px/s)
    expect(navCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.card-nav__back\s*\{[^}]*min-width:\s*52px/s)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__brand\s*\{[^}]*font-size:\s*\.68rem[^}]*white-space:\s*nowrap/s)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__actions\s*\{[^}]*gap:\s*2px/s)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__primary\s*\{[^}]*font-size:\s*\.76rem/s)
    expect(navCss).not.toMatch(/\.card-nav--wiki \.card-nav__bar\s*\{[^}]*min-height:\s*40px/s)
  })

  it('defines phone home sizing, media contrast, and safe scroll cue placement', () => {
    expect(homeCss).toContain('@media (max-width: 720px)')
    expect(homeCss).toMatch(/\.home-section__video\s*\{[^}]*object-fit:\s*cover/s)
    expect(homeCss).toMatch(/\.home-section__title\s*\{[^}]*color:\s*var\(--on-media-primary\)/s)
    expect(homeCss).toMatch(/\.home-section__cta\s*\{[^}]*border:[^}]*var\(--on-media-accent\)/s)
    expect(homeCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.home-section__cta\s*\{[^}]*min-height:\s*44px/s)
    expect(homeCss).toContain('env(safe-area-inset-bottom')
  })

  it('switches data panels to the approved transparent poster at 980px', () => {
    expect(dataCss).toContain('@media (max-width: 980px)')
    expect(dataCss).toMatch(/\.category-panel__meta\s*\{[^}]*color:\s*var\(--on-media-secondary\)/s)
    expect(dataCss).toMatch(/\.category-panel__layout\s*\{[^}]*grid-template-columns:\s*minmax\(320px, \.72fr\) minmax\(560px, 1\.45fr\)/s)
    expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.category-panel__copy\s*\{[^}]*position:\s*absolute[^}]*bottom:/s)
    expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.data-section__nav\s*\{[^}]*overflow-x:\s*auto/s)
    expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.data-section__nav\s*\{[^}]*scrollbar-width:\s*none/s)
    expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.data-section__nav-button\s*\{[^}]*min-height:\s*44px/s)
    expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.category-panel__wiki-link\s*\{[^}]*z-index:\s*4/s)
    const mobileCopy = dataCss.match(/@media \(max-width: 980px\)[\s\S]*?\.category-panel__copy\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(mobileCopy).not.toMatch(/background(?:-color)?:/)
    expect(mobileCopy).toContain('text-shadow:')
  })

  it('constrains the sticky data navigation to the data sequence', () => {
    expect(dataCss).toMatch(
      /\.data-section__nav-shell\s*\{[^}]*height:\s*100vh[^}]*height:\s*100dvh/s,
    )
    expect(dataCss).toMatch(
      /\.data-section__panels\s*\{[^}]*margin-top:\s*-100vh[^}]*margin-top:\s*-100dvh/s,
    )
    expect(dataCss).not.toMatch(/\.data-section__nav-shell\s*\{[^}]*margin-bottom:\s*-100/s)
  })

  it('keeps the chat toolbar below navigation and the mobile input shrinkable', () => {
    expect(chatCss).toContain('@media (max-width: 720px)')
    expect(chatCss).toMatch(/\.chat-section\s*\{[^}]*background:\s*linear-gradient[^}]*backdrop-filter:\s*blur\(2px\)/s)
    expect(chatCss).toMatch(/\.chat-section__empty\s*\{[^}]*flex:\s*0 0 auto/s)
    expect(chatCss).toMatch(/\.chat-section__empty\s*\{[^}]*border-radius:\s*16px/s)
    expect(chatCss).toMatch(/\.chat-section__empty-register\s*\{[^}]*color:\s*var\(--text-muted\)[^}]*opacity:\s*0\.72/s)
    expect(chatCss).toMatch(/\.chat-section__empty-register span\s*\{[^}]*padding:\s*0/s)
    expect(chatCss).toContain('background-image: var(--archive-texture)')
    expect(chatCss).toMatch(/\.chat-section__clear\s*\{[^}]*width:\s*36px[^}]*height:\s*36px/s)
    const baseToolbar = chatCss.match(/\.chat-section__toolbar\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(baseToolbar).toContain('padding-top: 88px')
    expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.chat-section__toolbar\s*\{[^}]*padding:\s*calc\([^}]*--main-nav-mobile-offset/s)
    expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.category-select\s*\{[^}]*width:\s*100%[^}]*min-width:\s*0/s)
    expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.chat-input__form\s*\{[^}]*padding-right:\s*calc\(18px \+ env\(safe-area-inset-right, 0px\)\)/s)
    expect(chatCss).toMatch(/\.chat-input__row\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) auto/s)
    expect(chatCss).toMatch(/\.chat-input__field\s*\{[^}]*min-width:\s*0/s)
    expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.message-bubble\s*\{[^}]*max-width:\s*88%/s)
    const baseBubble = chatCss.match(/\.message-bubble\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(baseBubble).not.toContain('overflow-wrap:')
    expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.message-bubble\s*\{[^}]*overflow-wrap:\s*anywhere/s)
    expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.markdown-message pre\s*\{[^}]*overflow-x:\s*auto/s)
    expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.markdown-message table\s*\{[^}]*display:\s*block[^}]*overflow-x:\s*auto/s)
  })
})
