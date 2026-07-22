import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PageIndex } from './PageIndex'

const page = {
  pageId: 'char:3074',
  title: '爱兹拉',
  meta: 'character · char:3074',
  thumbnail: 'https://example.test/ezra.webp',
  route: '/wiki/char/3074',
  summary: '不应显示的长摘要',
}

const baseProps = {
  pages: [page],
  selectedPageId: '',
  query: '',
  activeCategoryLabel: '角色',
  loading: false,
  loadingMore: false,
  error: '',
  loadedCount: 30,
  totalCount: 132,
  hasMore: true,
  restoreScrollTop: 0,
  onQueryChange: vi.fn(),
  onSelect: vi.fn(),
  onScrollTopChange: vi.fn(),
  onLoadMore: vi.fn(),
  onRetry: vi.fn(),
}

describe('PageIndex', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders only stable thumbnail, name and meta for each selectable entry', () => {
    const onSelect = vi.fn()
    const { container } = render(<PageIndex {...baseProps} onSelect={onSelect} selectedPageId="char:3074" />)

    expect(screen.getByText('character · char:3074')).toBeInTheDocument()
    expect(screen.queryByText('不应显示的长摘要')).not.toBeInTheDocument()
    expect(container.querySelector('img')).toHaveAttribute('src', page.thumbnail)
    expect(screen.getByRole('button', { name: /爱兹拉/ })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: /爱兹拉/ }))
    expect(onSelect).toHaveBeenCalledWith('char:3074')
  })

  it('uses a fixed placeholder when a thumbnail is unavailable', () => {
    render(<PageIndex {...baseProps} pages={[{ ...page, pageId: 'char:1', thumbnail: '' }]} />)

    expect(screen.getByTestId('wiki-index-placeholder')).toBeInTheDocument()
  })

  it('replaces a failed remote thumbnail with the same fixed placeholder', () => {
    const { container } = render(<PageIndex {...baseProps} />)
    const image = container.querySelector('img')

    expect(image).not.toBeNull()
    fireEvent.error(image as HTMLImageElement)

    expect(container.querySelector('img')).not.toBeInTheDocument()
    expect(screen.getByTestId('wiki-index-placeholder')).toBeInTheDocument()
  })

  it('keeps search and loaded items visible while showing an error with retry', () => {
    const onRetry = vi.fn()
    render(<PageIndex {...baseProps} error="HTTP 503" onRetry={onRetry} />)

    expect(screen.getByRole('searchbox', { name: '搜索页面' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /爱兹拉/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试条目列表' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: '重试条目列表' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('distinguishes loading and successful empty results', () => {
    const { rerender } = render(<PageIndex {...baseProps} pages={[]} loading />)
    expect(screen.getByText('正在读取档案索引...')).toBeInTheDocument()
    expect(screen.queryByText('暂无匹配档案')).not.toBeInTheDocument()

    rerender(<PageIndex {...baseProps} pages={[]} loading={false} loadedCount={0} totalCount={0} hasMore={false} />)
    expect(screen.getByText('暂无匹配档案')).toBeInTheDocument()
  })

  it('restores scroll and reports throttled scroll changes', () => {
    let frame: FrameRequestCallback | undefined
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frame = callback
      return 1
    })
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined)
    const onScrollTopChange = vi.fn()
    render(<PageIndex {...baseProps} restoreScrollTop={180} onScrollTopChange={onScrollTopChange} />)
    const index = screen.getByTestId('wiki-page-index')
    expect(index.scrollTop).toBe(180)

    index.scrollTop = 260
    fireEvent.scroll(index)
    expect(onScrollTopChange).not.toHaveBeenCalled()
    act(() => frame?.(0))
    expect(onScrollTopChange).toHaveBeenCalledWith(260)
  })

  it('shows loaded totals and a stable load-more command only when available', () => {
    const onLoadMore = vi.fn()
    const { rerender } = render(<PageIndex {...baseProps} onLoadMore={onLoadMore} />)

    expect(screen.getByText('已载入 30 / 132')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '加载更多档案' }))
    expect(onLoadMore).toHaveBeenCalledTimes(1)

    rerender(<PageIndex {...baseProps} hasMore={false} />)
    expect(screen.queryByRole('button', { name: '加载更多档案' })).not.toBeInTheDocument()

    rerender(<PageIndex {...baseProps} loadingMore />)
    expect(screen.getByRole('button', { name: '正在加载更多档案' })).toBeDisabled()
  })
})
