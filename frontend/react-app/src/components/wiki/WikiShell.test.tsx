import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WikiShell } from './WikiShell'
import * as wikiApi from '../../api/wiki'

vi.mock('../../api/wiki', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/wiki')>()
  return {
    ...actual,
    fetchWikiCategories: vi.fn(),
    fetchWikiPages: vi.fn(),
    fetchWikiPage: vi.fn(),
    fetchWikiPageByRoute: vi.fn(),
    fetchWikiHealth: vi.fn(),
    resolveWikiRoute: vi.fn(),
  }
})

const listItem = {
  pageId: 'char:3074',
  pageType: 'character',
  title: '爱兹拉',
  subtitle: 'Ezra Theodore',
  category: '角色',
  route: '/wiki/char/3074',
  thumbnail: 'https://example.test/ezra.webp',
  summary: '角色摘要',
}

const detail = {
  ...listItem,
  thumbnail: '',
  sourceTitle: 'Data:Char/3074.json',
  content: {
    summary: '角色正文',
    crawlerProjectionVersion: 1,
    blocks: [
      { id: 'inheritance', type: 'table' as const, section: 'inheritance', mediaIds: [], rows: [['洞悉', '效果'], ['洞悉 III', '效果三']] },
      { id: 'portray', type: 'table' as const, section: 'portray', mediaIds: [], rows: [['等级', '效果'], ['LV.1', '一阶'], ['LV.5', '五阶']] },
      { id: 'body', type: 'paragraph' as const, section: 'remainder', mediaIds: [], text: '角色正文' },
    ],
  },
  mediaLinks: [],
  relations: [],
  linkSpans: [],
}

