import { describe, expect, it } from 'vitest'
import { getWikiMotionProfile } from './wikiMotionProfiles'

describe('Wiki motion profiles', () => {
  it('uses distinct type profiles and a stable fallback', () => {
    expect(getWikiMotionProfile('character')).not.toEqual(getWikiMotionProfile('story'))
    expect(getWikiMotionProfile('unknown')).toEqual(getWikiMotionProfile())
  })
})
