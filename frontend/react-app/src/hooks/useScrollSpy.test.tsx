import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useScrollSpy } from './useScrollSpy'
import { useUIStore } from '../store/uiStore'

type ObserverRecord = {
  callback: IntersectionObserverCallback
  options?: IntersectionObserverInit
}

const records: ObserverRecord[] = []
const observed: Element[] = []

function Probe() {
  useScrollSpy()
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
    scroller.appendChild(section)
    leaves.set(id, section)
  }
  document.body.appendChild(scroller)
  return { scroller, leaves }
}

function intersectingEntry(target: Element): IntersectionObserverEntry {
  return { isIntersecting: true, intersectionRatio: 0.6, target } as IntersectionObserverEntry
}

describe('useScrollSpy', () => {
  beforeEach(() => {
    records.length = 0
    observed.length = 0
    useUIStore.setState({ currentSection: 'home', currentCategory: null })
    vi.stubGlobal('IntersectionObserver', class {
      callback: IntersectionObserverCallback
      options?: IntersectionObserverInit
      constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
        this.callback = callback
        this.options = options
        records.push({ callback, options })
      }
      observe(el: Element) {
        observed.push(el)
      }
      disconnect() {}
    })
  })

  it('constructs the observer with the main snap container as root', () => {
    const { scroller } = mountSnapDom(['home'])
    render(<Probe />)

    expect(records).toHaveLength(1)
    expect(records[0].options?.root).toBe(scroller)
  })

  it('observes only leaf snap targets under the main scroller', async () => {
    const { scroller, leaves } = mountSnapDom(['home', 'data:人物', 'chat'])
    const outside = document.createElement('section')
    outside.setAttribute('data-snap-section', 'data:外部')
    document.body.appendChild(outside)

    render(<Probe />)

    expect(observed).toContain(leaves.get('home'))
    expect(observed).toContain(leaves.get('data:人物'))
    expect(observed).toContain(leaves.get('chat'))
    expect(observed).not.toContain(outside)
    expect(scroller.contains(outside)).toBe(false)
  })

  it('observes leaf targets added under the scroller after the hook mounts', async () => {
    const { scroller } = mountSnapDom(['home'])
    render(<Probe />)

    const dynamicSection = document.createElement('section')
    dynamicSection.setAttribute('data-snap-section', 'data:人物')
    scroller.appendChild(dynamicSection)

    await waitFor(() => {
      expect(observed).toContain(dynamicSection)
    })
  })

  it('maps data:loading to the data section without selecting a category', () => {
    const { leaves } = mountSnapDom(['home', 'data:loading', 'chat'])
    render(<Probe />)

    const loadingLeaf = leaves.get('data:loading') as HTMLElement
    act(() => {
      records[0].callback([intersectingEntry(loadingLeaf)], {} as IntersectionObserver)
    })

    expect(useUIStore.getState().currentSection).toBe('data')
    expect(useUIStore.getState().currentCategory).toBeNull()
  })

  it('keeps category selection for real data leaves', () => {
    const { leaves } = mountSnapDom(['home', 'data:人物', 'chat'])
    render(<Probe />)

    const characterLeaf = leaves.get('data:人物') as HTMLElement
    act(() => {
      records[0].callback([intersectingEntry(characterLeaf)], {} as IntersectionObserver)
    })

    expect(useUIStore.getState().currentSection).toBe('data')
    expect(useUIStore.getState().currentCategory).toBe('人物')
  })
})
