import { useCallback, useEffect, useRef, useState } from 'react'
import type { WheelEvent as ReactWheelEvent } from 'react'
import { Maximize2, X } from 'lucide-react'
import './CircularGallery.css'
import { getMotionPolicy } from '../../../motion/motionPolicy'
import { recordMotionDiagnostic } from '../../../motion/motionDiagnostics'

export interface CircularGalleryItem { id: string; image: string; title: string; alt: string }
export interface CircularGalleryProps { items: readonly CircularGalleryItem[]; bend: 0; borderRadius: 0.1 }

type GalleryPosition = 'before' | 'previous' | 'current' | 'next' | 'after'

function galleryPosition(index: number, currentIndex: number): GalleryPosition {
  if (index === currentIndex) return 'current'
  if (index === currentIndex - 1) return 'previous'
  if (index === currentIndex + 1) return 'next'
  return index < currentIndex ? 'before' : 'after'
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
  const [viewerOpen, setViewerOpen] = useState(false)
  const wheelLockRef = useRef(0)

  const count = items.length
  const safeIndex = count > 0 ? Math.min(currentIndex, count - 1) : 0

  const moveTo = useCallback((index: number) => {
    if (count === 0) return
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

  // 仅在明确横向滚动意图时切换图片，避免聊天区纵向滚动误触；节流防止一次滚动连跳
  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return
    const now = performance.now()
    if (now - wheelLockRef.current < 260) return
    wheelLockRef.current = now
    moveTo(safeIndex + (event.deltaX > 0 ? 1 : -1))
  }

  return (
    <div className="circular-gallery" data-gallery-status={status} data-bend={bend} data-border-radius={borderRadius}>
      <div className="circular-gallery__viewport" onWheel={handleWheel}>
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
              onClick={() => moveTo(index)}
            >
              <img src={item.image} alt={item.alt} loading="lazy" draggable={false} />
            </button>
          )
        })}
      </div>
      <div className="circular-gallery__controls" aria-label="图片画廊控制">
        <button type="button" disabled={safeIndex === 0} onClick={() => moveTo(safeIndex - 1)} aria-label="上一张图片">‹</button>
        <span aria-live="polite">{items[safeIndex]?.title || ''} · {safeIndex + 1}/{items.length}</span>
        <button type="button" disabled={safeIndex >= count - 1} onClick={() => moveTo(safeIndex + 1)} aria-label="下一张图片">›</button>
        <button ref={openerRef} type="button" disabled={!items[safeIndex]} onClick={() => setViewerOpen(true)} aria-label="Open current image"><Maximize2 aria-hidden="true" /></button>
      </div>
      {viewerOpen && items[safeIndex] && <div className="circular-gallery__lightbox" role="dialog" aria-modal="true" aria-label={items[safeIndex].title} onMouseDown={(event) => event.target === event.currentTarget && setViewerOpen(false)}><button type="button" onClick={() => setViewerOpen(false)} aria-label="Close image viewer"><X aria-hidden="true" /></button><img src={items[safeIndex].image} alt={items[safeIndex].alt} /></div>}
    </div>
  )
}
