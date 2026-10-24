import { useEffect, useRef } from 'react'
import { getMainSnapIds } from '../navigation/mainSectionNavigation'
import { useUIStore } from '../store/uiStore'

const WHEEL_DELTA_THRESHOLD = 24
const WHEEL_NAV_LOCK_MS = 850

function getSnapId(el: HTMLElement) {
  return el.getAttribute('data-snap-section') ?? ''
}

/** 主容器内的扁平叶目标序列:home → data:loading 或全部 data:{key} → chat。 */
function getNavigableSnapTargets(scroller: HTMLElement) {
  const leaves = [...scroller.querySelectorAll<HTMLElement>('[data-snap-section]')]
  return getMainSnapIds(scroller)
    .map((snapId) => leaves.find((el) => getSnapId(el) === snapId))
    .filter((el): el is HTMLElement => el !== undefined)
}

function getActiveSnapId() {
  const { currentSection, currentCategory } = useUIStore.getState()
  if (currentSection === 'data' && currentCategory) return `data:${currentCategory}`
  return currentSection
}

function getClosestSnapIndex(targets: HTMLElement[]) {
  let closestIndex = 0
  let closestDistance = Number.POSITIVE_INFINITY
  for (let index = 0; index < targets.length; index += 1) {
    const distance = Math.abs(targets[index].getBoundingClientRect().top)
    if (distance < closestDistance) {
      closestDistance = distance
      closestIndex = index
    }
  }
  return closestIndex
}

function canScrollInsideLockedRegion(event: WheelEvent) {
  const target = event.target
  if (!(target instanceof Element)) return false

  let searchFrom: Element | null = target
  while (searchFrom) {
    const lockedRegion: HTMLElement | null = searchFrom.closest('[data-page-wheel-lock="true"]')
    if (!lockedRegion) break

    const maxScrollTop = lockedRegion.scrollHeight - lockedRegion.clientHeight
    if (maxScrollTop > 0) {
      if (event.deltaY > 0 && lockedRegion.scrollTop < maxScrollTop) return true
      if (event.deltaY < 0 && lockedRegion.scrollTop > 0) return true
    }
    searchFrom = lockedRegion.parentElement
  }
  return false
}

export function useWheelSnapNavigation(lockMs = WHEEL_NAV_LOCK_MS) {
  const lockedRef = useRef(false)
  const unlockTimerRef = useRef<number | null>(null)

  useEffect(() => {
    const scroller = document.querySelector<HTMLElement>('.snap-container')
    if (!scroller) return

    const unlock = () => {
      lockedRef.current = false
      unlockTimerRef.current = null
    }

    const handleWheel = (event: WheelEvent) => {
      if (event.ctrlKey || Math.abs(event.deltaY) < WHEEL_DELTA_THRESHOLD) return
      if (canScrollInsideLockedRegion(event)) return

      event.preventDefault()
      if (lockedRef.current) return

      const targets = getNavigableSnapTargets(scroller)
      if (targets.length === 0) return

      const activeSnapId = getActiveSnapId()
      const activeIndex = targets.findIndex((target) => getSnapId(target) === activeSnapId)
      const currentIndex = activeIndex >= 0 ? activeIndex : getClosestSnapIndex(targets)
      const direction = event.deltaY > 0 ? 1 : -1
      const nextIndex = Math.min(Math.max(currentIndex + direction, 0), targets.length - 1)
      if (nextIndex === currentIndex) return

      lockedRef.current = true
      targets[nextIndex].scrollIntoView({ behavior: 'smooth', block: 'start' })
      unlockTimerRef.current = window.setTimeout(unlock, lockMs)
    }

    scroller.addEventListener('wheel', handleWheel, { passive: false })
    return () => {
      scroller.removeEventListener('wheel', handleWheel)
      if (unlockTimerRef.current !== null) window.clearTimeout(unlockTimerRef.current)
    }
  }, [lockMs])
}
