import { describe, expect, it } from 'vitest'
import { loadRecentWikiPages, rememberWikiPage } from './recentWiki'

function memoryStorage(seed = '') {
  let value = seed
  return { getItem: () => value || null, setItem: (_key: string, next: string) => { value = next } }
}

describe('recent Wiki pages', () => {
  it('deduplicates and bounds recent routes', () => {
    const storage = memoryStorage()
    for (let index = 0; index < 7; index += 1) {
      rememberWikiPage({ pageId: `p:${index}`, pageType: 'story', title: `Page ${index}`, route: `/wiki/story/${index}`, subtitle: '', category: 'story' }, storage)
    }
    rememberWikiPage({ pageId: 'p:4', pageType: 'story', title: 'Page 4 updated', route: '/wiki/story/4', subtitle: '', category: 'story' }, storage)
    const pages = loadRecentWikiPages(storage)
    expect(pages).toHaveLength(5)
    expect(pages[0]).toMatchObject({ pageId: 'p:4', title: 'Page 4 updated' })
    expect(new Set(pages.map((page) => page.pageId)).size).toBe(5)
  })

  it('drops malformed and external routes', () => {
    const storage = memoryStorage(JSON.stringify([{ pageId: 'x', pageType: 'story', title: 'Bad', route: 'https://example.com' }]))
    expect(loadRecentWikiPages(storage)).toEqual([])
  })
})
