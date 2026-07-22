import { useRef, useState } from 'react'
import { StreamingDescription } from './StreamingDescription'
import { AutoHideScrollbar } from './ui/AutoHideScrollbar'

export function ScrollableDescription({ text, start }: { text: string; start: boolean }) {
  const [scrollbarVisible, setScrollbarVisible] = useState(false)
  const hideTimerRef = useRef<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const revealScrollbar = () => {
    setScrollbarVisible(true)
    if (hideTimerRef.current !== null) window.clearTimeout(hideTimerRef.current)
    hideTimerRef.current = window.setTimeout(() => {
      setScrollbarVisible(false)
      hideTimerRef.current = null
    }, 800)
  }

  return (
    <div className="scrollable-description-shell" style={{ marginTop: 28 }}>
      <div
        ref={scrollRef}
        data-page-wheel-lock="true"
        data-scrollbar-visible={scrollbarVisible ? 'true' : 'false'}
        data-testid="scrollable-description"
        onScroll={revealScrollbar}
        onWheel={revealScrollbar}
        style={{
          maxHeight: 'clamp(320px, 50vh, 580px)',
          overflowY: 'auto',
          overscrollBehavior: 'contain',
          paddingRight: 14,
        }}
        className="description-scrollbox native-scrollbar-hidden"
      >
        <StreamingDescription text={text} start={start} />
      </div>
      <AutoHideScrollbar
        targetRef={scrollRef}
        testId="scrollable-description-scrollbar"
        variant="local"
      />
    </div>
  )
}
