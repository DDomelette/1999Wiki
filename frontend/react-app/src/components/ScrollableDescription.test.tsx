import { act, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ScrollableDescription } from './ScrollableDescription'

describe('ScrollableDescription', () => {
  it('keeps long text inside a bounded scroll region and reveals the scrollbar while scrolling', () => {
    vi.useFakeTimers()
    const longText = '长文本'.repeat(200)
    const { getByTestId } = render(<ScrollableDescription text={longText} start />)

    const region = getByTestId('scrollable-description')
    expect(region.parentElement).toHaveStyle({
      marginTop: '28px',
    })
    expect(region).toHaveStyle({
      maxHeight: 'clamp(320px, 50vh, 580px)',
      overflowY: 'auto',
    })
    expect(region).toHaveAttribute('data-scrollbar-visible', 'false')
    expect(region).toHaveClass('native-scrollbar-hidden')

    const overlay = getByTestId('scrollable-description-scrollbar')
    expect(overlay).toHaveAttribute('data-scrollbar-visible', 'false')

    act(() => {
      region.dispatchEvent(new WheelEvent('wheel', { deltaY: 120, bubbles: true, cancelable: true }))
    })
    expect(region).toHaveAttribute('data-scrollbar-visible', 'true')
    expect(overlay).toHaveAttribute('data-scrollbar-visible', 'true')

    act(() => {
      vi.advanceTimersByTime(900)
    })
    expect(region).toHaveAttribute('data-scrollbar-visible', 'false')
    expect(overlay).toHaveAttribute('data-scrollbar-visible', 'false')

    vi.useRealTimers()
  })
})
