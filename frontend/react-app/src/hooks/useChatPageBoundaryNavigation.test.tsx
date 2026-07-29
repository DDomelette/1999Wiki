import { createEvent, fireEvent, render, screen } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  CHAT_PAGE_GESTURE_THRESHOLD_PX,
  useChatPageBoundaryNavigation,
} from './useChatPageBoundaryNavigation'

function Harness({ onlyChat = false }: { onlyChat?: boolean }) {
  const messageRef = useRef<HTMLDivElement>(null)
  useChatPageBoundaryNavigation(messageRef)

  return (
    <main className="snap-container">
      {!onlyChat && <section data-snap-section="home" />}
      {!onlyChat && <section data-snap-section="data:人物" />}
      <section data-snap-section="chat">
        <div ref={messageRef} data-testid="messages" />
      </section>
    </main>
  )
}

function setScrollMetrics(element: HTMLElement, scrollTop: number) {
  Object.defineProperty(element, 'scrollTop', { configurable: true, value: scrollTop })
  Object.defineProperty(element, 'scrollHeight', { configurable: true, value: 1000 })
  Object.defineProperty(element, 'clientHeight', { configurable: true, value: 300 })
}

function drag(
  messages: HTMLElement,
  from: readonly [number, number],
  to: readonly [number, number],
) {
  fireEvent.touchStart(messages, {
    touches: [{ clientX: from[0], clientY: from[1] }],
  })
  const move = createEvent.touchMove(messages, {
    touches: [{ clientX: to[0], clientY: to[1] }],
  })
  fireEvent(messages, move)
  fireEvent.touchEnd(messages)
  return move
}

describe('useChatPageBoundaryNavigation', () => {
  it('exposes the approved deliberate-gesture threshold', () => {
    expect(CHAT_PAGE_GESTURE_THRESHOLD_PX).toBe(64)
  })

  beforeEach(() => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function prepare(onlyChat = false, scrollTop = 0) {
    const { container, unmount } = render(<Harness onlyChat={onlyChat} />)
    const scroller = container.querySelector('.snap-container') as HTMLElement
    const previous = container.querySelector('[data-snap-section="data:人物"]') as HTMLElement | null
    const messages = screen.getByTestId('messages')
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo
    Object.defineProperty(scroller, 'scrollTop', { configurable: true, value: 800 })
    scroller.getBoundingClientRect = vi.fn(() => ({ top: 0 }) as DOMRect)
    if (previous) {
      previous.getBoundingClientRect = vi.fn(() => ({ top: -100 }) as DOMRect)
    }
    setScrollMetrics(messages, scrollTop)
    return { messages, scrollTo, unmount }
  }

  it('navigates once to the leaf before chat after a deliberate downward drag at the top', () => {
    const replaceState = vi.spyOn(window.history, 'replaceState')
    const { messages, scrollTo } = prepare()

    fireEvent.touchStart(messages, { touches: [{ clientX: 120, clientY: 200 }] })
    const move = createEvent.touchMove(messages, {
      touches: [{ clientX: 122, clientY: 270 }],
    })
    fireEvent(messages, move)
    fireEvent(messages, move)
    fireEvent.touchEnd(messages)

    expect(move.defaultPrevented).toBe(false)
    expect(scrollTo).toHaveBeenCalledTimes(1)
    expect(scrollTo).toHaveBeenCalledWith({ top: 700, behavior: 'smooth' })
    expect(replaceState).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['chat can still scroll toward the top', 40, [120, 200], [122, 280]],
    ['finger moves upward', 0, [120, 200], [122, 150]],
    ['movement stays below threshold', 0, [120, 200], [122, 250]],
    ['horizontal movement dominates', 0, [120, 200], [220, 270]],
    ['gesture begins at the bottom', 700, [120, 200], [122, 280]],
  ] as const)('does nothing when %s', (_name, scrollTop, from, to) => {
    const { messages, scrollTo } = prepare(false, scrollTop)
    drag(messages, from, to)
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('does nothing after touch cancel', () => {
    const { messages, scrollTo } = prepare()
    fireEvent.touchStart(messages, { touches: [{ clientX: 120, clientY: 200 }] })
    fireEvent.touchCancel(messages)
    fireEvent.touchMove(messages, { touches: [{ clientX: 122, clientY: 280 }] })
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('does nothing when chat has no preceding main target', () => {
    const { messages, scrollTo } = prepare(true)
    drag(messages, [120, 200], [122, 280])
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('removes native touch listeners on unmount', () => {
    const { messages, scrollTo, unmount } = prepare()
    unmount()
    drag(messages, [120, 200], [122, 280])
    expect(scrollTo).not.toHaveBeenCalled()
  })
})
