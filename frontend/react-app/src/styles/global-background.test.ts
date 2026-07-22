import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

declare const __dirname: string

describe('global project background', () => {
  it('uses the official home background as the body-level base layer', () => {
    const cssText = readFileSync(resolve(__dirname, 'global.css'), 'utf-8')

    expect(cssText).toContain('--global-background-image: url("/images/global-background.png")')
    expect(cssText).toContain('background-image:')
    expect(cssText).toContain('var(--global-background-image)')
    expect(cssText).toContain('background-attachment: fixed')
  })
})
