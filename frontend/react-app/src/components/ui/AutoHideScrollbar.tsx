import { type RefObject, useEffect, useRef, useState } from 'react'

type AutoHideScrollbarVariant = 'fixed' | 'local'

type AutoHideScrollbarProps = {
  targetRef: RefObject<HTMLElement>
  testId: string
  variant?: AutoHideScrollbarVariant
  hideDelay?: number
}

const MIN_THUMB_HEIGHT = 34

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

export function AutoHideScrollbar({
  targetRef,
  testId,
  variant = 'fixed',
  hideDelay = 800,
}: AutoHideScrollbarProps) {
  const [visible, setVisible] = useState(false)
  const [thumbHeight, setThumbHeight] = useState(MIN_THUMB_HEIGHT)
  const [thumbTop, setThumbTop] = useState(0)
  const hideTimerRef = useRef<number | null>(null)

  useEffect(() => {
    const target = targetRef.current
    if (!target) return

    const edgeOffset = variant === 'fixed' ? 24 : 12

    const updateMetrics = () => {
      const viewportHeight = target.clientHeight || window.innerHeight || 1
      const scrollHeight = Math.max(target.scrollHeight || viewportHeight, viewportHeight)
      const trackHeight = Math.max(1, viewportHeight - edgeOffset)
      const maxScrollTop = Math.max(scrollHeight - viewportHeight, 0)
      const nextThumbHeight =
        maxScrollTop > 0
          ? clamp(trackHeight * (viewportHeight / scrollHeight), MIN_THUMB_HEIGHT, trackHeight)
          : trackHeight
      const nextThumbTop =
        maxScrollTop > 0
          ? (target.scrollTop / maxScrollTop) * (trackHeight - nextThumbHeight)
          : 0

      setThumbHeight(nextThumbHeight)
      setThumbTop(nextThumbTop)
    }

    const reveal = () => {
      updateMetrics()
      setVisible(true)

      if (hideTimerRef.current !== null) window.clearTimeout(hideTimerRef.current)
      hideTimerRef.current = window.setTimeout(() => {
        setVisible(false)
        hideTimerRef.current = null
      }, hideDelay)
    }

    updateMetrics()
    target.addEventListener('scroll', reveal, { passive: true })
    target.addEventListener('wheel', reveal, { passive: true })
    window.addEventListener('resize', updateMetrics)

    return () => {
      target.removeEventListener('scroll', reveal)
      target.removeEventListener('wheel', reveal)
      window.removeEventListener('resize', updateMetrics)
      if (hideTimerRef.current !== null) window.clearTimeout(hideTimerRef.current)
    }
  }, [hideDelay, targetRef, variant])

  return (
    <div
      aria-hidden="true"
      className={`overlay-scrollbar overlay-scrollbar--${variant}`}
      data-scrollbar-visible={visible ? 'true' : 'false'}
      data-testid={testId}
    >
      <div
        className="overlay-scrollbar__thumb"
        style={{
          height: thumbHeight,
          transform: `translateY(${thumbTop}px)`,
        }}
      />
    </div>
  )
}
