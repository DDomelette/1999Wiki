import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HomeSection } from './HomeSection'

describe('HomeSection media background', () => {
  it('renders the home video with the global image as poster fallback', () => {
    const { container } = render(<HomeSection />)

    const video = container.querySelector('video')
    expect(video).toBeInTheDocument()
    expect(video).toHaveAttribute('poster', '/images/global-background.png')
    expect(video).toHaveStyle({ opacity: '0', transition: 'opacity 900ms ease' })

    fireEvent.canPlay(video as HTMLVideoElement)
    expect(video).toHaveStyle({ opacity: '1' })

    const source = video?.querySelector('source')
    expect(source).toHaveAttribute('src', '/videos/pv.mp4')
    expect(source).toHaveAttribute('type', 'video/mp4')

    expect(screen.getByRole('button', { name: '立即下载' })).toBeInTheDocument()
  })
})
