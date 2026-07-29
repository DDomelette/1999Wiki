import { act, render } from '@testing-library/react'
import { createRef } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MainSnapId } from '../navigation/mainSectionNavigation'
import { useMainViewportAlignment } from './useMainViewportAlignment'

class TestVisualViewport extends EventTarget {}

function Harness({ activeSnapId }: { activeSnapId: MainSnapId }) {
  const scrollerRef = createRef<HTMLElement>()
  useMainViewportAlignment(scrollerRef, activeSnapId)

  return (
    <main ref={scrollerRef} className="snap-container">
      <section data-snap-section="home" />
      <section data-snap-section="data:人物" />
      <section data-snap-section="chat">
        <div data-testid="chat-messages" />
      </section>
    </main>
  )
}

describe('useMainViewportAlignment', () => {
  let visualViewport: TestVisualViewport

  beforeEach(() => {
    vi.useFakeTimers()
    visualViewport = new TestVisualViewport()
    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: visualViewport,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: undefined,
    })
  })

  function prepareChatGeometry(container: HTMLElement) {
    const scroller = container.querySelector('.snap-container') as HTMLElement
    const chat = container.querySelector('[data-snap-section="chat"]') as HTMLElement
    const messages = container.querySelector('[data-testid="chat-messages"]') as HTMLElement
    const scrollTo = vi.fn()

    Object.defineProperty(scroller, 'scrollTop', { configurable: true, value: 400 })
    Object.defineProperty(messages, 'scrollTop', { configurable: true, writable: true, value: 321 })
    scroller.scrollTo = scrollTo
    scroller.getBoundingClientRect = vi.fn(() => ({ top: 20 }) as DOMRect)
    chat.getBoundingClientRect = vi.fn(() => ({ top: 620 }) as DOMRect)

    return { messages, scrollTo }
  }

  it('debounces window resize and realigns the active leaf without moving chat history', () => {
    const { container } = render(<Harness activeSnapId="chat" />)
    const { messages, scrollTo } = prepareChatGeometry(container)

    act(() => {
      window.dispatchEvent(new Event('resize'))
      window.dispatchEvent(new Event('resize'))
      vi.advanceTimersByTime(119)
    })
    expect(scrollTo).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(scrollTo).toHaveBeenCalledTimes(1)
    expect(scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: 'auto' })
    expect(messages.scrollTop).toBe(321)
  })

  it('realigns after visual viewport resize', () => {
    const { container } = render(<Harness activeSnapId="chat" />)
    const { scrollTo } = prepareChatGeometry(container)

    act(() => {
      visualViewport.dispatchEvent(new Event('resize'))
      vi.advanceTimersByTime(120)
    })

    expect(scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: 'auto' })
  })

  it('removes resize listeners and pending timers on unmount', () => {
    const { container, unmount } = render(<Harness activeSnapId="chat" />)
    const { scrollTo } = prepareChatGeometry(container)

    act(() => {
      window.dispatchEvent(new Event('resize'))
      unmount()
      vi.advanceTimersByTime(120)
      window.dispatchEvent(new Event('resize'))
      visualViewport.dispatchEvent(new Event('resize'))
      vi.advanceTimersByTime(120)
    })

    expect(scrollTo).not.toHaveBeenCalled()
  })
})
