import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  TransitionEvent as ReactTransitionEvent,
  WheelEvent as ReactWheelEvent,
} from 'react'
import { createPortal } from 'react-dom'
import { Maximize2, X } from 'lucide-react'
import './CircularGallery.css'
import { getMotionPolicy } from '../../../motion/motionPolicy'
import { recordMotionDiagnostic } from '../../../motion/motionDiagnostics'
import {
  applyEdgeResistance,
  calculateGallerySnapDuration,
  resolveGalleryTarget,
} from './circularGalleryMotion'

export interface CircularGalleryItem { id: string; image: string; title: string; alt: string }
export interface CircularGalleryProps { items: readonly CircularGalleryItem[]; bend: 0; borderRadius: 0.1 }

type GalleryPosition = 'before' | 'previous' | 'current' | 'next' | 'after'

function galleryPosition(index: number, currentIndex: number): GalleryPosition {
  if (index === currentIndex) return 'current'
  if (index === currentIndex - 1) return 'previous'
  if (index === currentIndex + 1) return 'next'
  return index < currentIndex ? 'before' : 'after'
}

interface DragSample {
  pointerId: number
  startX: number
  lastX: number
  lastTime: number
  velocityPxPerMs: number
  stepPx: number
}

interface SnapState {
  targetIndex: number
  durationMs: number
}

type GalleryViewportStyle = CSSProperties & {
  '--gallery-drag-offset': string
  '--gallery-snap-duration': string
}

function centerX(element: Element): number {
  const bounds = element.getBoundingClientRect()
  return bounds.left + bounds.width / 2
}

/**
 * DOM 轮播画廊。
 * 历史上的 WebGL(ogl) 实现有两个缺陷：
 * 1. 每张图被强制缩放到固定 1.08x1.48 的平面，无视原图宽高比，导致图片被压扁；
 * 2. 每次切换都重建 renderer / 重载纹理，快速点击时 canvas 反复销毁重建，导致闪烁和索引乱跳。
 * 现在使用稳定 DOM 节点组成前、中、后三个视觉槽位。切换时只更新槽位 class，
 * 图片节点不会卸载，CSS transform 负责连续过渡，object-fit: contain 保持原始比例。
 */
