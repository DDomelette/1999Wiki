export type MainSnapId = 'home' | 'chat' | 'data:loading' | `data:${string}`

export type MainRouteTarget =
  | { kind: 'home' }
  | { kind: 'chat' }
  | { kind: 'data'; categoryKey?: string }

export interface NavigateMainOptions {
  behavior?: ScrollBehavior
  history?: 'push' | 'replace' | 'none'
}

const DATA_PREFIX = 'data:'

function isMainSnapId(value: string): value is MainSnapId {
  return value === 'home' || value === 'chat' || (value.startsWith(DATA_PREFIX) && value.length > DATA_PREFIX.length)
}

export function mainTargetToHash(target: MainRouteTarget): string {
  if (target.kind === 'home') return '#home'
  if (target.kind === 'chat') return '#chat'
  if (!target.categoryKey) return '#data'
  return `#data/${encodeURIComponent(target.categoryKey)}`
}

export function parseMainHash(hash: string): MainRouteTarget | null {
  if (hash === '#home') return { kind: 'home' }
  if (hash === '#chat') return { kind: 'chat' }
  if (hash === '#data') return { kind: 'data' }
  if (!hash.startsWith('#data/')) return null
  let categoryKey: string
  try {
    categoryKey = decodeURIComponent(hash.slice('#data/'.length))
  } catch {
    return null
  }
  if (!categoryKey) return null
  return { kind: 'data', categoryKey }
}

export function resolveMainSnapId(
  target: MainRouteTarget,
  availableSnapIds: readonly MainSnapId[],
): MainSnapId | null {
  if (target.kind === 'home') return availableSnapIds.includes('home') ? 'home' : null
  if (target.kind === 'chat') return availableSnapIds.includes('chat') ? 'chat' : null
  if (target.categoryKey) {
    const snapId: MainSnapId = `data:${target.categoryKey}`
    return availableSnapIds.includes(snapId) ? snapId : null
  }
  const firstCategory = availableSnapIds.find((id) => id.startsWith(DATA_PREFIX) && id !== 'data:loading')
  if (firstCategory) return firstCategory
  return availableSnapIds.includes('data:loading') ? 'data:loading' : null
}

export function mainSnapIdToTarget(snapId: MainSnapId): MainRouteTarget {
  if (snapId === 'home') return { kind: 'home' }
  if (snapId === 'chat') return { kind: 'chat' }
  if (snapId === 'data:loading') return { kind: 'data' }
  return { kind: 'data', categoryKey: snapId.slice(DATA_PREFIX.length) }
}

export function getMainSnapIds(root: ParentNode = document): MainSnapId[] {
  const ids: MainSnapId[] = []
  root.querySelectorAll('[data-snap-section]').forEach((el) => {
    const value = el.getAttribute('data-snap-section')
    if (value !== null && isMainSnapId(value)) ids.push(value)
  })
  return ids
}

function findSnapTarget(scroller: HTMLElement, snapId: MainSnapId): HTMLElement | null {
  return [...scroller.querySelectorAll<HTMLElement>('[data-snap-section]')]
    .find((el) => el.getAttribute('data-snap-section') === snapId) ?? null
}

export function navigateToMainSection(
  target: MainRouteTarget,
  options: NavigateMainOptions = {},
): boolean {
  const { behavior = 'auto', history = 'none' } = options
  const scroller = document.querySelector<HTMLElement>('.snap-container')
  if (!scroller) return false
  const snapId = resolveMainSnapId(target, getMainSnapIds(scroller))
  if (!snapId) return false
  const element = findSnapTarget(scroller, snapId)
  if (!element) return false

  const scrollerRect = scroller.getBoundingClientRect()
  const targetRect = element.getBoundingClientRect()
  scroller.scrollTo({ top: targetRect.top - scrollerRect.top + scroller.scrollTop, behavior })

  if (history === 'push' || history === 'replace') {
    const url = `${window.location.pathname}${window.location.search}${mainTargetToHash(target)}`
    if (history === 'push') window.history.pushState({}, '', url)
    else window.history.replaceState({}, '', url)
  }
  return true
}
