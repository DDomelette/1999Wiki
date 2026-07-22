import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { vi } from 'vitest'
import { KeywordText } from './KeywordText'

describe('KeywordText', () => {
  it('renders multiple and repeated spans from API data', () => {
    render(
      <KeywordText
        text="维尔汀见到维尔汀和十四行诗。"
        spans={[
          { text: '维尔汀', targetRoute: '/wiki/char/3001', confidence: 0.95 },
          { text: '维尔汀', targetRoute: '/wiki/char/3001', confidence: 0.95 },
          { text: '十四行诗', targetRoute: '/wiki/char/3002', confidence: 0.95 },
        ]}
      />,
    )

    expect(screen.getAllByRole('link', { name: '维尔汀' })).toHaveLength(2)
    expect(screen.getByRole('link', { name: '十四行诗' })).toHaveAttribute('href', '/wiki/char/3002')
  })

  it('does not create empty links for missing routes', () => {
    render(<KeywordText text="未知实体" spans={[{ text: '未知实体', targetRoute: '', confidence: 0.2 }]} />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('未知实体')).toBeInTheDocument()
  })

  it('validates routes before navigation when a validator is provided', async () => {
    const validateRoute = vi.fn().mockResolvedValue('/wiki/char/3001')
    const onNavigate = vi.fn()

    render(
      <KeywordText
        text="维尔汀"
        spans={[{ text: '维尔汀', targetRoute: '/wiki/char/3001', confidence: 0.95 }]}
        validateRoute={validateRoute}
        onNavigate={onNavigate}
      />,
    )

    fireEvent.click(screen.getByRole('link', { name: '维尔汀' }))

    await waitFor(() => expect(validateRoute).toHaveBeenCalledWith({
      text: '维尔汀',
      targetRoute: '/wiki/char/3001',
      confidence: 0.95,
    }))
    expect(onNavigate).toHaveBeenCalledWith('/wiki/char/3001')
  })

  it('falls back to wiki search when route validation cannot resolve a target', async () => {
    const validateRoute = vi.fn().mockResolvedValue(null)
    const onNavigate = vi.fn()

    render(
      <KeywordText
        text="未知实体"
        spans={[{ text: '未知实体', targetRoute: '/wiki/missing', confidence: 0.6 }]}
        validateRoute={validateRoute}
        onNavigate={onNavigate}
      />,
    )

    fireEvent.click(screen.getByRole('link', { name: '未知实体' }))

    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith('/wiki?q=%E6%9C%AA%E7%9F%A5%E5%AE%9E%E4%BD%93'))
  })
})
