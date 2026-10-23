import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CharacterMediaViewModel, CharacterVoiceViewModel } from '../characterDetailViewModel'
import { CharacterVoiceRecords } from './CharacterVoiceRecords'

function audio(id: string): CharacterMediaViewModel {
  return {
    id,
    url: `https://cdn.test/${id}.mp3`,
    title: id,
    mime: 'audio/mpeg',
    role: 'voice',
    sectionKey: 'voice',
    displayOrder: 1,
    width: 0,
    height: 0,
    variant: '',
  }
}

const voices: CharacterVoiceViewModel[] = [{
  id: 'voice-1',
  title: '初遇',
  languages: [
    { code: 'zh-CN', label: '中文', text: '我是槲寄生。', audio: audio('voice-zh') },
    { code: 'en', label: 'English', text: 'I am Druvis III.', audio: audio('voice-en') },
  ],
}]

function mockPlayback() {
  return {
    play: vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(),
    pause: vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {}),
  }
}

afterEach(() => vi.restoreAllMocks())

describe('CharacterVoiceRecords playback', () => {
  it('starts audio and exposes the progress controls from the same play action', () => {
    const playback = mockPlayback()
    const { container } = render(<CharacterVoiceRecords voices={voices} />)
    const audioElement = container.querySelector('audio')!
    expect(audioElement.controls).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))

    expect(playback.play).toHaveBeenCalledTimes(1)
    expect(audioElement.controls).toBe(true)
    expect(screen.getByRole('button', { name: '暂停初遇' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '暂停初遇' }))
    expect(playback.pause).toHaveBeenCalled()
    expect(audioElement.controls).toBe(false)
  })

  it('resets the play state when playback ends', () => {
    mockPlayback()
    const { container } = render(<CharacterVoiceRecords voices={voices} />)
    const audioElement = container.querySelector('audio')!
    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))
    fireEvent.ended(audioElement)

    expect(audioElement.controls).toBe(false)
    expect(screen.getByRole('button', { name: '播放初遇' })).toBeInTheDocument()
  })

  it('stops the current audio when changing language', () => {
    const playback = mockPlayback()
    const { container } = render(<CharacterVoiceRecords voices={voices} />)
    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))
    fireEvent.click(screen.getByRole('button', { name: 'English' }))

    const audioElement = container.querySelector('audio')!
    expect(playback.pause).toHaveBeenCalled()
    expect(audioElement).toHaveAttribute('src', 'https://cdn.test/voice-en.mp3')
    expect(audioElement.controls).toBe(false)
    expect(screen.getByRole('button', { name: '播放初遇' })).toBeInTheDocument()
  })

  it('restores the play action when the browser rejects playback', async () => {
    const playback = mockPlayback()
    playback.play.mockRejectedValueOnce(new Error('NotAllowedError'))
    const { container } = render(<CharacterVoiceRecords voices={voices} />)
    const audioElement = container.querySelector('audio')!
    fireEvent.click(screen.getByRole('button', { name: '播放初遇' }))

    await waitFor(() => expect(audioElement.controls).toBe(false))
    expect(screen.getByRole('button', { name: '播放初遇' })).toBeInTheDocument()
  })
})
