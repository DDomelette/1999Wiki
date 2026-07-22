import { useEffect, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { motion } from 'framer-motion'
import './AnimatedList.css'

export interface AnimatedListProps<T> {
  items: readonly T[]
  itemKey: (item: T) => string
  renderItem: (item: T, index: number) => ReactNode
  selectedKey?: string | null
  onItemSelect?: (item: T, index: number) => void
  displayScrollbar?: boolean
  replayOnEnter?: boolean
  ariaLabel: string
  className?: string
}

export function AnimatedList<T>({
  items,
  itemKey,
  renderItem,
  selectedKey,
  onItemSelect,
  displayScrollbar = false,
  replayOnEnter = false,
  ariaLabel,
  className = '',
}: AnimatedListProps<T>) {
  const reducedMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const selectedIndex = Math.max(0, items.findIndex((item) => itemKey(item) === selectedKey))
  const [focusedIndex, setFocusedIndex] = useState(selectedIndex)
  const [edgeState, setEdgeState] = useState({ start: true, end: items.length <= 1 })

  useEffect(() => {
    setFocusedIndex(Math.min(selectedIndex, Math.max(0, items.length - 1)))
  }, [items.length, selectedIndex])

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!items.length) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const direction = event.key === 'ArrowDown' ? 1 : -1
      setFocusedIndex((current) => (current + direction + items.length) % items.length)
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onItemSelect?.(items[focusedIndex], focusedIndex)
    }
  }

  const syncEdges = (element: HTMLDivElement) => {
    setEdgeState({ start: element.scrollTop <= 1, end: element.scrollTop + element.clientHeight >= element.scrollHeight - 1 })
  }

  return (
    <div
      role="listbox"
      aria-label={ariaLabel}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onScroll={(event) => syncEdges(event.currentTarget)}
      data-scroll-start={edgeState.start}
      data-scroll-end={edgeState.end}
      data-replay-on-enter={replayOnEnter || undefined}
      className={`reactbits-animated-list ${displayScrollbar ? '' : 'reactbits-scrollbar-hidden'} ${className}`.trim()}
    >
      {items.map((item, index) => {
          const key = itemKey(item)
          const active = index === focusedIndex
          const replayViewportAnimation = replayOnEnter
            && !reducedMotion
            && typeof IntersectionObserver !== 'undefined'
          return (
            <motion.div
              role="option"
              aria-selected={selectedKey ? key === selectedKey : active}
              key={key}
              layout={!reducedMotion}
              initial={reducedMotion ? false : { opacity: 0, y: 12 }}
              animate={replayViewportAnimation
                ? { scale: active ? 1.01 : 1 }
                : { opacity: 1, y: 0, scale: active && !reducedMotion ? 1.01 : 1 }}
              whileInView={replayViewportAnimation ? { opacity: 1, y: 0 } : undefined}
              viewport={replayViewportAnimation ? { once: false, amount: 0.18 } : undefined}
              exit={reducedMotion ? undefined : { opacity: 0, y: -8 }}
              transition={{ duration: reducedMotion ? 0 : 0.24 }}
              className="reactbits-animated-list__item"
              data-active={active || undefined}
              onMouseEnter={() => setFocusedIndex(index)}
              onClick={() => onItemSelect?.(item, index)}
            >
              {renderItem(item, index)}
            </motion.div>
          )
        })}
    </div>
  )
}
