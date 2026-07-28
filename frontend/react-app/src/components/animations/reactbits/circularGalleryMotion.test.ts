import { describe, expect, it } from 'vitest'
import {
  applyEdgeResistance,
  calculateGallerySnapDuration,
  resolveGalleryTarget,
} from './circularGalleryMotion'

describe('resolveGalleryTarget', () => {
  it.each([
    [{ currentIndex: 2, itemCount: 5, offsetPx: -130, stepPx: 400, velocityPxPerMs: -0.1 }, 3],
    [{ currentIndex: 2, itemCount: 5, offsetPx: 130, stepPx: 400, velocityPxPerMs: 0.1 }, 1],
    [{ currentIndex: 2, itemCount: 5, offsetPx: -40, stepPx: 400, velocityPxPerMs: -0.6 }, 3],
    [{ currentIndex: 2, itemCount: 5, offsetPx: 40, stepPx: 400, velocityPxPerMs: 0.6 }, 1],
    [{ currentIndex: 2, itemCount: 5, offsetPx: -40, stepPx: 400, velocityPxPerMs: -0.1 }, 2],
    [{ currentIndex: 0, itemCount: 5, offsetPx: 180, stepPx: 400, velocityPxPerMs: 0.8 }, 0],
    [{ currentIndex: 4, itemCount: 5, offsetPx: -180, stepPx: 400, velocityPxPerMs: -0.8 }, 4],
    [{ currentIndex: 0, itemCount: 0, offsetPx: -180, stepPx: 400, velocityPxPerMs: -0.8 }, 0],
  ])('selects the bounded target for %#', (input, expected) => {
    expect(resolveGalleryTarget(input)).toBe(expected)
  })
})

describe('applyEdgeResistance', () => {
  it('damps outward movement at each boundary without damping inward movement', () => {
    expect(applyEdgeResistance(120, 0, 4)).toBe(42)
    expect(applyEdgeResistance(-120, 0, 4)).toBe(-120)
    expect(applyEdgeResistance(-120, 3, 4)).toBe(-42)
    expect(applyEdgeResistance(120, 3, 4)).toBe(120)
  })
})

describe('calculateGallerySnapDuration', () => {
  it('clamps distance-derived duration and disables it for reduced motion', () => {
    expect(calculateGallerySnapDuration(30, false)).toBe(180)
    expect(calculateGallerySnapDuration(360, false)).toBe(240)
    expect(calculateGallerySnapDuration(900, false)).toBe(420)
    expect(calculateGallerySnapDuration(360, true)).toBe(0)
  })
})
