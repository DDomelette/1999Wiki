import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { WikiMediaViewModel, WikiPortraitSlots } from '../wikiViewModel'
import { CharacterMediaStage } from './CharacterMediaStage'

function portrait(id: string, title: string, variant: WikiMediaViewModel['variant']): WikiMediaViewModel {
  return {
    id,
    title,
    url: `https://example.test/${id}.webp`,
    kind: 'portrait',
    variant,
    priority: 0,
  }
}

const initial = portrait('initial', '初始立绘图片', 'initial')
const insight = portrait('insight', '洞悉立绘图片', 'insight')
const explicitSlots: WikiPortraitSlots = { initial, insight, extras: [] }

describe('CharacterMediaStage', () => {
  it('switches explicit initial and insight portraits in one stable stage', () => {
    render(
      <CharacterMediaStage
        title="槲寄生"
        portraitSlots={explicitSlots}
        portraits={[initial, insight]}
        voices={[]}
      />,
    )

    expect(screen.getByRole('button', { name: '初始' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('img', { name: '初始立绘图片' })).toBeInTheDocument()
    expect(screen.getByTestId('tilted-image-card')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '洞悉' }))
    expect(screen.getByRole('button', { name: '洞悉' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('img', { name: '洞悉立绘图片' })).toBeInTheDocument()
    expect(screen.getByTestId('character-media-stage')).toBeInTheDocument()
  })

  it('uses neutral ordered labels when portrait semantics are unknown', () => {
    const first = portrait('unknown-a', '未知立绘 A', 'unspecified')
    const second = portrait('unknown-b', '未知立绘 B', 'unspecified')
    render(
      <CharacterMediaStage
        title="角色"
        portraitSlots={{ initial: null, insight: null, extras: [first, second] }}
        portraits={[first, second]}
        voices={[]}
      />,
    )

    expect(screen.getByRole('button', { name: '立绘 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '立绘 2' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '初始' })).not.toBeInTheDocument()
  })

  it('keeps the current static portrait when Live2D is not ready', () => {
    render(
      <CharacterMediaStage
        title="槲寄生"
        portraitSlots={explicitSlots}
        portraits={[initial, insight]}
        voices={[]}
      />,
    )

    const live2d = screen.getByRole('button', { name: 'Live2D（未就绪）' })
    expect(live2d).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('播放器未就绪')).toBeInTheDocument()
    fireEvent.click(live2d)
    expect(screen.getByRole('img', { name: '初始立绘图片' })).toBeInTheDocument()
  })

  it('keeps voice records behind an explicit entry', () => {
    const voice: WikiMediaViewModel = {
      id: 'voice-1',
      title: '初见语音',
      url: 'https://example.test/voice.mp3',
      kind: 'voice',
      variant: 'unspecified',
      priority: 100,
    }
    render(
      <CharacterMediaStage
        title="槲寄生"
        portraitSlots={explicitSlots}
        portraits={[initial, insight]}
        voices={[voice]}
      />,
    )

    expect(screen.queryByTestId('voice-list')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '语音' }))
    expect(screen.getByTestId('voice-list')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '初见语音' })).toHaveAttribute('href', voice.url)
  })

  it('shows a fixed empty state without inventing a portrait', () => {
    render(
      <CharacterMediaStage
        title="未知角色"
        portraitSlots={{ initial: null, insight: null, extras: [] }}
        portraits={[]}
        voices={[]}
      />,
    )

    expect(screen.getByText('暂无立绘')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
