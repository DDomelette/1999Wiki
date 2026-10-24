import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getMainSnapIds,
  mainSnapIdToTarget,
  mainTargetToHash,
  navigateToMainSection,
  parseMainHash,
  resolveMainSnapId,
} from './mainSectionNavigation'

function rect(top: number): DOMRect {
  return { top, left: 0, right: 0, bottom: top, width: 0, height: 0, x: 0, y: top, toJSON: () => ({}) } as DOMRect
}

function mountSnapDom(ids: string[]): HTMLElement {
  const scroller = document.createElement('main')
  scroller.className = 'snap-container'
  for (const id of ids) {
    const section = document.createElement('section')
    section.setAttribute('data-snap-section', id)
    scroller.appendChild(section)
  }
  document.body.appendChild(scroller)
  return scroller
}

function snapTarget(scroller: HTMLElement, id: string): HTMLElement {
  return [...scroller.querySelectorAll<HTMLElement>('[data-snap-section]')]
    .find((el) => el.getAttribute('data-snap-section') === id)!
}

describe('mainTargetToHash', () => {
  it('formats stable targets and encoded category keys', () => {
    expect(mainTargetToHash({ kind: 'home' })).toBe('#home')
    expect(mainTargetToHash({ kind: 'data' })).toBe('#data')
    expect(mainTargetToHash({ kind: 'chat' })).toBe('#chat')
    expect(mainTargetToHash({ kind: 'data', categoryKey: '人物 档案' }))
      .toBe('#data/%E4%BA%BA%E7%89%A9%20%E6%A1%A3%E6%A1%88')
  })
})

describe('parseMainHash', () => {
  it('parses stable targets and encoded category keys', () => {
    expect(parseMainHash('#home')).toEqual({ kind: 'home' })
    expect(parseMainHash('#data')).toEqual({ kind: 'data' })
    expect(parseMainHash('#chat')).toEqual({ kind: 'chat' })
    expect(parseMainHash('#data/%E4%BA%BA%E7%89%A9')).toEqual({
      kind: 'data',
      categoryKey: '人物',
    })
  })

  it('rejects unknown, empty, and malformed hashes', () => {
    expect(parseMainHash('#unknown')).toBeNull()
    expect(parseMainHash('#data/%E0%A4%A')).toBeNull()
    expect(parseMainHash('')).toBeNull()
    expect(parseMainHash('#')).toBeNull()
    expect(parseMainHash('#data/')).toBeNull()
  })
})

describe('resolveMainSnapId', () => {
  it('resolves generic data to the first real category, then the loading panel', () => {
    expect(resolveMainSnapId(
      { kind: 'data' },
      ['home', 'data:人物', 'data:心相', 'chat'] as const,
    )).toBe('data:人物')
    expect(resolveMainSnapId(
      { kind: 'data' },
      ['home', 'data:loading', 'chat'] as const,
    )).toBe('data:loading')
    expect(resolveMainSnapId({ kind: 'data' }, ['home', 'chat'] as const)).toBeNull()
  })

  it('resolves explicit categories and stable targets exactly', () => {
    const available = ['home', 'data:人物', 'data:心相', 'chat'] as const
    expect(resolveMainSnapId({ kind: 'data', categoryKey: '心相' }, available)).toBe('data:心相')
    expect(resolveMainSnapId({ kind: 'data', categoryKey: '缺失' }, available)).toBeNull()
    expect(resolveMainSnapId({ kind: 'home' }, available)).toBe('home')
    expect(resolveMainSnapId({ kind: 'chat' }, available)).toBe('chat')
    expect(resolveMainSnapId({ kind: 'chat' }, ['home', 'data:人物'] as const)).toBeNull()
  })

  it('resolves chat whether data categories are loaded or not', () => {
    expect(resolveMainSnapId({ kind: 'chat' }, ['home', 'data:loading', 'chat'] as const)).toBe('chat')
    expect(resolveMainSnapId({ kind: 'chat' }, ['home', 'data:人物', 'chat'] as const)).toBe('chat')
  })
})

describe('mainSnapIdToTarget', () => {
  it('maps snap ids back to route targets', () => {
    expect(mainSnapIdToTarget('home')).toEqual({ kind: 'home' })
    expect(mainSnapIdToTarget('chat')).toEqual({ kind: 'chat' })
    expect(mainSnapIdToTarget('data:loading')).toEqual({ kind: 'data' })
    expect(mainSnapIdToTarget('data:人物')).toEqual({ kind: 'data', categoryKey: '人物' })
  })
})

describe('getMainSnapIds', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('lists leaf targets in DOM order and ignores the legacy data group shell', () => {
    const scroller = mountSnapDom(['home', 'data', 'data:人物', 'data:loading', 'chat'])
    expect(getMainSnapIds(scroller)).toEqual(['home', 'data:人物', 'data:loading', 'chat'])
    expect(getMainSnapIds()).toEqual(['home', 'data:人物', 'data:loading', 'chat'])
  })

  it('returns an empty list without a snap container', () => {
    expect(getMainSnapIds()).toEqual([])
  })
})

