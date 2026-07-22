import { useEffect, useRef } from 'react'
import { HOVER_REVEAL_DELAY_MS, TOP_NAV_HEIGHT } from '../constants/layout'
import { useUIStore } from '../store/uiStore'

/** Show TopNav at the first page, or after the pointer stays in the nav area. */
export function useTopNavTrigger() {
  const hoverTimerRef = useRef<number | null>(null)
  const pointerInsideNavRef = useRef(false)

  useEffect(() => {
    const scroller = document.querySelector<HTMLElement>('.snap-container')
    const getScrollTop = () => scroller?.scrollTop ?? window.scrollY

    const clearHoverTimer = () => {
      if (hoverTimerRef.current !== null) {
        window.clearTimeout(hoverTimerRef.current)
        hoverTimerRef.current = null
      }
    }

    const scheduleHoverReveal = () => {
      if (hoverTimerRef.current !== null || useUIStore.getState().topNavVisible) return
      hoverTimerRef.current = window.setTimeout(() => {
        hoverTimerRef.current = null
        if (pointerInsideNavRef.current && getScrollTop() >= 50) {
          useUIStore.getState().setTopNav(true)
        }
      }, HOVER_REVEAL_DELAY_MS)
    }

    const syncFromScroll = () => {
      if (getScrollTop() < 50) {
        clearHoverTimer()
        useUIStore.getState().setTopNav(true)
      } else if (pointerInsideNavRef.current) {
        scheduleHoverReveal()
      } else {
        useUIStore.getState().setTopNav(false)
      }
    }

    const onMouseMove = (e: MouseEvent) => {
      if (getScrollTop() < 50) {
        clearHoverTimer()
        useUIStore.getState().setTopNav(true)
        return
      }

      pointerInsideNavRef.current = e.clientY <= TOP_NAV_HEIGHT

      if (pointerInsideNavRef.current) {
        scheduleHoverReveal()
      } else {
        clearHoverTimer()
        useUIStore.getState().setTopNav(false)
      }
    }

    const onScroll = () => syncFromScroll()

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('scroll', onScroll, { passive: true })
    scroller?.addEventListener('scroll', onScroll, { passive: true })
    syncFromScroll()

    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('scroll', onScroll)
      scroller?.removeEventListener('scroll', onScroll)
      clearHoverTimer()
    }
  }, [])
}
