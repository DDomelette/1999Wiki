import { useEffect } from 'react'
import type { RefObject } from 'react'
import {
  getMainSnapIds,
  mainSnapIdToTarget,
  navigateToMainSection,
} from '../navigation/mainSectionNavigation'

export const CHAT_PAGE_GESTURE_THRESHOLD_PX = 64
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function prefersReducedMotion() {
  return typeof window.matchMedia === 'function' && window.matchMedia(REDUCED_MOTION_QUERY).matches
}

/**
 * 聊天消息区触顶后的下拉手势:导航到主吸附序列中 chat 之前的叶目标。
 * 全程 passive、不 preventDefault、不干预消息区自身滚动;每次手势至多触发一次。
 */
export function useChatPageBoundaryNavigation(
  messageRef: RefObject<HTMLElement | null>,
  thresholdPx = CHAT_PAGE_GESTURE_THRESHOLD_PX,
) {
  useEffect(() => {
    const element = messageRef.current
    if (!element) return

    let startX = 0
    let startY = 0
    let eligible = false
    let triggered = false

    const handleTouchStart = (event: TouchEvent) => {
      const touch = event.touches[0]
      if (!touch) return
      startX = touch.clientX
      startY = touch.clientY
      eligible = element.scrollTop <= 1
      triggered = false
    }

    const handleTouchMove = (event: TouchEvent) => {
      if (!eligible || triggered) return
      const touch = event.touches[0]
      if (!touch) return
      const deltaY = touch.clientY - startY
      const deltaX = touch.clientX - startX
      if (deltaY < thresholdPx || Math.abs(deltaY) <= Math.abs(deltaX)) return

      const scroller =
        element.closest('.snap-container') ?? document.querySelector('.snap-container')
      if (!scroller) return
      const snapIds = getMainSnapIds(scroller)
      const chatIndex = snapIds.indexOf('chat')
      if (chatIndex <= 0) return

      triggered = true
      navigateToMainSection(mainSnapIdToTarget(snapIds[chatIndex - 1]), {
        behavior: prefersReducedMotion() ? 'auto' : 'smooth',
        history: 'replace',
      })
    }

    const resetGesture = () => {
      eligible = false
      triggered = false
    }

    const options: AddEventListenerOptions = { passive: true }
    element.addEventListener('touchstart', handleTouchStart, options)
    element.addEventListener('touchmove', handleTouchMove, options)
    element.addEventListener('touchend', resetGesture, options)
    element.addEventListener('touchcancel', resetGesture, options)

    return () => {
      element.removeEventListener('touchstart', handleTouchStart)
      element.removeEventListener('touchmove', handleTouchMove)
      element.removeEventListener('touchend', resetGesture)
      element.removeEventListener('touchcancel', resetGesture)
    }
  }, [messageRef, thresholdPx])
}
