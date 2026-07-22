import { describe, expect, it } from 'vitest'
import {
  CRAWLER_CHARACTER_COVER_SRC,
  CRAWLER_PSYCHUBE_COVER_SRC,
  CRAWLER_STORY_COVER_SRC,
} from './crawlerCovers'
import { getCategoryCoverSrc } from './assets'

describe('crawler category cover assets', () => {
  it('uses crawler-proven character standees', () => {
    expect(CRAWLER_CHARACTER_COVER_SRC.length).toBeGreaterThan(0)
    for (const src of CRAWLER_CHARACTER_COVER_SRC) {
      expect(src).toMatch(/^\/images\/characters\/standees\/.+\.(png|jpe?g|webp)$/)
    }
    expect(getCategoryCoverSrc('\u4eba\u7269')).toMatch(
      /^\/images\/characters\/standees\/.+\.(png|jpe?g|webp)$/,
    )
  })

  it('uses crawler-proven psychube covers', () => {
    expect(CRAWLER_PSYCHUBE_COVER_SRC.length).toBeGreaterThan(0)
    for (const src of CRAWLER_PSYCHUBE_COVER_SRC) {
      expect(src).toMatch(/^\/images\/psychube\/.+\.(png|jpe?g|webp)$/)
    }
    expect(getCategoryCoverSrc('\u5fc3\u76f8')).toMatch(
      /^\/images\/psychube\/.+\.(png|jpe?g|webp)$/,
    )
  })

  it('uses crawler-proven story covers', () => {
    expect(CRAWLER_STORY_COVER_SRC.length).toBeGreaterThan(0)
    for (const src of CRAWLER_STORY_COVER_SRC) {
      expect(src).toMatch(/^\/images\/story\/.+\.(png|jpe?g|webp)$/)
    }
    expect(getCategoryCoverSrc('\u5267\u60c5')).toMatch(
      /^\/images\/story\/.+\.(png|jpe?g|webp)$/,
    )
  })

  it('falls back to the crawler-proven global background', () => {
    expect(getCategoryCoverSrc('\u4e16\u754c')).toBe('/images/global-background.png')
  })
})
