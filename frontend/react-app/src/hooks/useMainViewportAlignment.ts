import { useEffect } from 'react'
import type { RefObject } from 'react'
import type { MainSnapId } from '../navigation/mainSectionNavigation'
import { mainSnapIdToTarget, navigateToMainSection } from '../navigation/mainSectionNavigation'

const DEFAULT_DELAY_MS = 120

/**
 * 视口尺寸变化(window resize / visualViewport resize)后,去抖地重新对齐主吸附容器
 * 到当前活动叶目标;不写历史、不监听 scroll,也不触碰聊天消息区滚动位置。
 */
export function useMainViewportAlignment(
  scrollerRef: RefObject<HTMLElement | null>,
  activeSnapId: MainSnapId,
  delayMs = DEFAULT_DELAY_MS,
) {
  useEffect(() => {
    let timer: number | null = null

    const realign = () => {
      timer = null
      navigateToMainSection(mainSnapIdToTarget(activeSnapId), { behavior: 'auto', history: 'none' })
    }

    const scheduleRealign = () => {
      if (timer !== null) window.clearTimeout(timer)
      timer = window.setTimeout(realign, delayMs)
    }

    const visualViewport = window.visualViewport
    window.addEventListener('resize', scheduleRealign)
    visualViewport?.addEventListener('resize', scheduleRealign)

    return () => {
      window.removeEventListener('resize', scheduleRealign)
      visualViewport?.removeEventListener('resize', scheduleRealign)
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [scrollerRef, activeSnapId, delayMs])
}
