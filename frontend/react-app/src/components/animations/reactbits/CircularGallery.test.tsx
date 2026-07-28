import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CircularGallery } from './CircularGallery'

const items = Array.from({ length: 12 }, (_, index) => ({ id: String(index), image: `/image-${index}.webp`, title: `Image ${index}`, alt: `Alt ${index}` }))

function box(left: number, width = 200): DOMRect {
  return {
    x: left,
    y: 0,
    top: 0,
    right: left + width,
    bottom: 300,
    left,
    width,
    height: 300,
    toJSON: () => ({}),
  }
}

function stubSlotGeometry() {
  vi.spyOn(screen.getByRole('img', { name: 'Alt 0' }).parentElement!, 'getBoundingClientRect').mockReturnValue(box(100))
  vi.spyOn(screen.getByRole('img', { name: 'Alt 1' }).parentElement!, 'getBoundingClientRect').mockReturnValue(box(500))
}

describe('CircularGallery P1 behavior', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'PointerEvent', { configurable: true, value: MouseEvent })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('keeps stable image nodes and exposes bounded previous, current, and next slots', () => {
    render(<CircularGallery items={items.slice(0, 4)} bend={0} borderRadius={0.1} />)

    const firstImage = screen.getByRole('img', { name: 'Alt 0' })
    const previous = screen.getByRole('button', { name: '上一张图片' })
    const next = screen.getByRole('button', { name: '下一张图片' })
    expect(firstImage.closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
    expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'next')
    expect(screen.queryByRole('button', { name: 'Select previous image Alt 0' })).not.toBeInTheDocument()
    expect(previous).toHaveClass('circular-gallery__previous')
    expect(next).toHaveClass('circular-gallery__next')
    expect(previous.parentElement).toHaveClass('circular-gallery__viewport')
    expect(next.parentElement).toHaveClass('circular-gallery__viewport')
    expect(screen.getByText('Image 0')).toHaveClass('circular-gallery__title')
    expect(previous).toBeDisabled()

    fireEvent.click(next)

    expect(screen.getByRole('img', { name: 'Alt 0' })).toBe(firstImage)
    expect(firstImage.closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'previous')
    expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
    expect(screen.getByRole('img', { name: 'Alt 2' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'next')
  })

  it('opens the current source image and closes with Escape', () => {
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: vi.fn().mockReturnValue({ matches: true }) })
    render(<CircularGallery items={items.slice(0, 2)} bend={0} borderRadius={0.1} />)
    const opener = screen.getByRole('button', { name: 'Open current image' })
    fireEvent.click(opener)
    const dialog = screen.getByRole('dialog', { name: 'Image 0' })
    expect(dialog.parentElement).toBe(document.body)
    expect(dialog).toContainElement(within(dialog).getByRole('button', { name: 'Close image viewer' }))
    expect(within(dialog).getByRole('img', { name: 'Alt 0' })).toHaveAttribute('src', '/image-0.webp')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })

  it('uses Shift-wheel and horizontal touchpad intent without consuming zoom or vertical scroll', () => {
    vi.spyOn(performance, 'now').mockReturnValue(1_000)
    const { container } = render(<CircularGallery items={items.slice(0, 4)} bend={0} borderRadius={0.1} />)
    const viewport = container.querySelector('.circular-gallery__viewport')!

    fireEvent.wheel(viewport, { shiftKey: true, deltaY: 120 })
    expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')

    const ctrlWheel = new WheelEvent('wheel', { bubbles: true, cancelable: true, ctrlKey: true, deltaY: 120 })
    expect(viewport.dispatchEvent(ctrlWheel)).toBe(true)
    expect(ctrlWheel.defaultPrevented).toBe(false)

    const verticalWheel = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 120 })
    expect(viewport.dispatchEvent(verticalWheel)).toBe(true)
    expect(verticalWheel.defaultPrevented).toBe(false)

    fireEvent.keyDown(viewport, { key: 'ArrowRight' })
    expect(screen.getByRole('img', { name: 'Alt 2' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
    fireEvent.keyDown(viewport, { key: 'ArrowLeft' })
    expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
  })

  it('uses native horizontal wheel intent to select the next image', () => {
    vi.spyOn(performance, 'now').mockReturnValue(1_000)
    const { container } = render(<CircularGallery items={items.slice(0, 3)} bend={0} borderRadius={0.1} />)
    fireEvent.wheel(container.querySelector('.circular-gallery__viewport')!, { deltaX: 120, deltaY: 4 })
    expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
  })

  it('drags with the pointer and commits the measured next slot after linear snapping', () => {
    vi.spyOn(performance, 'now')
      .mockReturnValueOnce(1_000)
      .mockReturnValueOnce(1_200)
      .mockReturnValueOnce(1_400)
    const { container } = render(<CircularGallery items={items.slice(0, 3)} bend={0} borderRadius={0.1} />)
    const gallery = container.querySelector('.circular-gallery')!
    const viewport = container.querySelector('.circular-gallery__viewport')!
    stubSlotGeometry()

    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 300 })
    fireEvent.pointerMove(viewport, { pointerId: 1, clientX: 160 })

    expect(gallery).toHaveAttribute('data-gallery-dragging', 'true')
    expect(viewport).toHaveStyle('--gallery-drag-offset: -140px')

    const firstSlide = screen.getByRole('img', { name: 'Alt 0' }).parentElement!
    fireEvent.pointerUp(viewport, { pointerId: 1, clientX: 160 })
    expect(gallery).toHaveAttribute('data-gallery-snapping', 'true')
    fireEvent.transitionEnd(firstSlide, { propertyName: 'transform' })

    expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
    expect(viewport).toHaveStyle('--gallery-drag-offset: 0px')
  })

  it('returns a small slow drag to the current image', () => {
    vi.spyOn(performance, 'now')
      .mockReturnValueOnce(1_000)
      .mockReturnValueOnce(2_000)
      .mockReturnValueOnce(3_000)
    const { container } = render(<CircularGallery items={items.slice(0, 3)} bend={0} borderRadius={0.1} />)
    const viewport = container.querySelector('.circular-gallery__viewport')!
    stubSlotGeometry()

    fireEvent.pointerDown(viewport, { pointerId: 2, clientX: 300 })
    fireEvent.pointerUp(viewport, { pointerId: 2, clientX: 260 })
    fireEvent.transitionEnd(screen.getByRole('img', { name: 'Alt 0' }).parentElement!, { propertyName: 'transform' })

    expect(screen.getByRole('img', { name: 'Alt 0' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
    expect(viewport).toHaveStyle('--gallery-drag-offset: 0px')
  })

  it('resists an outward drag at the first image and cancels without changing index', () => {
    vi.spyOn(performance, 'now')
      .mockReturnValueOnce(1_000)
      .mockReturnValueOnce(1_200)
    const { container } = render(<CircularGallery items={items.slice(0, 3)} bend={0} borderRadius={0.1} />)
    const viewport = container.querySelector('.circular-gallery__viewport')!
    stubSlotGeometry()

    fireEvent.pointerDown(viewport, { pointerId: 3, clientX: 300 })
    fireEvent.pointerMove(viewport, { pointerId: 3, clientX: 420 })
    expect(viewport).toHaveStyle('--gallery-drag-offset: 42px')
    fireEvent.pointerCancel(viewport, { pointerId: 3 })

    expect(screen.getByRole('img', { name: 'Alt 0' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
    expect(viewport).toHaveStyle('--gallery-drag-offset: 0px')
  })

  it('commits a drag immediately when reduced motion is requested', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    })
    vi.spyOn(performance, 'now')
      .mockReturnValueOnce(1_000)
      .mockReturnValueOnce(1_200)
      .mockReturnValueOnce(1_400)
    const { container } = render(<CircularGallery items={items.slice(0, 3)} bend={0} borderRadius={0.1} />)
    const gallery = container.querySelector('.circular-gallery')!
    const viewport = container.querySelector('.circular-gallery__viewport')!
    stubSlotGeometry()

    fireEvent.pointerDown(viewport, { pointerId: 4, clientX: 300 })
    fireEvent.pointerMove(viewport, { pointerId: 4, clientX: 160 })
    fireEvent.pointerUp(viewport, { pointerId: 4, clientX: 160 })

    expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
    expect(gallery).toHaveAttribute('data-gallery-snapping', 'false')
    expect(viewport).toHaveStyle('--gallery-snap-duration: 0ms')
  })
})
