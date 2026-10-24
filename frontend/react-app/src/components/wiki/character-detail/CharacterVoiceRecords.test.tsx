import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CharacterVoiceViewModel } from '../characterDetailViewModel'
import { CharacterVoiceRecords } from './CharacterVoiceRecords'

const voices: CharacterVoiceViewModel[] = [{
  id: 'voice-1',
  title: '初遇',
  languages: [
    {
      code: 'zh-CN',
      label: '中文',
      text: '很高兴认识你。',
      audio: {
        id: 'voice-zh',
        url: 'https://cdn.test/voice-zh.mp3',
        title: '初遇',
        mime: 'audio/mpeg',
        role: 'voice',
        sectionKey: 'voice',
        displayOrder: 1,
        width: 0,
        height: 0,
        variant: '',
      },
    },
    {
      code: 'en',
      label: 'English',
      text: 'Nice to meet you.',
      audio: {
        id: 'voice-en',
        url: 'https://cdn.test/voice-en.mp3',
        title: 'First meeting',
        mime: 'audio/mpeg',
        role: 'voice',
        sectionKey: 'voice',
        displayOrder: 2,
        width: 0,
        height: 0,
        variant: '',
      },
    },
  ],
}]

describe('CharacterVoiceRecords playback', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('keeps progress controls available while paused and restarts from the heading button', () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
    const { container } = render(<CharacterVoiceRecords voices={voices} />)
    const audio = container.querySelector('audio')!

    expect(audio).not.toHaveAttribute('controls')
    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))

    expect(play).toHaveBeenCalledTimes(1)
    expect(audio).toHaveAttribute('controls')
    expect(screen.getByRole('button', { name: '暂停初遇' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '暂停初遇' }))
    expect(pause).toHaveBeenCalledTimes(1)
    expect(audio).toHaveAttribute('controls')

    audio.currentTime = 7.5
    fireEvent.pause(audio)
    fireEvent.timeUpdate(audio)
    expect(audio).toHaveAttribute('controls')
    expect(screen.getByRole('button', { name: '播放初遇' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))
    expect(audio.currentTime).toBe(0)
    expect(play).toHaveBeenCalledTimes(2)
    expect(audio).toHaveAttribute('controls')
  })

  it('stops the current audio when changing its language', () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
    const { container } = render(<CharacterVoiceRecords voices={voices} />)

    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))
    fireEvent.click(screen.getByRole('button', { name: 'English' }))

    expect(pause).toHaveBeenCalledTimes(1)
    expect(container.querySelector('audio')).toHaveAttribute('src', 'https://cdn.test/voice-en.mp3')
    expect(container.querySelector('audio')).not.toHaveAttribute('controls')
    expect(screen.getByRole('button', { name: '播放初遇' })).toBeInTheDocument()
  })

  it('collapses the previous progress bar when another voice starts', () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
    const secondVoice = { ...voices[0], id: 'voice-2', title: '箱中气候' }
    const { container } = render(<CharacterVoiceRecords voices={[...voices, secondVoice]} />)
    const audios = container.querySelectorAll('audio')

    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))
    fireEvent.click(screen.getByRole('button', { name: '播放箱中气候' }))

    expect(audios[0]).not.toHaveAttribute('controls')
    expect(audios[1]).toHaveAttribute('controls')
    expect(audios[1].currentTime).toBe(0)
  })

  it('collapses the progress bar when its voice record leaves the viewport', () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
    let observerCallback: IntersectionObserverCallback = () => undefined
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: IntersectionObserverCallback) {
        observerCallback = callback
      }

      observe() {}
      disconnect() {}
    })
    const { container } = render(<CharacterVoiceRecords voices={voices} />)
    const audio = container.querySelector('audio')!

    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))
    expect(audio).toHaveAttribute('controls')
    act(() => {
      observerCallback([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver)
    })

    expect(pause).toHaveBeenCalledTimes(1)
    expect(audio).not.toHaveAttribute('controls')
    expect(screen.getByRole('button', { name: '播放初遇' })).toBeInTheDocument()
  })

  it('restores the play state when the browser rejects playback', async () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockRejectedValue(new Error('Not allowed'))
    const { container } = render(<CharacterVoiceRecords voices={voices} />)

    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))

    await waitFor(() => expect(screen.getByRole('button', { name: '播放初遇' })).toBeInTheDocument())
    expect(container.querySelector('audio')).not.toHaveAttribute('controls')
  })
})
