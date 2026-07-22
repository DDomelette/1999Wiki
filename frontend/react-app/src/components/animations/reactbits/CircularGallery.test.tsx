import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CircularGallery } from './CircularGallery'

const items = Array.from({ length: 12 }, (_, index) => ({ id: String(index), image: `/image-${index}.webp`, title: `Image ${index}`, alt: `Alt ${index}` }))

describe('CircularGallery P1 behavior', () => {
  it('keeps stable image nodes and exposes bounded previous, current, and next slots', () => {
    render(<CircularGallery items={items.slice(0, 4)} bend={0} borderRadius={0.1} />)

    const firstImage = screen.getByRole('img', { name: 'Alt 0' })
    expect(firstImage.closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
    expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'next')
    expect(screen.queryByRole('button', { name: 'Select previous image Alt 0' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '上一张图片' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: '下一张图片' }))

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
    expect(within(dialog).getByRole('img', { name: 'Alt 0' })).toHaveAttribute('src', '/image-0.webp')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })
})
