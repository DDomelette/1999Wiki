import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchVoicePage, VoicePageError } from './media'
import type { VoicePanelPage } from '../types'

const PAGE: VoicePanelPage = {
  type: 'voice',
  grouping: 'voice_line',
  entity_id: 'char:test',
  lines: [
    {
      voice_line_id: 'char:test/voice:0001',
      title: 'Line one',
      variants: [
        {
          media_id: 'voice-zh',
          asset_type: 'voice',
          role: 'voice',
          language: 'zh',
          url: 'https://media.example/voice-zh.mp3',
        },
      ],
    },
  ],
  page_size: 1,
  total_lines: 2,
  has_more: true,
  next_cursor: 'next/cursor?token=a+b',
}

describe('fetchVoicePage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('gets the page with only an encoded cursor and forwards the signal', async () => {
    const signal = new AbortController().signal
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(PAGE),
    } as unknown as Response)

    await expect(fetchVoicePage('next/cursor?token=a+b', signal)).resolves.toEqual(PAGE)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith(
      '/api/media/voice/page?cursor=next%2Fcursor%3Ftoken%3Da%2Bb',
      { method: 'GET', signal },
    )
  })

  it('throws a typed 400 error without requesting a first-page reload', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: vi.fn().mockResolvedValue({ detail: 'Invalid voice cursor' }),
    } as unknown as Response)

    const error = await fetchVoicePage('invalid').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(VoicePageError)
    expect(error).toMatchObject({
      status: 400,
      reloadFirstPage: false,
      message: 'Invalid voice cursor',
    })
  })

  it('marks a typed 409 error as requiring a first-page reload', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: vi.fn().mockResolvedValue({ detail: 'Voice media build changed; reload first page' }),
    } as unknown as Response)

    const error = await fetchVoicePage('stale').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(VoicePageError)
    expect(error).toMatchObject({
      status: 409,
      reloadFirstPage: true,
      message: 'Voice media build changed; reload first page',
    })
  })
})