export function CircularGallery({ items, bend, borderRadius }: CircularGalleryProps) {
  const policy = getMotionPolicy()
  const status: 'ready' | 'fallback' = policy.enabled ? 'ready' : 'fallback'
  const [currentIndex, setCurrentIndex] = useState(0)
  const openerRef = useRef<HTMLButtonElement>(null)
  const viewportRef = useRef<HTMLDivElement>(null)
  const [viewerOpen, setViewerOpen] = useState(false)
  const wheelLockRef = useRef(0)
  const dragRef = useRef<DragSample | null>(null)
  const suppressClickRef = useRef(false)
  const [dragOffset, setDragOffset] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const [snap, setSnap] = useState<SnapState | null>(null)

  const count = items.length
  const safeIndex = count > 0 ? Math.min(currentIndex, count - 1) : 0

  const moveTo = useCallback((index: number) => {
    if (count === 0) return
    dragRef.current = null
    setIsDragging(false)
    setSnap(null)
    setDragOffset(0)
    setCurrentIndex(Math.min(count - 1, Math.max(0, index)))
  }, [count])

  useEffect(() => {
    recordMotionDiagnostic({ component: 'CircularGallery', event: status === 'ready' ? 'initialized' : 'fallback', reason: policy.reason })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!viewerOpen) return
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setViewerOpen(false)
    }
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('keydown', close)
      openerRef.current?.focus()
    }
  }, [viewerOpen])

  // Shift + wheel 遵循桌面横向滚动习惯；原生 deltaX 支持触控板横滑。
  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (event.ctrlKey) return
    const horizontalDelta = Math.abs(event.deltaX) > Math.abs(event.deltaY)
      ? event.deltaX
      : event.shiftKey
        ? event.deltaY
        : 0
    if (horizontalDelta === 0) return
    event.preventDefault()
    const now = performance.now()
    if (now - wheelLockRef.current < 260) return
    wheelLockRef.current = now
    moveTo(safeIndex + (horizontalDelta > 0 ? 1 : -1))
  }

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    moveTo(safeIndex + (event.key === 'ArrowRight' ? 1 : -1))
  }

  const measureStep = () => {
    const viewport = viewportRef.current
    if (!viewport) return 1
    const current = viewport.querySelector('[data-gallery-position="current"]')
    const adjacent = viewport.querySelector('[data-gallery-position="next"]')
      || viewport.querySelector('[data-gallery-position="previous"]')
    if (!current || !adjacent) return Math.max(1, viewport.clientWidth)
    return Math.max(1, Math.abs(centerX(adjacent) - centerX(current)))
  }

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (count === 0 || snap || event.button > 0) return
    const now = performance.now()
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      lastX: event.clientX,
      lastTime: now,
      velocityPxPerMs: 0,
      stepPx: measureStep(),
    }
    suppressClickRef.current = false
    setDragOffset(0)
    setIsDragging(true)
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const sample = dragRef.current
    if (!sample || sample.pointerId !== event.pointerId) return
    const now = performance.now()
    const elapsed = Math.max(1, now - sample.lastTime)
    sample.velocityPxPerMs = (event.clientX - sample.lastX) / elapsed
    sample.lastX = event.clientX
    sample.lastTime = now
    const rawOffset = event.clientX - sample.startX
    suppressClickRef.current = Math.abs(rawOffset) > 5
    setDragOffset(applyEdgeResistance(rawOffset, safeIndex, count))
    if (event.cancelable) event.preventDefault()
  }

  const finishPointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    const sample = dragRef.current
    if (!sample || sample.pointerId !== event.pointerId) return
    const rawOffset = event.clientX - sample.startX
    const releaseOffset = applyEdgeResistance(rawOffset, safeIndex, count)
    const targetIndex = resolveGalleryTarget({
      currentIndex: safeIndex,
      itemCount: count,
      offsetPx: releaseOffset,
      stepPx: sample.stepPx,
      velocityPxPerMs: sample.velocityPxPerMs,
    })
    const targetOffset = targetIndex > safeIndex
      ? -sample.stepPx
      : targetIndex < safeIndex
        ? sample.stepPx
        : 0
    const reducedMotion = policy.reason === 'reduced-motion'
    const durationMs = calculateGallerySnapDuration(targetOffset - releaseOffset, reducedMotion)
    dragRef.current = null
    setIsDragging(false)
    event.currentTarget.releasePointerCapture?.(event.pointerId)

    if (reducedMotion) {
      setCurrentIndex(targetIndex)
      setSnap(null)
      setDragOffset(0)
      return
    }

    setSnap({ targetIndex, durationMs })
    setDragOffset(targetOffset)
  }

  const handlePointerCancel = (event: ReactPointerEvent<HTMLDivElement>) => {
    const sample = dragRef.current
    if (!sample || sample.pointerId !== event.pointerId) return
    dragRef.current = null
    suppressClickRef.current = false
    setIsDragging(false)
    setSnap(null)
    setDragOffset(0)
    event.currentTarget.releasePointerCapture?.(event.pointerId)
  }

  const handleSnapEnd = (event: ReactTransitionEvent<HTMLButtonElement>, position: GalleryPosition) => {
    if (!snap || position !== 'current' || (event.propertyName && event.propertyName !== 'transform')) return
    setCurrentIndex(snap.targetIndex)
    setSnap(null)
    setDragOffset(0)
  }

  const viewportStyle: GalleryViewportStyle = {
    '--gallery-drag-offset': `${dragOffset}px`,
    '--gallery-snap-duration': `${policy.reason === 'reduced-motion' ? 0 : snap?.durationMs ?? 480}ms`,
  }

  return (
    <div
      className="circular-gallery"
      data-gallery-status={status}
      data-gallery-dragging={String(isDragging)}
      data-gallery-snapping={String(Boolean(snap))}
      data-bend={bend}
      data-border-radius={borderRadius}
    >
      <div
        ref={viewportRef}
        className="circular-gallery__viewport"
        style={viewportStyle}
        tabIndex={0}
        onWheel={handleWheel}
        onKeyDown={handleKeyDown}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishPointer}
        onPointerCancel={handlePointerCancel}
      >
        {items.map((item, index) => {
          const position = galleryPosition(index, safeIndex)
          const visible = position === 'previous' || position === 'current' || position === 'next'
          return (
            <button
              key={item.id}
              type="button"
              data-animation-slot="image-card"
              data-gallery-position={position}
              className={`circular-gallery__slide circular-gallery__slide--${position}`}
              aria-label={`Select image ${item.alt}`}
              aria-current={position === 'current' ? 'true' : undefined}
              aria-hidden={!visible || undefined}
              tabIndex={visible ? 0 : -1}
              onClick={() => {
                if (suppressClickRef.current) {
                  suppressClickRef.current = false
                  return
                }
                moveTo(index)
              }}
              onTransitionEnd={(event) => handleSnapEnd(event, position)}
            >
              <img src={item.image} alt={item.alt} loading="lazy" draggable={false} />
            </button>
          )
        })}
        <button
          type="button"
          className="circular-gallery__previous"
          disabled={safeIndex === 0}
          onClick={() => moveTo(safeIndex - 1)}
          aria-label="上一张图片"
        >
          ‹
        </button>
        <button
          type="button"
          className="circular-gallery__next"
          disabled={safeIndex >= count - 1}
          onClick={() => moveTo(safeIndex + 1)}
          aria-label="下一张图片"
        >
          ›
        </button>
      </div>
      <div className="circular-gallery__caption" aria-label="图片画廊控制">
        <span className="circular-gallery__title" aria-live="polite">{items[safeIndex]?.title || ''}</span>
        <span className="circular-gallery__counter">{safeIndex + 1}/{items.length}</span>
        <button className="circular-gallery__open" ref={openerRef} type="button" disabled={!items[safeIndex]} onClick={() => setViewerOpen(true)} aria-label="Open current image"><Maximize2 aria-hidden="true" /></button>
      </div>
      {viewerOpen && items[safeIndex] && createPortal(
        <div className="circular-gallery__lightbox" role="dialog" aria-modal="true" aria-label={items[safeIndex].title} onMouseDown={(event) => event.target === event.currentTarget && setViewerOpen(false)}>
          <button className="circular-gallery__lightbox-close" type="button" onClick={() => setViewerOpen(false)} aria-label="Close image viewer"><X aria-hidden="true" /></button>
          <img src={items[safeIndex].image} alt={items[safeIndex].alt} />
        </div>,
        document.body,
      )}
    </div>
  )
}
