export interface GalleryReleaseInput {
  currentIndex: number
  itemCount: number
  offsetPx: number
  stepPx: number
  velocityPxPerMs: number
}

const DISTANCE_RATIO = 0.25
const FLICK_VELOCITY = 0.45
const EDGE_RESISTANCE = 0.35

export function resolveGalleryTarget({
  currentIndex,
  itemCount,
  offsetPx,
  stepPx,
  velocityPxPerMs,
}: GalleryReleaseInput): number {
  if (itemCount <= 0) return 0
  const distanceIntent = Math.abs(offsetPx) >= Math.max(1, stepPx) * DISTANCE_RATIO
  const velocityIntent = Math.abs(velocityPxPerMs) >= FLICK_VELOCITY
  const movesNext = offsetPx < 0 || velocityPxPerMs < -FLICK_VELOCITY
  const direction = distanceIntent || velocityIntent ? (movesNext ? 1 : -1) : 0
  return Math.min(itemCount - 1, Math.max(0, currentIndex + direction))
}

export function applyEdgeResistance(offsetPx: number, currentIndex: number, itemCount: number): number {
  const beyondStart = currentIndex <= 0 && offsetPx > 0
  const beyondEnd = currentIndex >= itemCount - 1 && offsetPx < 0
  return beyondStart || beyondEnd ? offsetPx * EDGE_RESISTANCE : offsetPx
}

export function calculateGallerySnapDuration(distancePx: number, reducedMotion: boolean): number {
  if (reducedMotion) return 0
  return Math.min(420, Math.max(180, Math.round(Math.abs(distancePx) / 1.5)))
}