describe('navigateToMainSection', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    window.history.pushState({}, '', '/')
    vi.restoreAllMocks()
  })

  it('scrolls the main container to the target with scroller-relative offset math', () => {
    const scroller = mountSnapDom(['home', 'data:人物', 'chat'])
    scroller.scrollTop = 400
    scroller.getBoundingClientRect = () => rect(20)
    snapTarget(scroller, 'chat').getBoundingClientRect = () => rect(620)
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo

    expect(navigateToMainSection({ kind: 'chat' }, { behavior: 'smooth', history: 'none' })).toBe(true)
    expect(scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: 'smooth' })
  })

  it('resolves generic data to the first real category instead of the legacy shell', () => {
    const scroller = mountSnapDom(['home', 'data', 'data:人物', 'data:心相', 'chat'])
    scroller.getBoundingClientRect = () => rect(0)
    snapTarget(scroller, 'data:人物').getBoundingClientRect = () => rect(300)
    snapTarget(scroller, 'data:心相').getBoundingClientRect = () => rect(600)
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo

    expect(navigateToMainSection({ kind: 'data' }, { behavior: 'auto', history: 'none' })).toBe(true)
    expect(scrollTo).toHaveBeenCalledWith({ top: 300, behavior: 'auto' })
  })

  it('falls back to the loading panel for generic data while categories load', () => {
    const scroller = mountSnapDom(['home', 'data:loading', 'chat'])
    scroller.getBoundingClientRect = () => rect(0)
    snapTarget(scroller, 'data:loading').getBoundingClientRect = () => rect(300)
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo

    expect(navigateToMainSection({ kind: 'data' }, { behavior: 'auto', history: 'none' })).toBe(true)
    expect(scrollTo).toHaveBeenCalledWith({ top: 300, behavior: 'auto' })
  })

  it('restores #chat from the location hash before and after categories load', () => {
    window.history.replaceState({}, '', '/#chat')
    const scroller = mountSnapDom(['home', 'data:loading', 'chat'])
    scroller.getBoundingClientRect = () => rect(0)
    snapTarget(scroller, 'chat').getBoundingClientRect = () => rect(600)
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo

    const pendingTarget = parseMainHash(window.location.hash)
    expect(pendingTarget).toEqual({ kind: 'chat' })
    expect(navigateToMainSection(pendingTarget!, { behavior: 'auto', history: 'none' })).toBe(true)
    expect(scrollTo).toHaveBeenCalledWith({ top: 600, behavior: 'auto' })

    document.body.innerHTML = ''
    const loaded = mountSnapDom(['home', 'data:人物', 'data:心相', 'chat'])
    loaded.getBoundingClientRect = () => rect(0)
    snapTarget(loaded, 'chat').getBoundingClientRect = () => rect(900)
    const loadedScrollTo = vi.fn()
    loaded.scrollTo = loadedScrollTo

    const loadedTarget = parseMainHash(window.location.hash)
    expect(loadedTarget).toEqual({ kind: 'chat' })
    expect(navigateToMainSection(loadedTarget!, { behavior: 'auto', history: 'none' })).toBe(true)
    expect(loadedScrollTo).toHaveBeenCalledWith({ top: 900, behavior: 'auto' })
  })

  it('pushes a history entry when history is push', () => {
    const scroller = mountSnapDom(['home', 'chat'])
    scroller.getBoundingClientRect = () => rect(0)
    snapTarget(scroller, 'chat').getBoundingClientRect = () => rect(300)
    scroller.scrollTo = vi.fn()
    const pushState = vi.spyOn(window.history, 'pushState')
    const replaceState = vi.spyOn(window.history, 'replaceState')

    expect(navigateToMainSection({ kind: 'chat' }, { behavior: 'smooth', history: 'push' })).toBe(true)
    expect(pushState).toHaveBeenCalledWith({}, '', '/#chat')
    expect(replaceState).not.toHaveBeenCalled()
  })

  it('replaces the history entry when history is replace', () => {
    const scroller = mountSnapDom(['home', 'chat'])
    scroller.getBoundingClientRect = () => rect(0)
    snapTarget(scroller, 'chat').getBoundingClientRect = () => rect(300)
    scroller.scrollTo = vi.fn()
    const pushState = vi.spyOn(window.history, 'pushState')
    const replaceState = vi.spyOn(window.history, 'replaceState')

    expect(navigateToMainSection({ kind: 'chat' }, { behavior: 'auto', history: 'replace' })).toBe(true)
    expect(replaceState).toHaveBeenCalledWith({}, '', '/#chat')
    expect(pushState).not.toHaveBeenCalled()
  })

  it('writes no history when history is none', () => {
    const scroller = mountSnapDom(['home', 'chat'])
    scroller.getBoundingClientRect = () => rect(0)
    snapTarget(scroller, 'chat').getBoundingClientRect = () => rect(300)
    scroller.scrollTo = vi.fn()
    const pushState = vi.spyOn(window.history, 'pushState')
    const replaceState = vi.spyOn(window.history, 'replaceState')

    expect(navigateToMainSection({ kind: 'chat' }, { behavior: 'auto', history: 'none' })).toBe(true)
    expect(pushState).not.toHaveBeenCalled()
    expect(replaceState).not.toHaveBeenCalled()
  })

  it('returns false without scrolling or history writes when the target is unavailable', () => {
    const scroller = mountSnapDom(['home', 'chat'])
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo
    const pushState = vi.spyOn(window.history, 'pushState')
    const replaceState = vi.spyOn(window.history, 'replaceState')

    expect(navigateToMainSection({ kind: 'data', categoryKey: '人物' }, { history: 'push' })).toBe(false)
    expect(scrollTo).not.toHaveBeenCalled()
    expect(pushState).not.toHaveBeenCalled()
    expect(replaceState).not.toHaveBeenCalled()
  })

  it('returns false when the snap container is missing', () => {
    const pushState = vi.spyOn(window.history, 'pushState')
    expect(navigateToMainSection({ kind: 'home' }, { history: 'push' })).toBe(false)
    expect(pushState).not.toHaveBeenCalled()
  })
})
