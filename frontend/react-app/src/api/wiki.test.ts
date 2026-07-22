import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchWikiCategories,
  fetchWikiPage,
  fetchWikiPageByRoute,
  fetchWikiPages,
  resolveWikiRoute,
} from './wiki'

describe('wiki API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches categories and page lists from /api/wiki', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ categories: [{ key: 'character', label: '角色', count: 1 }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [], nextCursor: null }) })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchWikiCategories()).resolves.toEqual([{ key: 'character', label: '角色', count: 1 }])
    await expect(fetchWikiPages({ category: '角色', q: '爱兹拉', type: 'character', limit: 20 })).resolves.toEqual({
      items: [],
      nextCursor: null,
    })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/wiki/categories')
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/wiki/pages?category=%E8%A7%92%E8%89%B2&q=%E7%88%B1%E5%85%B9%E6%8B%89&type=character&limit=20',
    )
  })

  it('fetches detail and resolves routes with backend field names', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ pageId: 'char:3074', title: '爱兹拉' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ route: '/wiki/char/3074', query: '3074' }) })
    vi.stubGlobal('fetch', fetchMock)

    await fetchWikiPage('char:3074')
    await resolveWikiRoute({ entityId: '3074', sourceId: 'Data:Char/3074.json', title: '爱兹拉' })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/wiki/pages/char%3A3074')
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/wiki/routes/resolve?source_id=Data%3AChar%2F3074.json&entity_id=3074&title=%E7%88%B1%E5%85%B9%E6%8B%89',
    )
  })

  it('fetches page detail by stable wiki route', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ pageId: 'char:3074', route: '/wiki/char/3074' }) })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchWikiPageByRoute('/wiki/char/3074')).resolves.toEqual({
      pageId: 'char:3074',
      route: '/wiki/char/3074',
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/wiki/pages/by-route?route=%2Fwiki%2Fchar%2F3074')
  })

  it('preserves HTTP status without turning network and server errors into 404', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 404 })
      .mockResolvedValueOnce({ ok: false, status: 500 })
      .mockRejectedValueOnce(new TypeError('network down'))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchWikiPageByRoute('/wiki/char/missing')).rejects.toMatchObject({ status: 404 })
    await expect(fetchWikiPageByRoute('/wiki/char/failing')).rejects.toMatchObject({ status: 500 })
    await expect(fetchWikiPageByRoute('/wiki/char/offline')).rejects.toBeInstanceOf(TypeError)
  })
})
