// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const globalCss = readFileSync(new URL('../../styles/global.css', import.meta.url), 'utf8')
const navCss = readFileSync(new URL('../animations/reactbits/CardNav.css', import.meta.url), 'utf8')
const homeCss = readFileSync(new URL('./HomeSection.css', import.meta.url), 'utf8')
const dataCss = readFileSync(new URL('./DataSection.css', import.meta.url), 'utf8')
const chatCss = readFileSync(new URL('./ChatSection.css', import.meta.url), 'utf8')

describe('main page responsive CSS contract', () => {
  it('uses dynamic viewport units and mobile-safe snap behavior', () => {
    expect(globalCss).toContain('--main-nav-mobile-offset: 56px')
    expect(globalCss).toContain('--main-page-bottom-safe: env(safe-area-inset-bottom, 0px)')
    expect(globalCss).toMatch(/\.snap-container\s*\{[^}]*height:\s*100vh[^}]*height:\s*100dvh/s)
    expect(globalCss).toMatch(/\.snap-section\s*\{[^}]*height:\s*100vh[^}]*height:\s*100dvh/s)
    expect(globalCss).toMatch(/@media \(max-width: 720px\)[\s\S]*scroll-snap-type:\s*y proximity/)
  })

  it('compacts only the main Card Nav on phones', () => {
    expect(navCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.card-nav--main \.card-nav__bar/)
    expect(navCss).toMatch(/\.card-nav--main\s*\{[^}]*top:\s*calc\(env\(safe-area-inset-top, 0px\) \+ 6px\)/s)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__bar\s*\{[^}]*min-height:\s*40px/s)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__toggle[\s\S]*width:\s*36px[\s\S]*height:\s*36px/)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__brand\s*\{[^}]*font-size:\s*\.68rem[^}]*white-space:\s*nowrap/s)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__actions\s*\{[^}]*gap:\s*2px/s)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__primary\s*\{[^}]*font-size:\s*\.76rem/s)
    expect(navCss).not.toMatch(/\.card-nav--wiki \.card-nav__bar\s*\{[^}]*min-height:\s*40px/s)
  })

  it('defines phone home sizing and safe scroll cue placement', () => {
    expect(homeCss).toContain('@media (max-width: 720px)')
    expect(homeCss).toMatch(/\.home-section__video\s*\{[^}]*object-fit:\s*cover/s)
    expect(homeCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.home-section__cta\s*\{[^}]*min-height:\s*44px/s)
    expect(homeCss).toContain('env(safe-area-inset-bottom')
  })

  it('switches data panels to the approved transparent poster at 980px', () => {
    expect(dataCss).toContain('@media (max-width: 980px)')
    expect(dataCss).toMatch(/\.category-panel__layout\s*\{[^}]*grid-template-columns:\s*minmax\(320px, \.72fr\) minmax\(560px, 1\.45fr\)/s)
    expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.category-panel__copy\s*\{[^}]*position:\s*absolute[^}]*bottom:/s)
    expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.data-section__nav\s*\{[^}]*overflow-x:\s*auto/s)
    expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.data-section__nav-button\s*\{[^}]*min-height:\s*44px/s)
    expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.category-panel__wiki-link\s*\{[^}]*z-index:\s*4/s)
    const mobileCopy = dataCss.match(/@media \(max-width: 980px\)[\s\S]*?\.category-panel__copy\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(mobileCopy).not.toMatch(/background(?:-color)?:/)
    expect(mobileCopy).toContain('text-shadow:')
  })

  it('keeps the mobile chat toolbar below navigation and the input shrinkable', () => {
    expect(chatCss).toContain('@media (max-width: 720px)')
    expect(chatCss).toMatch(/\.chat-section\s*\{[^}]*background:\s*linear-gradient[^}]*backdrop-filter:\s*blur\(2px\)/s)
    expect(chatCss).toMatch(/\.chat-section__clear\s*\{[^}]*width:\s*36px[^}]*height:\s*36px/s)
    expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.chat-section__toolbar\s*\{[^}]*padding:\s*calc\([^}]*--main-nav-mobile-offset/s)
    expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.chat-section__toolbar select\s*\{[^}]*min-width:\s*0[^}]*width:\s*100%/s)
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
