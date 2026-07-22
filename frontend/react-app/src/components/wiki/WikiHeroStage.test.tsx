import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { WikiMediaViewModel } from './wikiViewModel'
import { WikiHeroStage } from './WikiHeroStage'

function media(id: string, title: string): WikiMediaViewModel {
  return {
    id,
    title,
    url: `https://example.test/${id}.webp`,
    kind: 'image',
    variant: 'unspecified',
    priority: 0,
  }
}

describe('WikiHeroStage', () => {
  it('falls forward to the next candidate when the active image fails', () => {
    const onActiveIndexChange = vi.fn()
    render(
      <WikiHeroStage
        title="档案标题"
        candidates={[media('first', '第一张'), media('second', '第二张')]}
        emptyLabel="暂无媒体"
        onActiveIndexChange={onActiveIndexChange}
      />,
    )

    expect(screen.getByTestId('tilted-image-card')).toBeInTheDocument()
    fireEvent.error(screen.getByRole('img', { name: '第一张' }))
    expect(screen.getByRole('img', { name: '第二张' })).toBeInTheDocument()
    expect(onActiveIndexChange).toHaveBeenLastCalledWith(1)
  })

  it('keeps the stage title and surrounding content when every image fails', () => {
    render(
      <article>
        <WikiHeroStage title="档案标题" candidates={[media('only', '唯一图片')]} emptyLabel="暂无媒体" />
        <p>后续正文</p>
      </article>,
    )

    fireEvent.error(screen.getByRole('img', { name: '唯一图片' }))
    expect(screen.getByText('暂无媒体')).toBeInTheDocument()
    expect(screen.getByText('档案标题')).toBeInTheDocument()
    expect(screen.getByText('后续正文')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-hero-stage')).toHaveStyle({ border: 'none', background: 'transparent' })
  })

  it('honors an externally selected candidate without replacing the media interaction', () => {
    render(
      <WikiHeroStage
        title="档案标题"
        candidates={[media('first', '第一张'), media('second', '第二张')]}
        emptyLabel="暂无媒体"
        activeIndex={1}
      />,
    )

    expect(screen.getByRole('img', { name: '第二张' })).toBeInTheDocument()
    expect(screen.getByTestId('tilted-image-card')).toBeInTheDocument()
  })
})