describe('WikiShell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    window.history.replaceState({}, '', '/wiki/character')
    vi.mocked(wikiApi.fetchWikiCategories).mockResolvedValue([{ key: 'character', label: '角色', count: 1, templateGroup: 'character', animationProfile: 'entity-list', themeToken: 'character' }])
    vi.mocked(wikiApi.fetchWikiPages).mockResolvedValue({ items: [listItem], nextCursor: null })
    vi.mocked(wikiApi.fetchWikiPage).mockResolvedValue(detail)
    vi.mocked(wikiApi.fetchWikiPageByRoute).mockResolvedValue(detail)
    vi.mocked(wikiApi.fetchWikiHealth).mockResolvedValue({
      ready: true,
      pageCount: 132,
      categoryCount: 6,
      mediaLinkCount: 1,
      linkSpanCount: 0,
      aliasCount: 0,
      sourceMode: 'mysql',
      buildVersion: 'dev',
      artifactSchemaVersion: '1',
      manifestSha256Prefix: 'abc123',
      stale: false,
      error: '',
    })
    vi.mocked(wikiApi.resolveWikiRoute).mockResolvedValue({ route: null, query: '' })
  })

  it('mounts only the character selection page on the selection route', async () => {
    render(<WikiShell />)
    await waitFor(() => expect(screen.getByRole('link', { name: '首页' })).toBeInTheDocument())
    expect(screen.getByTestId('wiki-shell')).toHaveClass('wiki-shell--selection')
    expect(screen.getByTestId('wiki-character-selection')).toBeInTheDocument()
    expect(screen.queryByTestId('wiki-character-detail')).not.toBeInTheDocument()
    expect(screen.queryByTestId('wiki-category-rail')).not.toBeInTheDocument()
    expect(screen.queryByTestId('wiki-category-hot-zone')).not.toBeInTheDocument()
    expect(screen.getByTestId('wiki-page-index')).toBeInTheDocument()
    expect(screen.queryByTestId('wiki-reader')).not.toBeInTheDocument()
  })

  it('mounts the Kimi selection tree only on the isolated preview route', async () => {
    window.history.replaceState({}, '', '/wiki-preview/character')

    render(<WikiShell variant="kimi-preview" />)

    expect(await screen.findByTestId('wiki-character-selection-preview')).toBeInTheDocument()
    expect(screen.queryByTestId('wiki-character-selection')).not.toBeInTheDocument()
    expect(screen.getByTestId('kimi-character-roster')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-shell')).toHaveAttribute('data-wiki-variant', 'kimi-preview')
  })

  it('shows crawler snapshot diagnostics only in the Kimi preview without blocking the page', async () => {
    window.history.replaceState({}, '', '/wiki-preview/character')
    vi.mocked(wikiApi.fetchWikiHealth).mockResolvedValue({
      ready: true,
      pageCount: 132,
      categoryCount: 6,
      mediaLinkCount: 1,
      linkSpanCount: 0,
      aliasCount: 0,
      sourceMode: 'mysql',
      buildVersion: 'dev',
      artifactSchemaVersion: '1',
      manifestSha256Prefix: 'abc123',
      stale: true,
      error: '',
    })

    render(<WikiShell variant="kimi-preview" />)

    expect(await screen.findByText(/WIKI SNAPSHOT STALE/i)).toBeInTheDocument()
    expect(screen.getByTestId('wiki-character-selection-preview')).toBeInTheDocument()
  })

  it('does not request preview health from the formal Wiki route', async () => {
    render(<WikiShell />)

    await screen.findByTestId('wiki-character-selection')
    expect(wikiApi.fetchWikiHealth).not.toHaveBeenCalled()
  })

  it('keeps preview content available when health fails and exposes a health-only retry', async () => {
    window.history.replaceState({}, '', '/wiki-preview/character')
    vi.mocked(wikiApi.fetchWikiHealth).mockRejectedValue(new wikiApi.WikiApiError(503, '/api/wiki/health'))

    render(<WikiShell variant="kimi-preview" />)

    expect(await screen.findByText('WIKI HEALTH UNAVAILABLE')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-character-selection-preview')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重试 Wiki 健康检查' }))
    await waitFor(() => expect(wikiApi.fetchWikiHealth).toHaveBeenCalledTimes(2))
  })

  it('separates category discovery failure from list data and allows category-only retry', async () => {
    window.history.replaceState({}, '', '/wiki-preview/character')
    vi.mocked(wikiApi.fetchWikiCategories).mockRejectedValue(new wikiApi.WikiApiError(503, '/api/wiki/categories'))

    render(<WikiShell variant="kimi-preview" />)

    expect(await screen.findByText('分类入口暂不可用：HTTP 503')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试 Wiki 分类' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '爱兹拉' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重试 Wiki 分类' }))
    await waitFor(() => expect(wikiApi.fetchWikiCategories).toHaveBeenCalledTimes(2))
  })

  it('distinguishes a selected-character preview failure from a list failure and allows retry', async () => {
    window.history.replaceState({}, '', '/wiki-preview/character')
    vi.mocked(wikiApi.fetchWikiPage).mockRejectedValue(new wikiApi.WikiApiError(503, '/api/wiki/pages/char:3074'))

    render(<WikiShell variant="kimi-preview" />)

    expect(await screen.findByText('角色预览暂不可用：HTTP 503')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试角色预览' })).toBeInTheDocument()
    expect(screen.queryByText(/条目列表暂不可用/)).not.toBeInTheDocument()
  })

  it('distinguishes a missing detail from a temporarily unavailable detail service', async () => {
    window.history.replaceState({}, '', '/wiki-preview/char/3074')
    vi.mocked(wikiApi.fetchWikiPageByRoute).mockRejectedValue(new wikiApi.WikiApiError(404, '/api/wiki/pages/by-route'))
    vi.mocked(wikiApi.resolveWikiRoute).mockResolvedValue({ route: null, query: '3074' })

    const missing = render(<WikiShell variant="kimi-preview" />)
    expect(await screen.findByText('未找到对应 Wiki 档案（HTTP 404）')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '返回角色索引' })).toBeInTheDocument()
    missing.unmount()

    window.history.replaceState({}, '', '/wiki-preview/char/3074')
    vi.mocked(wikiApi.fetchWikiPageByRoute).mockRejectedValue(new wikiApi.WikiApiError(503, '/api/wiki/pages/by-route'))
    render(<WikiShell variant="kimi-preview" />)
    expect(await screen.findByText('Wiki 详情服务暂不可用（HTTP 503）')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试 Wiki 详情' })).toBeInTheDocument()
  })

  it('keeps the official global background visible under the wiki surface', async () => {
    render(<WikiShell />)
    await waitFor(() => expect(screen.getByTestId('wiki-shell')).toBeInTheDocument())
    expect(screen.getByTestId('wiki-shell').style.background).toContain('color-mix')
    expect(screen.getByTestId('wiki-shell').style.backdropFilter).toBeFalsy()
  })

  it('enables document scrolling while mounted', async () => {
    document.body.style.overflow = 'hidden'
    const { unmount } = render(<WikiShell />)
    await waitFor(() => expect(screen.getByTestId('wiki-character-selection')).toBeInTheDocument())
    expect(document.body.style.overflow).toBe('auto')
    unmount()
    expect(document.body.style.overflow).toBe('hidden')
  })

  it('selects a dynamic category from Card Nav and exposes metadata', async () => {
    render(<WikiShell />)
    await waitFor(() => expect(screen.getByRole('button', { name: '展开导航' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '展开导航' }))
    fireEvent.click(screen.getByRole('button', { name: '角色 1' }))
    await waitFor(() => expect(screen.getByTestId('wiki-character-selection')).toHaveAttribute('data-active-category', 'character'))
    expect(screen.getByTestId('wiki-character-selection')).toHaveAttribute('data-template-group', 'character')
  })

  it('loads a detail deep link directly without requesting categories or page lists', async () => {
    window.history.replaceState({}, '', '/wiki/character/3074')

    render(<WikiShell />)

    await waitFor(() => expect(wikiApi.fetchWikiPageByRoute).toHaveBeenCalledWith('/wiki/character/3074'))
    expect(wikiApi.fetchWikiCategories).not.toHaveBeenCalled()
    expect(wikiApi.fetchWikiPages).not.toHaveBeenCalled()
    expect(wikiApi.fetchWikiPage).not.toHaveBeenCalled()
    expect(screen.getByTestId('wiki-character-detail')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-shell')).toHaveClass('wiki-shell--detail')
    expect(screen.queryByTestId('wiki-character-selection')).not.toBeInTheDocument()
    expect(screen.getByTestId('desktop-character-dossier')).toBeInTheDocument()
    expect(screen.getByTestId('character-portrait-stage')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '传承' })).toBeInTheDocument()
    expect(screen.getByText('LV.5')).toBeInTheDocument()
    expect(screen.getByText('角色摘要')).toBeInTheDocument()
  })

  it('requests the canonical API route while preserving a preview detail URL', async () => {
    window.history.replaceState({}, '', '/wiki-preview/char/3074')

    render(<WikiShell variant="kimi-preview" />)

    await waitFor(() => expect(wikiApi.fetchWikiPageByRoute).toHaveBeenCalledWith('/wiki/char/3074'))
    expect(window.location.pathname).toBe('/wiki-preview/char/3074')
    expect(screen.getByTestId('wiki-shell')).toHaveAttribute('data-wiki-variant', 'kimi-preview')
  })

  it('mounts only the Kimi dossier tree on a preview detail route', async () => {
    window.history.replaceState({}, '', '/wiki-preview/char/3074')

    render(<WikiShell variant="kimi-preview" />)

    expect(await screen.findByTestId('kimi-desktop-character-dossier')).toBeInTheDocument()
    expect(screen.queryByTestId('desktop-character-dossier')).not.toBeInTheDocument()
    expect(screen.queryByTestId('wiki-character-detail')).not.toBeInTheDocument()
  })

  it('mounts the mobile dossier tree and keeps voice records as its only nested scroll owner', async () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === '(max-width: 760px)',
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    window.history.replaceState({}, '', '/wiki/character/3074')
    const mobileDetail = {
      ...detail,
      content: {
        ...detail.content,
        blocks: [
          ...detail.content.blocks,
          {
            id: 'voice',
            type: 'voice_reference' as const,
            section: 'voice',
            title: '初遇',
            mediaIds: [],
            text: '初遇\n中文: 我是爱兹拉，很高兴认识你。',
          },
        ],
      },
    }
    vi.mocked(wikiApi.fetchWikiPageByRoute).mockResolvedValue(mobileDetail)

    render(<WikiShell />)

    const mobile = await screen.findByTestId('mobile-character-dossier')
    expect(screen.queryByTestId('desktop-character-dossier')).not.toBeInTheDocument()
    expect([...mobile.querySelectorAll('[data-mobile-module]')].map((item) => item.getAttribute('data-mobile-module'))).toEqual([
      'hero',
      'summary',
      'profile',
      'inheritance',
      'portray',
      'voices',
      'technical',
    ])
    expect(screen.getAllByTestId('character-voice-scroll')).toHaveLength(1)
    expect(mobile.querySelectorAll('.character-detail__nested-scroll')).toHaveLength(1)
    expect(screen.getByText('我是爱兹拉，很高兴认识你。')).toBeInTheDocument()
  })

  it('uses resolver fallback only after a direct detail request returns 404', async () => {
    window.history.replaceState({}, '', '/wiki/character/3074')
    vi.mocked(wikiApi.fetchWikiPageByRoute)
      .mockRejectedValueOnce(new wikiApi.WikiApiError(404, '/api/wiki/pages/by-route'))
      .mockResolvedValueOnce(detail)
    vi.mocked(wikiApi.resolveWikiRoute).mockResolvedValue({ route: '/wiki/char/3074', query: '3074' })

    render(<WikiShell />)

    await waitFor(() => expect(wikiApi.fetchWikiPageByRoute).toHaveBeenCalledTimes(2))
    expect(wikiApi.resolveWikiRoute).toHaveBeenCalledWith({ entityId: '3074' })
    expect(window.location.pathname).toBe('/wiki/char/3074')
  })

  it('does not reinterpret network or server failures as aliases', async () => {
    window.history.replaceState({}, '', '/wiki/character/3074')
    vi.mocked(wikiApi.fetchWikiPageByRoute).mockRejectedValue(new wikiApi.WikiApiError(503, '/api/wiki/pages/by-route'))

    render(<WikiShell />)

    await waitFor(() => expect(screen.getByText(/Wiki 数据暂不可用/)).toBeInTheDocument())
    expect(wikiApi.resolveWikiRoute).not.toHaveBeenCalled()
  })

  it('appends opaque cursor pages without duplicate page IDs', async () => {
    vi.mocked(wikiApi.fetchWikiPages)
      .mockResolvedValueOnce({ items: [listItem, { ...listItem, pageId: 'char:3003', title: '槲寄生', route: '/wiki/char/3003' }], nextCursor: 'opaque-next' })
      .mockResolvedValueOnce({ items: [{ ...listItem, pageId: 'char:3003', title: '槲寄生', route: '/wiki/char/3003' }, { ...listItem, pageId: 'char:3004', title: '星锑', route: '/wiki/char/3004' }], nextCursor: null })

    render(<WikiShell />)
    await waitFor(() => expect(screen.getByRole('button', { name: '加载更多档案' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '加载更多档案' }))

    await waitFor(() => expect(screen.getByRole('button', { name: '星锑' })).toBeInTheDocument())
    expect(screen.getAllByRole('button', { name: '槲寄生' })).toHaveLength(1)
    expect(wikiApi.fetchWikiPages).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: 'opaque-next' }))
  })

  it('keeps loaded items visible when loading the next page returns 503', async () => {
    vi.mocked(wikiApi.fetchWikiPages)
      .mockResolvedValueOnce({ items: [listItem], nextCursor: 'opaque-next' })
      .mockRejectedValueOnce(new wikiApi.WikiApiError(503, '/api/wiki/pages'))

    render(<WikiShell />)
    await waitFor(() => expect(screen.getByRole('button', { name: '爱兹拉' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '加载更多档案' }))

    await waitFor(() => expect(screen.getByText(/列表暂不可用/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '爱兹拉' })).toBeInTheDocument()
    expect(screen.queryByText('暂无页面')).not.toBeInTheDocument()
  })

  it('restores selection filters and scroll state when popstate returns to the index', async () => {
    const selection = {
      category: 'character',
      query: '爱兹拉',
      selectedPageId: 'char:3074',
      listScrollTop: 180,
    }
    window.history.replaceState({ wikiSelection: selection }, '', '/wiki/character')

    render(<WikiShell />)

    await waitFor(() => expect(screen.getByRole('searchbox', { name: '搜索页面' })).toHaveValue('爱兹拉'))
    await waitFor(() => expect(screen.getByTestId('wiki-page-index').scrollTop).toBe(180))
    expect(screen.getByRole('button', { name: '爱兹拉' })).toHaveAttribute('aria-pressed', 'true')
  })
})
