import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HomeSection } from './HomeSection'

describe('HomeSection media background', () => {
  let idleCallback: IdleRequestCallback | undefined

  beforeEach(() => {
    idleCallback = undefined
    Object.defineProperty(window, 'requestIdleCallback', {
      configurable: true,
      value: (callback: IdleRequestCallback) => {
        idleCallback = callback
        return 41
      },
    })
    Object.defineProperty(window, 'cancelIdleCallback', {
      configurable: true,
      value: vi.fn(),
    })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: () => ({
        matches: false,
        media: '(prefers-reduced-motion: reduce)',
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }),
    })
  })

  it('keeps the UI interactive before activating the home video while idle', () => {
    const { container } = render(<HomeSection />)

    expect(container.querySelector('video')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '立即下载' })).toBeInTheDocument()

    act(() => {
      idleCallback?.({
        didTimeout: false,
        timeRemaining: () => 16,
      })
    })

    const video = container.querySelector('video')
    expect(video).toBeInTheDocument()
    expect(video).toHaveAttribute('preload', 'none')
    expect(video).toHaveAttribute('poster', '/images/global-background.png')
    expect(video).toHaveStyle({ opacity: '0', transition: 'opacity 900ms ease' })

    fireEvent.canPlay(video as HTMLVideoElement)
    expect(video).toHaveStyle({ opacity: '1' })

    const source = video?.querySelector('source')
    expect(source).toHaveAttribute('src', '/videos/pv.mp4')
    expect(source).toHaveAttribute('type', 'video/mp4')

    expect(screen.getByRole('button', { name: '立即下载' })).toBeInTheDocument()
  })

  it('does not activate the video when reduced motion is preferred', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: () => ({
        matches: true,
        media: '(prefers-reduced-motion: reduce)',
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }),
    })

    const { container } = render(<HomeSection />)

    expect(idleCallback).toBeUndefined()
    expect(container.querySelector('video')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '立即下载' })).toBeInTheDocument()
  })

  it('removes a failed deferred video without removing the UI', () => {
    const { container } = render(<HomeSection />)
    act(() => {
      idleCallback?.({
        didTimeout: false,
        timeRemaining: () => 16,
      })
    })

    const video = container.querySelector('video')
    expect(video).toBeInTheDocument()
    fireEvent.error(video as HTMLVideoElement)

    expect(container.querySelector('video')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '立即下载' })).toBeInTheDocument()
  })

  it('exposes responsive home layout hooks without changing media behavior', () => {
    const { container } = render(<HomeSection />)

    expect(container.querySelector('.home-section')).toBeInTheDocument()
    expect(container.querySelector('.home-section__content')).toBeInTheDocument()
    expect(container.querySelector('.home-section__title')).toBeInTheDocument()
    expect(container.querySelector('.home-section__cta')).toHaveTextContent('立即下载')
    expect(container.querySelector('.home-section__scroll-cue')).toBeInTheDocument()
  })
})
