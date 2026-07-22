import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { KimiWikiPreviewViewModel } from './kimiWikiPreviewViewModel'
import { KimiWikiCharacterSelectionPage } from './KimiWikiCharacterSelectionPage'

const model: KimiWikiPreviewViewModel = {
  entries: [
    {
      pageId: 'char:3003',
      title: '槲寄生',
      subtitle: 'Druvis III',
      summary: '林间的神秘学家。',
      summaryFacts: [{ label: 'Rarity', value: '5' }],
      summaryParagraphs: ['A mystic artist.', 'Lives in Europe.'],
      canonicalRoute: '/wiki/char/3003',
      thumbnail: 'https://media.test/thumb.webp',
      selected: true,
    },
    {
      pageId: 'char:3004',
      title: '红弩箭',
      subtitle: 'Regulus',
      summary: '海上的摇滚船长。',
      summaryFacts: [],
      summaryParagraphs: ['Rock-and-roll captain.'],
      canonicalRoute: '/wiki/char/3004',
      thumbnail: '',
      selected: false,
    },
  ],
  selected: {
    pageId: 'char:3003',
    title: '槲寄生',
    subtitle: 'Druvis III',
    summary: '林间的神秘学家。',
    summaryFacts: [{ label: 'Rarity', value: '5' }],
    summaryParagraphs: ['A mystic artist.', 'Lives in Europe.'],
    canonicalRoute: '/wiki/char/3003',
    thumbnail: 'https://media.test/thumb.webp',
    selected: true,
    portrait: {
      id: 'portrait-initial',
      url: 'https://media.test/portrait.webp',
      title: '槲寄生初始立绘',
      role: 'portrait',
      variant: 'initial',
    },
    backdrop: {
      id: 'backdrop-library',
      url: 'https://media.test/backdrop.webp',
      title: '档案室背景',
      role: 'backdrop',
      variant: '',
    },
  },
  detail: null,
}

function renderPage(overrides: Partial<React.ComponentProps<typeof KimiWikiCharacterSelectionPage>> = {}) {
  const props: React.ComponentProps<typeof KimiWikiCharacterSelectionPage> = {
    model,
    query: '',
    activeCategoryLabel: '角色',
    loading: false,
    loadingMore: false,
    error: '',
    previewError: '',
    loadedCount: 30,
    totalCount: 132,
    hasMore: true,
    restoreScrollTop: 0,
    canOpenDetail: true,
    onQueryChange: vi.fn(),
    onSelect: vi.fn(),
    onScrollTopChange: vi.fn(),
    onLoadMore: vi.fn(),
    onRetry: vi.fn(),
    onRetryPreview: vi.fn(),
    onOpenDetail: vi.fn(),
    ...overrides,
  }
  return { ...render(<KimiWikiCharacterSelectionPage {...props} />), props }
}

describe('KimiWikiCharacterSelectionPage', () => {
  it('renders the approved archive workspace and connects selection, search, paging and detail actions', () => {
    const { props } = renderPage()

    expect(screen.getByTestId('wiki-character-selection-preview')).toBeInTheDocument()
    expect(screen.getByText('ARCHIVE INDEX')).toBeInTheDocument()
    expect(screen.getByText('132')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '槲寄生' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('img', { name: '槲寄生初始立绘' })).toHaveAttribute('src', 'https://media.test/portrait.webp')
    expect(screen.getByTestId('kimi-personnel-facts')).toHaveTextContent('Rarity5')
    expect(screen.getByTestId('kimi-personnel-copy')).toHaveTextContent('A mystic artist.')
    expect(screen.getByTestId('kimi-personnel-copy')).toHaveTextContent('Lives in Europe.')

    fireEvent.change(screen.getByRole('searchbox', { name: '搜索页面' }), { target: { value: '露西' } })
    expect(props.onQueryChange).toHaveBeenCalledWith('露西')
    fireEvent.click(screen.getByRole('button', { name: '红弩箭' }))
    expect(props.onSelect).toHaveBeenCalledWith('char:3004')
    fireEvent.click(screen.getByRole('button', { name: '加载更多档案' }))
    expect(props.onLoadMore).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: '查看完整档案' }))
    expect(props.onOpenDetail).toHaveBeenCalledTimes(1)
  })

  it('keeps loaded entries visible during list failure and exposes retry', () => {
    const { props } = renderPage({ error: 'HTTP 503' })

    expect(screen.getByRole('button', { name: '槲寄生' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('HTTP 503')
    fireEvent.click(screen.getByRole('button', { name: '重试条目列表' }))
    expect(props.onRetry).toHaveBeenCalledTimes(1)
  })

  it('shows stable empty, loading and media fallback states without enabling an invalid route', () => {
    const emptyModel: KimiWikiPreviewViewModel = { entries: [], selected: null, detail: null }
    const { rerender, props } = renderPage({
      model: emptyModel,
      loading: true,
      hasMore: false,
      canOpenDetail: false,
    })

    expect(screen.getByText('正在读取档案索引...')).toBeInTheDocument()
    expect(screen.getByText('MEDIA UNAVAILABLE')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看完整档案' })).toBeDisabled()

    rerender(<KimiWikiCharacterSelectionPage {...props} loading={false} />)
    expect(screen.getByText('暂无匹配档案')).toBeInTheDocument()
  })
})
