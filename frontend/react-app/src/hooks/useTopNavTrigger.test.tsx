import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useTopNavTrigger } from './useTopNavTrigger'
import { useUIStore } from '../store/uiStore'

function Probe() {
  useTopNavTrigger()
  return null
}

function setScrollTop(el: HTMLElement, value: number) {
  Object.defineProperty(el, 'scrollTop', {
    configurable: true,
    value,
  })
}

describe('useTopNavTrigger', () => {
  beforeEach(() => {
    document.body.innerHTML = '<main class="snap-container"></main>'
    useUIStore.setState({ topNavVisible: false })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the nav when the snap container scrolls to the top', () => {
    render(<Probe />)
    const scroller = document.querySelector('.snap-container') as HTMLElement

    setScrollTop(scroller, 0)
    scroller.dispatchEvent(new Event('scroll'))

    expect(useUIStore.getState().topNavVisible).toBe(true)
  })

  it('hides the nav when the snap container scrolls away from the top', () => {
    useUIStore.setState({ topNavVisible: true })
    render(<Probe />)
    const scroller = document.querySelector('.snap-container') as HTMLElement

    setScrollTop(scroller, 120)
    scroller.dispatchEvent(new Event('scroll'))

    expect(useUIStore.getState().topNavVisible).toBe(false)
  })

  it('shows the nav after the pointer stays inside the nav height for 700ms', () => {
    vi.useFakeTimers()
    render(<Probe />)
    const scroller = document.querySelector('.snap-container') as HTMLElement

    setScrollTop(scroller, 120)
    scroller.dispatchEvent(new Event('scroll'))
    window.dispatchEvent(new MouseEvent('mousemove', { clientY: 40 }))

    expect(useUIStore.getState().topNavVisible).toBe(false)

    vi.advanceTimersByTime(699)

    expect(useUIStore.getState().topNavVisible).toBe(false)

    vi.advanceTimersByTime(1)

    expect(useUIStore.getState().topNavVisible).toBe(true)

    window.dispatchEvent(new MouseEvent('mousemove', { clientY: 72 }))

    expect(useUIStore.getState().topNavVisible).toBe(false)
  })

  it('cancels the nav reveal when the pointer leaves before 700ms', () => {
    vi.useFakeTimers()
    render(<Probe />)
    const scroller = document.querySelector('.snap-container') as HTMLElement

    setScrollTop(scroller, 120)
    scroller.dispatchEvent(new Event('scroll'))
    window.dispatchEvent(new MouseEvent('mousemove', { clientY: 40 }))
    vi.advanceTimersByTime(500)
    window.dispatchEvent(new MouseEvent('mousemove', { clientY: 72 }))
    vi.advanceTimersByTime(300)

    expect(useUIStore.getState().topNavVisible).toBe(false)
  })
})
