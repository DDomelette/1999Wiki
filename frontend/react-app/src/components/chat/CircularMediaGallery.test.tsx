import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AssetItem } from '../../types'
import { CircularMediaGallery } from './CircularMediaGallery'

const images: AssetItem[] = [
  { asset_id: 'one', role: 'image', alt: '图片一', url: 'https://example.test/one.webp' },
  { asset_id: 'two', role: 'image', alt: '图片二', url: 'https://example.test/two.webp' },
]

describe('CircularMediaGallery', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    })
  })

  it('retains the Circular Gallery shell and all DOM images in capability fallback', async () => {
    const { container } = render(<CircularMediaGallery items={images} />)
    const gallery = container.querySelector('.circular-gallery')

    expect(gallery).toBeInTheDocument()
    await waitFor(() => expect(gallery).toHaveAttribute('data-gallery-status', 'fallback'))
    expect(screen.getByRole('img', { name: '图片一' })).toHaveAttribute('src', images[0].url)
    expect(screen.getByRole('img', { name: '图片二' })).toHaveAttribute('src', images[1].url)
  })

  it('keeps the full-size viewer available in fallback mode', async () => {
    render(<CircularMediaGallery items={images} />)
    await waitFor(() => expect(document.querySelector('.circular-gallery')).toHaveAttribute('data-gallery-status', 'fallback'))

    fireEvent.click(screen.getByRole('button', { name: 'Open current image' }))
    const dialog = screen.getByRole('dialog', { name: '图片一' })
    expect(dialog.parentElement).toBe(document.body)
    expect(within(dialog).getByRole('img', { name: '图片一' })).toHaveAttribute('src', images[0].url)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close image viewer' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
