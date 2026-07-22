import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CategoryPanel } from './CategoryPanel'
import type { CategoryMeta } from '../../types'

vi.mock('../ScrollableDescription', () => ({
  ScrollableDescription: ({ text }: { text: string }) => (
    <div data-testid="scrollable-description">{text}</div>
  ),
}))

const meta: CategoryMeta = {
  key: '人物',
  title: '人物',
  subtitle: 'Characters',
  description: '人物资料',
  doc_count: 105,
  cover_prompt: '',
}

let intersectionCallback: IntersectionObserverCallback

describe('CategoryPanel cover media', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ docs: [] }),
    }))
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: IntersectionObserverCallback) {
        intersectionCallback = callback
      }
      observe() {}
      disconnect() {}
    })
  })

  it('uses a character standee image for the character category cover', () => {
    const { container } = render(<CategoryPanel meta={meta} />)

    const image = container.querySelector('img')
    expect(image).toBeInTheDocument()
    expect(image?.getAttribute('src')).toMatch(/^\/images\/characters\/standees\/.+\.(png|jpe?g|webp)$/)
  })

  it('keeps the character cover in a borderless tilted card shell', () => {
    const { container } = render(<CategoryPanel meta={meta} />)

    const card = container.querySelector('[data-testid="tilted-image-card"]')
    const image = container.querySelector('img')

    expect(card).toBeInTheDocument()
    expect(image).toHaveStyle({
      objectFit: 'contain',
      border: 'none',
      boxShadow: 'none',
    })
  })

  it('sizes the tilted cover card as a right-side showcase without covering navigation', () => {
    const { container } = render(<CategoryPanel meta={meta} />)

    const layout = container.querySelector('[data-testid="category-panel-layout"]')
    const card = container.querySelector('[data-testid="tilted-image-card"]')

    expect(layout).toHaveStyle({
      maxWidth: '1680px',
      gridTemplateColumns: 'minmax(320px, 0.72fr) minmax(560px, 1.45fr)',
    })
    expect(card).toHaveStyle({
      width: 'min(42vw, 680px)',
      height: 'min(64vh, 620px)',
    })
  })

  it('loads category docs only after the panel enters the viewport', async () => {
    render(<CategoryPanel meta={meta} />)
    expect(fetch).not.toHaveBeenCalled()

    act(() => {
      intersectionCallback([
        { isIntersecting: true, intersectionRatio: 0.75 } as IntersectionObserverEntry,
      ], {} as IntersectionObserver)
    })

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/category/%E4%BA%BA%E7%89%A9/docs?limit=5')
    })
  })

  it('keeps the category description even when loaded docs contain unusable snippets', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        docs: [
          { name: 'index', source: 'index.md', snippet: '%%' },
          { name: 'poster wall', source: 'poster.md', snippet: 'unrelated poster wall text' },
        ],
      }),
    } as Response)

    render(<CategoryPanel meta={meta} />)

    act(() => {
      intersectionCallback([
        { isIntersecting: true, intersectionRatio: 0.75 } as IntersectionObserverEntry,
      ], {} as IntersectionObserver)
    })

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled()
    })

    expect(screen.getByText(meta.description)).toBeInTheDocument()
    expect(screen.queryByText(/unrelated poster wall text/)).not.toBeInTheDocument()
  })

  it('renders a wiki CTA on the story page and not on hidden category pages', () => {
    const storyMeta: CategoryMeta = {
      key: '剧情',
      title: '剧情',
      subtitle: 'Story',
      description: '主线与支线剧情',
      doc_count: 12,
      cover_prompt: '',
    }

    const { unmount } = render(<CategoryPanel meta={storyMeta} />)

    const link = screen.getByRole('link', { name: /进入WIKI/ })
    expect(link).toHaveAttribute('href', '/wiki')
    unmount()

    const calendarMeta: CategoryMeta = {
      key: '日历',
      title: '日历',
      subtitle: 'Calendar',
      description: '时间记录',
      doc_count: 12,
      cover_prompt: '',
    }
    render(<CategoryPanel meta={calendarMeta} />)
    expect(screen.queryByRole('link', { name: /进入WIKI/ })).not.toBeInTheDocument()
  })
})
