import { afterEach, describe, expect, it } from 'vitest'
import {
  parseWikiLocation,
  pushWikiDetail,
  readWikiSelectionState,
  replaceWikiLocation,
  toCanonicalWikiRoute,
  toVisibleWikiRoute,
  type WikiSelectionHistoryState,
} from './wikiRoutes'

const selection: WikiSelectionHistoryState = {
  category: 'character',
  query: '槲寄生',
  selectedPageId: 'char:3003',
  listScrollTop: 240,
}

describe('wiki routes', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/')
  })

  it('classifies selection aliases and detail routes without rewriting backend routes', () => {
    expect(parseWikiLocation('/wiki')).toEqual({ kind: 'character-selection' })
    expect(parseWikiLocation('/wiki/character')).toEqual({ kind: 'character-selection' })
    expect(parseWikiLocation('/wiki/character/3003')).toEqual({
      kind: 'detail',
      route: '/wiki/character/3003',
      resolverHint: '3003',
    })
    expect(parseWikiLocation('/wiki/char/3003')).toEqual({ kind: 'detail', route: '/wiki/char/3003' })
    expect(parseWikiLocation('/wiki/story/42')).toEqual({ kind: 'detail', route: '/wiki/story/42' })
  })

  it('maps preview routes to API-owned canonical routes without changing the suffix', () => {
    expect(parseWikiLocation('/wiki-preview/character', '/wiki-preview')).toEqual({ kind: 'character-selection' })
    expect(parseWikiLocation('/wiki-preview/char/3003', '/wiki-preview')).toEqual({
      kind: 'detail',
      route: '/wiki-preview/char/3003',
    })
    expect(toCanonicalWikiRoute('/wiki-preview/char/3003', '/wiki-preview')).toBe('/wiki/char/3003')
    expect(toVisibleWikiRoute('/wiki/character/3003', '/wiki-preview')).toBe('/wiki-preview/character/3003')
  })

  it('stores selection state while preserving the API-owned detail route', () => {
    pushWikiDetail('/wiki/char/3003', selection)

    expect(window.location.pathname).toBe('/wiki/char/3003')
    expect(readWikiSelectionState(window.history.state)).toEqual(selection)

    replaceWikiLocation('/wiki/character', { wikiSelection: selection })
    expect(window.location.pathname).toBe('/wiki/character')
    expect(readWikiSelectionState(window.history.state)).toEqual(selection)
  })

  it('rejects malformed history state instead of contaminating filters', () => {
    expect(readWikiSelectionState(null)).toBeNull()
    expect(readWikiSelectionState({ wikiSelection: { ...selection, listScrollTop: -1 } })).toBeNull()
    expect(readWikiSelectionState({ wikiSelection: { ...selection, query: 42 } })).toBeNull()
  })
})
