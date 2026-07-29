import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { useUIStore } from './store/uiStore'
import type { CategoryMeta } from './types'

const fetchCategoriesMock = vi.hoisted(() => vi.fn())

const categories: CategoryMeta[] = [
  { key: '人物', title: '人物', subtitle: 'Characters', description: '', doc_count: 0, cover_prompt: '' },
  { key: '心相', title: '心相', subtitle: 'Psychubes', description: '', doc_count: 0, cover_prompt: '' },
]

vi.mock('./api/http', () => ({
  fetchCategories: fetchCategoriesMock,
}))

describe('App wheel snap navigation', () => {
  beforeEach(() => {
    fetchCategoriesMock.mockReset()
    fetchCategoriesMock.mockResolvedValue(categories)
    useUIStore.setState({
      currentSection: 'home',
      currentCategory: null,
      categoriesMeta: [],
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ docs: [] }),
    }))
    vi.stubGlobal('IntersectionObserver', class {
      observe() {}
      disconnect() {}
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('moves only one snap target for repeated wheel events during the cooldown', async () => {
    const { container } = render(<App />)

    await waitFor(() => {
      expect(document.querySelector('[data-snap-section="data:人物"]')).toBeInTheDocument()
      expect(document.querySelector('[data-snap-section="data:心相"]')).toBeInTheDocument()
    })

    vi.useFakeTimers()

    const scroller = container.querySelector('.snap-container') as HTMLElement
    const characterPanel = document.querySelector('[data-snap-section="data:人物"]') as HTMLElement
    const psychubePanel = document.querySelector('[data-snap-section="data:心相"]') as HTMLElement
    const characterScroll = vi.fn()
    const psychubeScroll = vi.fn()
    characterPanel.scrollIntoView = characterScroll
    psychubePanel.scrollIntoView = psychubeScroll

    const firstWheel = new WheelEvent('wheel', { deltaY: 160, bubbles: true, cancelable: true })
    act(() => {
      scroller.dispatchEvent(firstWheel)
    })
    expect(firstWheel.defaultPrevented).toBe(true)
    expect(characterScroll).toHaveBeenCalledTimes(1)

    act(() => {
      useUIStore.setState({ currentSection: 'data', currentCategory: '人物' })
    })
    const repeatedWheel = new WheelEvent('wheel', { deltaY: 160, bubbles: true, cancelable: true })
    act(() => {
      scroller.dispatchEvent(repeatedWheel)
    })
    expect(repeatedWheel.defaultPrevented).toBe(true)
    expect(psychubeScroll).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(850)
    })

    const nextWheel = new WheelEvent('wheel', { deltaY: 160, bubbles: true, cancelable: true })
    act(() => {
      scroller.dispatchEvent(nextWheel)
    })
    expect(nextWheel.defaultPrevented).toBe(true)
    expect(psychubeScroll).toHaveBeenCalledTimes(1)
  })

  it('uses one page-level overlay scrollbar while hiding the data scroller native bar', async () => {
    const { container } = render(<App />)

    await waitFor(() => {
      expect(container.querySelector('[data-snap-section^="data:"]')).toBeInTheDocument()
    })

    vi.useFakeTimers()

    const scroller = container.querySelector('.snap-container') as HTMLElement
    expect(scroller).toHaveClass('native-scrollbar-hidden')

    const globalScrollbar = container.querySelector('[data-testid="global-scrollbar"]') as HTMLElement
    expect(globalScrollbar).toHaveAttribute('data-scrollbar-visible', 'false')

    act(() => {
      scroller.dispatchEvent(new Event('scroll'))
    })
    expect(globalScrollbar).toHaveAttribute('data-scrollbar-visible', 'true')

    act(() => {
      vi.advanceTimersByTime(900)
    })
    expect(globalScrollbar).toHaveAttribute('data-scrollbar-visible', 'false')

    const dataScroller = container.querySelector('[data-testid="data-section-scroll"]') as HTMLElement
    expect(dataScroller).toHaveClass('native-scrollbar-hidden')
    expect(container.querySelector('[data-testid="data-section-scrollbar"]')).not.toBeInTheDocument()
    expect(container.querySelectorAll('.overlay-scrollbar--fixed')).toHaveLength(1)
  })

  it('renders fallback data panels when category metadata fails to load', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    fetchCategoriesMock.mockRejectedValue(new Error('category api failed'))

    render(<App />)

    await waitFor(() => {
      expect(document.querySelector('[data-snap-section^="data:"]')).toBeInTheDocument()
    })
    expect(document.querySelectorAll('[data-snap-section^="data:"]').length).toBeGreaterThan(0)
    expect(consoleError).toHaveBeenCalled()
    consoleError.mockRestore()
  })

  it('flattens data categories into leaf snap targets owned by the main scroller', async () => {
    const { container } = render(<App />)

    await waitFor(() => {
      expect(document.querySelector('[data-snap-section="data:人物"]')).toBeInTheDocument()
      expect(document.querySelector('[data-snap-section="data:心相"]')).toBeInTheDocument()
    })

    const dataScroller = container.querySelector('[data-testid="data-section-scroll"]') as HTMLElement
    expect(dataScroller.scrollHeight).toBe(dataScroller.clientHeight)
    expect(dataScroller).not.toHaveStyle({ overflowY: 'scroll' })
    expect(document.querySelector('[data-snap-section="data"]')).toBeNull()
    expect(document.querySelector('[data-snap-section="data:人物"]')).toBeInTheDocument()

    const flatIds = [...container.querySelectorAll('.snap-container [data-snap-section]')].map(
      (el) => el.getAttribute('data-snap-section'),
    )
    expect(flatIds).toEqual(['home', 'data:人物', 'data:心相', 'chat'])
  })

  it('does not skip the data page while category panels are still unavailable', async () => {
    fetchCategoriesMock.mockReturnValue(new Promise(() => {}))
    const { container } = render(<App />)

    await waitFor(() => {
      expect(document.querySelector('[data-snap-section="data:loading"]')).toBeInTheDocument()
    })

    const flatIds = [...container.querySelectorAll('.snap-container [data-snap-section]')].map(
      (el) => el.getAttribute('data-snap-section'),
    )
    expect(flatIds).toEqual(['home', 'data:loading', 'chat'])

    vi.useFakeTimers()

    const scroller = container.querySelector('.snap-container') as HTMLElement
    const loadingPanel = document.querySelector('[data-snap-section="data:loading"]') as HTMLElement
    const chatSection = document.querySelector('[data-snap-section="chat"]') as HTMLElement
    const loadingScroll = vi.fn()
    const chatScroll = vi.fn()
    loadingPanel.scrollIntoView = loadingScroll
    chatSection.scrollIntoView = chatScroll

    const wheel = new WheelEvent('wheel', { deltaY: 160, bubbles: true, cancelable: true })
    act(() => {
      scroller.dispatchEvent(wheel)
    })

    expect(wheel.defaultPrevented).toBe(true)
    expect(loadingScroll).toHaveBeenCalledTimes(1)
    expect(chatScroll).not.toHaveBeenCalled()
  })

  it('lets an inner description scroller consume wheel input before page navigation', async () => {
    const { container } = render(<App />)

    await waitFor(() => {
      expect(document.querySelector('[data-snap-section="data:人物"]')).toBeInTheDocument()
      expect(document.querySelector('[data-snap-section="data:心相"]')).toBeInTheDocument()
    })

    act(() => {
      useUIStore.setState({ currentSection: 'data', currentCategory: '人物' })
    })

    const scroller = container.querySelector('.snap-container') as HTMLElement
    const psychubePanel = document.querySelector('[data-snap-section="data:心相"]') as HTMLElement
    const psychubeScroll = vi.fn()
    psychubePanel.scrollIntoView = psychubeScroll

    const innerScroller = document.createElement('div')
    innerScroller.setAttribute('data-page-wheel-lock', 'true')
    Object.defineProperty(innerScroller, 'scrollTop', { value: 10, configurable: true })
    Object.defineProperty(innerScroller, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(innerScroller, 'clientHeight', { value: 300, configurable: true })
    scroller.appendChild(innerScroller)

    const innerWheel = new WheelEvent('wheel', { deltaY: 160, bubbles: true, cancelable: true })
    act(() => {
      innerScroller.dispatchEvent(innerWheel)
    })

    expect(innerWheel.defaultPrevented).toBe(false)
    expect(psychubeScroll).not.toHaveBeenCalled()
  })

  it('falls through a voice scroller boundary to a scrollable chat ancestor before page navigation', async () => {
    const { container } = render(<App />)

    await waitFor(() => {
      expect(container.querySelector('[data-testid="chat-message-scroll"]')).toBeInTheDocument()
    })

    act(() => {
      useUIStore.setState({ currentSection: 'chat', currentCategory: null })
    })

    const chatScroller = container.querySelector('[data-testid="chat-message-scroll"]') as HTMLElement
    const voiceScroller = document.createElement('div')
    voiceScroller.setAttribute('data-page-wheel-lock', 'true')
    chatScroller.appendChild(voiceScroller)

    Object.defineProperty(voiceScroller, 'scrollTop', { value: 700, configurable: true })
    Object.defineProperty(voiceScroller, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(voiceScroller, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(chatScroller, 'scrollTop', { value: 100, configurable: true })
    Object.defineProperty(chatScroller, 'scrollHeight', { value: 1200, configurable: true })
    Object.defineProperty(chatScroller, 'clientHeight', { value: 400, configurable: true })

    const wheel = new WheelEvent('wheel', { deltaY: 160, bubbles: true, cancelable: true })
    act(() => {
      voiceScroller.dispatchEvent(wheel)
    })

    expect(wheel.defaultPrevented).toBe(false)
  })

  it('lets the chat message scroller consume wheel input until it reaches the top', async () => {
    const { container } = render(<App />)
    const secondDataKey = categories[1].key

    await waitFor(() => {
      expect(document.querySelector(`[data-snap-section="data:${secondDataKey}"]`)).toBeInTheDocument()
    })

    act(() => {
      useUIStore.setState({ currentSection: 'chat', currentCategory: null })
    })

    const dataPanel = document.querySelector(`[data-snap-section="data:${secondDataKey}"]`) as HTMLElement
    const dataScroll = vi.fn()
    dataPanel.scrollIntoView = dataScroll

    const chatScroller = container.querySelector('[data-testid="chat-message-scroll"]') as HTMLElement
    expect(chatScroller).toHaveClass('native-scrollbar-hidden')
    expect(chatScroller).toHaveAttribute('data-page-wheel-lock', 'true')
    expect(container.querySelector('[data-testid="chat-message-scrollbar"]')).toBeInTheDocument()

    Object.defineProperty(chatScroller, 'scrollTop', { value: 32, configurable: true })
    Object.defineProperty(chatScroller, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(chatScroller, 'clientHeight', { value: 300, configurable: true })

    const innerWheel = new WheelEvent('wheel', { deltaY: -160, bubbles: true, cancelable: true })
    act(() => {
      chatScroller.dispatchEvent(innerWheel)
    })

    expect(innerWheel.defaultPrevented).toBe(false)
    expect(dataScroll).not.toHaveBeenCalled()

    Object.defineProperty(chatScroller, 'scrollTop', { value: 0, configurable: true })

    const boundaryWheel = new WheelEvent('wheel', { deltaY: -160, bubbles: true, cancelable: true })
    act(() => {
      chatScroller.dispatchEvent(boundaryWheel)
    })

    expect(boundaryWheel.defaultPrevented).toBe(true)
    expect(dataScroll).toHaveBeenCalledTimes(1)
  })
})
