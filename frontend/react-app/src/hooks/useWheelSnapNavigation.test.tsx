import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWheelSnapNavigation } from './useWheelSnapNavigation'
import { useUIStore } from '../store/uiStore'

function Probe() {
  useWheelSnapNavigation()
  return null
}

function mountSnapDom(ids: string[]) {
  document.body.innerHTML = ''
  const scroller = document.createElement('main')
  scroller.className = 'snap-container'
  const leaves = new Map<string, HTMLElement>()
  for (const id of ids) {
    const section = document.createElement('section')
    section.setAttribute('data-snap-section', id)
    section.scrollIntoView = vi.fn()
    scroller.appendChild(section)
    leaves.set(id, section)
  }
  document.body.appendChild(scroller)
  return { scroller, leaves }
}

function scrollIntoViewMock(leaf: HTMLElement | undefined) {
  return leaf?.scrollIntoView as ReturnType<typeof vi.fn>
}

function dispatchWheel(target: Element, init: WheelEventInit = { deltaY: 160 }) {
  const event = new WheelEvent('wheel', { bubbles: true, cancelable: true, ...init })
  act(() => {
    target.dispatchEvent(event)
  })
  return event
}

describe('useWheelSnapNavigation', () => {
  beforeEach(() => {
    useUIStore.setState({ currentSection: 'home', currentCategory: null })
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('follows the flat sequence home → data:loading → chat', () => {
    vi.useFakeTimers()
    const { scroller, leaves } = mountSnapDom(['home', 'data:loading', 'chat'])
    render(<Probe />)

    dispatchWheel(scroller)
    expect(scrollIntoViewMock(leaves.get('data:loading'))).toHaveBeenCalledTimes(1)
    expect(scrollIntoViewMock(leaves.get('chat'))).not.toHaveBeenCalled()

    act(() => {
      useUIStore.setState({ currentSection: 'chat', currentCategory: null })
      vi.advanceTimersByTime(900)
    })

    dispatchWheel(scroller, { deltaY: -160 })
    expect(scrollIntoViewMock(leaves.get('data:loading'))).toHaveBeenCalledTimes(2)
    expect(scrollIntoViewMock(leaves.get('home'))).not.toHaveBeenCalled()
  })

  it('ignores snap targets outside the main scroller', () => {
    const { scroller, leaves } = mountSnapDom(['home', 'chat'])
    const outside = document.createElement('section')
    outside.setAttribute('data-snap-section', 'data:外部')
    outside.scrollIntoView = vi.fn()
    document.body.appendChild(outside)
    render(<Probe />)

    act(() => {
      useUIStore.setState({ currentSection: 'data', currentCategory: '外部' })
    })

    dispatchWheel(scroller)
    expect(outside.scrollIntoView).not.toHaveBeenCalled()
    expect(scrollIntoViewMock(leaves.get('chat'))).toHaveBeenCalledTimes(1)
  })

  it('never navigates to a synthetic data parent target', () => {
    const { scroller, leaves } = mountSnapDom(['home', 'data', 'chat'])
    render(<Probe />)

    dispatchWheel(scroller)
    expect(scrollIntoViewMock(leaves.get('data'))).not.toHaveBeenCalled()
    expect(scrollIntoViewMock(leaves.get('chat'))).toHaveBeenCalledTimes(1)
  })

  it('moves only one snap target per lock window', () => {
    vi.useFakeTimers()
    const { scroller, leaves } = mountSnapDom(['home', 'data:人物', 'data:心相', 'chat'])
    render(<Probe />)

    dispatchWheel(scroller)
    dispatchWheel(scroller)
    expect(scrollIntoViewMock(leaves.get('data:人物'))).toHaveBeenCalledTimes(1)
    expect(scrollIntoViewMock(leaves.get('data:心相'))).not.toHaveBeenCalled()

    act(() => {
      useUIStore.setState({ currentSection: 'data', currentCategory: '人物' })
      vi.advanceTimersByTime(900)
    })

    dispatchWheel(scroller)
    expect(scrollIntoViewMock(leaves.get('data:心相'))).toHaveBeenCalledTimes(1)
  })

  it('ignores ctrl-wheel and sub-threshold deltas', () => {
    const { scroller, leaves } = mountSnapDom(['home', 'chat'])
    render(<Probe />)

    const ctrlWheel = dispatchWheel(scroller, { deltaY: 160, ctrlKey: true })
    expect(ctrlWheel.defaultPrevented).toBe(false)

    const smallWheel = dispatchWheel(scroller, { deltaY: 10 })
    expect(smallWheel.defaultPrevented).toBe(false)

    expect(scrollIntoViewMock(leaves.get('chat'))).not.toHaveBeenCalled()
  })

  it('lets a nested wheel-lock region consume wheel input first', () => {
    const { scroller, leaves } = mountSnapDom(['home', 'chat'])
    render(<Probe />)

    const inner = document.createElement('div')
    inner.setAttribute('data-page-wheel-lock', 'true')
    Object.defineProperty(inner, 'scrollTop', { value: 10, configurable: true })
    Object.defineProperty(inner, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(inner, 'clientHeight', { value: 300, configurable: true })
    scroller.appendChild(inner)

    const event = dispatchWheel(inner)
    expect(event.defaultPrevented).toBe(false)
    expect(scrollIntoViewMock(leaves.get('chat'))).not.toHaveBeenCalled()
  })
})
