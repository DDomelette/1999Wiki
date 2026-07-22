import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MessageBubble } from './MessageBubble'
import { MessageAssets } from './MessageAssets'
import { ChatInput } from './ChatInput'
import { MessageActions } from './MessageActions'
import { clearVoiceSessionPreferencesForTest, VoicePanel } from './VoicePanel'
import { VideoPanel } from './VideoPanel'
import type { MediaItem, Message, VoiceLineGroup, VoicePanelPage } from '../../types'
import { useChatStore } from '../../store/chatStore'

const originalSend = useChatStore.getState().send

type MotionMockProps = Record<string, unknown> & {
  children?: ReactNode
  layout?: boolean
  layoutId?: string
}

vi.mock('framer-motion', async () => {
  const React = await import('react')
  return {
    motion: new Proxy(
      {},
      {
        get: (_target, tag: string) =>
          ({ children, layout, layoutId, initial, animate, transition, whileInView, viewport, ...props }: MotionMockProps) =>
            React.createElement(
              tag,
              layoutId ? { ...props, 'data-layout-id': layoutId } : props,
              children,
            ),
      },
    ),
  }
})

function voiceVariant(mediaId: string, language: string, url = `/${mediaId}.mp3`): MediaItem {
  return {
    media_id: mediaId,
    asset_type: 'voice',
    role: 'voice',
    mime: 'audio/mpeg',
    language,
    url,
  }
}

function voicePage(
  lines: VoiceLineGroup[],
  options: Partial<Pick<VoicePanelPage, 'entity_id' | 'has_more' | 'next_cursor' | 'total_lines'>> = {},
): VoicePanelPage {
  return {
    type: 'voice',
    grouping: 'voice_line',
    entity_id: options.entity_id ?? 'char:test',
    lines,
    page_size: lines.length,
    total_lines: options.total_lines ?? lines.length,
    has_more: options.has_more ?? false,
    next_cursor: options.next_cursor ?? null,
  }
}

function stubAudio() {
  const audio = {
    pause: vi.fn(),
    play: vi.fn().mockResolvedValue(undefined),
    currentTime: 0,
    src: '',
    onended: null as (() => void) | null,
    ontimeupdate: null as (() => void) | null,
    duration: 0,
    removeAttribute: vi.fn(),
    load: vi.fn(),
  }
  audio.removeAttribute.mockImplementation((name: string) => {
    if (name === 'src') audio.src = ''
  })
  const constructor = vi.fn().mockImplementation(() => audio)
  vi.stubGlobal('Audio', constructor)
  return { audio, constructor }
}

describe('MessageBubble', () => {
  it('renders the server-provided citation ID without inferring array order', () => {
    const message: Message = {
      id: 'citation-message',
      role: 'assistant',
      content: 'Answer [S07]',
      sources: [{
        citation_id: 'S07',
        name: 'Source seven',
        category: 'fixture',
        source: 'fixture.json',
        score: 1,
      }],
    }
    useChatStore.setState({ messages: [message] })

    render(<MessageBubble message={message} />)

    expect(screen.getByText('[S07] Source seven')).toBeInTheDocument()
    expect(screen.queryByText('[S01] Source seven')).not.toBeInTheDocument()
  })

  beforeEach(() => {
    useChatStore.setState({ messages: [], sending: false, send: originalSend })
  })

  afterEach(() => {
    clearVoiceSessionPreferencesForTest()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders assistant markdown as formatted chat content', () => {
    const message: Message = {
      id: 'assistant-1',
      role: 'assistant',
      content: '## Foundation\nThis is **important** information.\n\n- Staff management\n- Arcane education',
    }

    const { container } = render(<MessageBubble message={message} />)

    expect(screen.getByRole('heading', { level: 2, name: 'Foundation' })).toBeInTheDocument()
    expect(container.querySelector('strong')).toHaveTextContent('important')
    expect(screen.getByText('Staff management').tagName).toBe('LI')
    expect(screen.getByText('Arcane education').tagName).toBe('LI')
  })

  it('keeps user messages as plain text instead of parsing markdown', () => {
    const message: Message = {
      id: 'user-1',
      role: 'user',
      content: '**do not parse me**',
    }

    const { container } = render(<MessageBubble message={message} />)

    expect(screen.getByText('**do not parse me**')).toBeInTheDocument()
    expect(container.querySelector('strong')).not.toBeInTheDocument()
  })

  it('does not assign a shared layout id to user bubbles', () => {
    const message: Message = {
      id: 'user-1',
      role: 'user',
      content: 'first question',
    }

    const { container } = render(<MessageBubble message={message} />)

    expect(container.querySelector('[data-layout-id]')).not.toBeInTheDocument()
  })

  it('renders assistant image assets below the answer', () => {
    render(
      <MessageBubble
        message={{
          id: 'assistant-assets',
          role: 'assistant',
          content: '这里是技能说明',
          assets: [{ asset_id: 'a2', role: 'skill', alt: '神秘术', url: 'http://minio/a2.png' }],
        }}
      />,
    )

    const image = screen.getByRole('img', { name: '神秘术' })
    expect(image).toHaveAttribute('src', 'http://minio/a2.png')
  })

  it('renders image media inside the circular gallery with a DOM fallback', () => {
    const { container } = render(
      <MessageBubble
        message={{
          id: 'assistant-image-panel',
          role: 'assistant',
          content: 'image panel',
          media: [
            {
              media_id: 'img-1',
              asset_type: 'portrait',
              mime: 'image/webp',
              title: 'Portrait 1',
              alt: 'Portrait 1',
              url: 'http://minio/img-1.webp',
            },
            {
              media_id: 'img-2',
              asset_type: 'image',
              mime: 'image/png',
              title: 'Portrait 2',
              alt: 'Portrait 2',
              url: 'http://minio/img-2.png',
            },
          ],
        }}
      />,
    )

    const panel = screen.getByTestId('image-panel')
    expect(panel).toHaveAttribute('data-animation-slot', 'image-panel')
    expect(panel.querySelector('.circular-gallery')).toHaveAttribute('data-bend', '0')
    expect(panel.querySelector('.circular-gallery')).toHaveAttribute('data-border-radius', '0.1')
    expect(container.querySelectorAll('[data-animation-slot="image-card"]')).toHaveLength(2)
  })

  it('keeps two bindings that share one compatibility media id', () => {
    const { container } = render(
      <MessageBubble
        message={{
          id: 'assistant-shared-resource-bindings',
          role: 'assistant',
          content: 'shared resource bindings',
          media: [
            {
              binding_id: 'binding:sha256:one',
              resource_id: 'resource:sha256:shared',
              media_id: 'media:sha1:shared',
              media_role: 'collection_item',
              asset_type: 'image',
              alt: 'Collection binding',
              url: 'http://minio/shared.webp',
            },
            {
              binding_id: 'binding:sha256:two',
              resource_id: 'resource:sha256:shared',
              media_id: 'media:sha1:shared',
              media_role: 'udimo',
              asset_type: 'image',
              alt: 'Udimo binding',
              url: 'http://minio/shared.webp',
            },
          ],
        }}
      />,
    )

    expect(container.querySelectorAll('[data-animation-slot="image-card"]')).toHaveLength(2)
    expect(screen.getByRole('img', { name: 'Collection binding' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Udimo binding' })).toBeInTheDocument()
  })

  it('fits image media inside cards without rendering filenames as captions', () => {
    const { container } = render(
      <MessageBubble
        message={{
          id: 'assistant-image-fit',
          role: 'assistant',
          content: 'image fit',
          media: [
            {
              media_id: 'img-fit',
              asset_type: 'portrait',
              mime: 'image/webp',
              title: 'File:Spine static-300301 hujisheng.webp',
              alt: 'File:Spine static-300301 hujisheng.webp',
              url: 'http://minio/img-fit.webp',
            },
          ],
        }}
      />,
    )

    const panel = screen.getByTestId('image-panel')
    const image = screen.getByRole('img', { name: 'File:Spine static-300301 hujisheng.webp' })

    expect(panel).toHaveTextContent('File:Spine static-300301 hujisheng.webp')
    expect(panel).toHaveTextContent('1/1')
    expect(container.querySelector('[data-animation-slot="image-caption"]')).not.toBeInTheDocument()
    expect(container.querySelector('.circular-gallery__viewport')).toBeInTheDocument()
    expect(image).toHaveAttribute('loading', 'lazy')
  })

  it('renders assistant audio media as a playback button', () => {
    render(
      <MessageBubble
        message={{
          id: 'assistant-media',
          role: 'assistant',
          content: '这里是语音说明',
          media: [{
            media_id: 'm-voice',
            asset_type: 'voice',
            mime: 'audio/mpeg',
            title: '玛蒂尔达语音',
            alt: '玛蒂尔达语音',
            url: 'http://minio/voice.mp3',
          }],
        }}
      />,
    )

    expect(screen.getByRole('button', { name: 'Play 玛蒂尔达语音' })).toBeInTheDocument()
  })

  it('renders markdown image syntax as a fallback', () => {
    render(
      <MessageBubble
        message={{
          id: 'assistant-markdown-image',
          role: 'assistant',
          content: '![技能图](http://minio/skill.png)',
        }}
      />,
    )

    const image = screen.getByRole('img', { name: '技能图' })
    expect(image).toHaveAttribute('src', 'http://minio/skill.png')
  })

  it('renders persistent route toggles under the input and keeps them independent', () => {
    useChatStore.setState({
      messages: [],
      sending: false,
      routeOptions: { expanded: false, freeSupplement: false },
    })

    render(<ChatInput />)

    const expanded = screen.getByRole('button', { name: '扩大检索' })
    const freeSupplement = screen.getByRole('button', { name: '自由补充' })

    expect(expanded).toHaveAttribute('data-action-kind', 'route-mode')
    expect(freeSupplement).toHaveAttribute('data-action-kind', 'route-mode')
    expect(expanded).toHaveAttribute('aria-pressed', 'false')
    expect(freeSupplement).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(expanded)
    expect(expanded).toHaveAttribute('aria-pressed', 'true')
    expect(freeSupplement).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(freeSupplement)
    expect(expanded).toHaveAttribute('aria-pressed', 'true')
    expect(freeSupplement).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders rescue buttons with distinct labels', () => {
    render(
      <MessageActions
        actions={[
          { label: '扩大范围重新搜索', query: '介绍一下十四行诗' },
          { label: '使用自由补充重答', query: '介绍一下十四行诗' },
        ]}
        variant="rescue"
        onAction={() => undefined}
      />,
    )

    expect(screen.getByRole('button', { name: '扩大范围重新搜索' })).toHaveAttribute('data-action-kind', 'recovery')
    expect(screen.getByRole('button', { name: '使用自由补充重答' })).toHaveAttribute('data-action-kind', 'recovery')
  })

  it('renders omitted action buttons with a separate action kind from rescue buttons', () => {
    render(
      <MessageActions
        actions={[{ label: '技能', query: '介绍十四行诗技能' }]}
        variant="omitted"
        onAction={() => undefined}
      />,
    )

    expect(screen.getByRole('button', { name: '技能' })).toHaveAttribute('data-action-kind', 'omitted')
  })

  it('separates message shell, body, media, sources, and actions into animation slots', () => {
    const { container } = render(
      <MessageBubble
        message={{
          id: 'assistant-structured',
          role: 'assistant',
          content: '这里是介绍',
          media: [{
            media_id: 'img-1',
            asset_type: 'portrait',
            mime: 'image/webp',
            title: '立绘',
            alt: '立绘',
            url: 'http://minio/img.webp',
          }],
          sources: [{ name: '十四行诗', category: '人物', source: 'Data:Char/3023.json', score: 1 }],
          omittedActions: [{ label: '技能', query: '介绍十四行诗技能' }],
          failureActions: [{ label: '扩大范围重新搜索', query: '介绍十四行诗' }],
        }}
      />,
    )

    expect(container.querySelector('[data-animation-slot="message-shell"]')).toBeInTheDocument()
    expect(container.querySelector('[data-animation-slot="message-body"]')).toBeInTheDocument()
    expect(container.querySelector('[data-animation-slot="message-media"]')).toBeInTheDocument()
    expect(container.querySelector('[data-animation-slot="message-sources"]')).toBeInTheDocument()
    expect(container.querySelectorAll('[data-animation-slot="message-actions"]')).toHaveLength(2)
  })

  it('renders one row per voice line with only its real languages and selects zh first', () => {
    render(
      <VoicePanel
        page={voicePage([{
          voice_line_id: 'line-1',
          title: 'First meeting',
          variants: [voiceVariant('v-en', 'en'), voiceVariant('v-zh', 'zh')],
        }])}
      />,
    )

    const rows = screen.getAllByTestId('voice-line')
    expect(screen.getByTestId('voice-panel')).toHaveAttribute('data-animation-slot', 'voice-panel')
    expect(screen.getByTestId('voice-panel')).toHaveClass('voice-panel-scroll')
    expect(screen.getByTestId('voice-panel')).toHaveAttribute('data-page-wheel-lock', 'true')
    expect(rows).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Select zh for First meeting' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Select en for First meeting' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Select jp for First meeting' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Play First meeting' })).toBeInTheDocument()
  })

  it('falls back through en, jp, kr, then the first stable other language', () => {
    render(
      <VoicePanel
        page={voicePage([
          { voice_line_id: 'line-en', title: 'English', variants: [voiceVariant('fr-1', 'fr'), voiceVariant('en-1', 'en')] },
          { voice_line_id: 'line-jp', title: 'Japanese', variants: [voiceVariant('kr-1', 'kr'), voiceVariant('jp-1', 'jp')] },
          { voice_line_id: 'line-kr', title: 'Korean', variants: [voiceVariant('es-1', 'es'), voiceVariant('kr-2', 'kr')] },
          { voice_line_id: 'line-other', title: 'Other', variants: [voiceVariant('fr-2', 'fr'), voiceVariant('es-2', 'es')] },
        ])}
      />,
    )

    expect(screen.getByRole('button', { name: 'Select en for English' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Select jp for Japanese' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Select kr for Korean' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Select fr for Other' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('stops and resets audio before switching language and uses the selected URL', () => {
    const { audio, constructor } = stubAudio()
    render(
      <VoicePanel
        page={voicePage([{
          voice_line_id: 'line-1',
          title: 'Line one',
          variants: [voiceVariant('zh-1', 'zh', '/zh.mp3'), voiceVariant('en-1', 'en', '/en.mp3')],
        }])}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Play Line one' }))
    expect(audio.src).toBe('/zh.mp3')
    fireEvent.click(screen.getByRole('button', { name: 'Select en for Line one' }))

    expect(audio.pause).toHaveBeenCalledTimes(1)
    expect(audio.currentTime).toBe(0)

    fireEvent.click(screen.getByRole('button', { name: 'Play Line one' }))
    expect(constructor).toHaveBeenCalledTimes(1)
    expect(audio.src).toBe('/en.mp3')
    expect(audio.play).toHaveBeenCalledTimes(2)
  })

  it('shows playback progress and remembers language for the same entity in this session', () => {
    const { audio } = stubAudio()
    const page = voicePage([{
      voice_line_id: 'line-session',
      title: 'Session line',
      variants: [voiceVariant('session-zh', 'zh'), voiceVariant('session-en', 'en')],
    }], { entity_id: 'char:session' })
    const first = render(<VoicePanel page={page} />)
    fireEvent.click(screen.getByRole('button', { name: 'Select en for Session line' }))
    fireEvent.click(screen.getByRole('button', { name: 'Play Session line' }))
    audio.duration = 10
    audio.currentTime = 4
    act(() => audio.ontimeupdate?.())
    expect(screen.getByRole('slider', { name: 'Playback progress for Session line' })).toHaveValue('40')
    first.unmount()

    render(<VoicePanel page={page} />)
    expect(screen.getByRole('button', { name: 'Select en for Session line' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('seeks the active voice line with a draggable progress slider', () => {
    const { audio } = stubAudio()
    render(
      <VoicePanel
        page={voicePage([{
          voice_line_id: 'line-seek',
          title: 'Seekable line',
          variants: [voiceVariant('seek-zh', 'zh')],
        }])}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Play Seekable line' }))
    audio.duration = 20
    fireEvent.change(screen.getByRole('slider', { name: 'Playback progress for Seekable line' }), { target: { value: '65' } })

    expect(audio.currentTime).toBe(13)
    expect(screen.getByRole('slider', { name: 'Playback progress for Seekable line' })).toHaveValue('65')
  })

  it('reuses one audio element and stops it before playing another line', () => {
    const { audio, constructor } = stubAudio()
    render(
      <VoicePanel
        page={voicePage([
          { voice_line_id: 'line-1', title: 'Line one', variants: [voiceVariant('zh-1', 'zh')] },
          { voice_line_id: 'line-2', title: 'Line two', variants: [voiceVariant('zh-2', 'zh')] },
        ])}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Play Line one' }))
    fireEvent.click(screen.getByRole('button', { name: 'Play Line two' }))

    expect(constructor).toHaveBeenCalledTimes(1)
    expect(audio.pause).toHaveBeenCalledTimes(1)
    expect(audio.currentTime).toBe(0)
    expect(audio.src).toBe('/zh-2.mp3')
    expect(audio.play).toHaveBeenCalledTimes(2)
  })

  it('loads one next page per click, disables while loading, and appends rows', async () => {
    let resolveFetch!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })))
    render(
      <VoicePanel
        page={voicePage(
          [{ voice_line_id: 'line-1', title: 'Line one', variants: [voiceVariant('zh-1', 'zh')] }],
          { has_more: true, next_cursor: 'cursor-1', total_lines: 2 },
        )}
      />,
    )

    const loadMore = screen.getByRole('button', { name: 'Load more voice lines' })
    fireEvent.click(loadMore)
    fireEvent.click(loadMore)

    expect(loadMore).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(1)
    resolveFetch({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(voicePage([
        { voice_line_id: 'line-2', title: 'Line two', variants: [voiceVariant('zh-2', 'zh')] },
      ])),
    } as unknown as Response)

    expect(await screen.findByText('Line two')).toBeInTheDocument()
    expect(screen.getByText('Line one')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load more voice lines' })).not.toBeInTheDocument()
    expect(screen.getByTestId('voice-panel')).toHaveClass('voice-panel-scroll')
  })

  it('deduplicates repeated line and media IDs while merging new variants', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(voicePage([
        {
          voice_line_id: 'line-1',
          title: 'Repeated line',
          variants: [voiceVariant('zh-1', 'zh'), voiceVariant('en-1', 'en'), voiceVariant('en-1', 'en')],
        },
        { voice_line_id: 'line-1', title: 'Repeated line again', variants: [voiceVariant('en-1', 'en')] },
        { voice_line_id: 'line-2', title: 'Line two', variants: [voiceVariant('jp-2', 'jp')] },
      ])),
    } as unknown as Response))
    render(
      <VoicePanel
        page={voicePage(
          [{ voice_line_id: 'line-1', title: 'Line one', variants: [voiceVariant('zh-1', 'zh')] }],
          { has_more: true, next_cursor: 'cursor-1', total_lines: 2 },
        )}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Load more voice lines' }))

    await waitFor(() => expect(screen.getAllByTestId('voice-line')).toHaveLength(2))
    expect(screen.getAllByRole('button', { name: 'Select en for Line one' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Select zh for Line one' })).toHaveLength(1)
  })

  it('upgrades an untouched automatic language default when a later page adds zh', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(voicePage([{
        voice_line_id: 'line-1',
        title: 'Line one',
        variants: [voiceVariant('zh-1', 'zh')],
      }])),
    } as unknown as Response))
    render(
      <VoicePanel
        page={voicePage(
          [{ voice_line_id: 'line-1', title: 'Line one', variants: [voiceVariant('en-1', 'en')] }],
          { has_more: true, next_cursor: 'cursor-1' },
        )}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Load more voice lines' }))

    expect(await screen.findByRole('button', { name: 'Select zh for Line one' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Select en for Line one' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('retains an explicit language override when a later page adds a higher-priority language', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(voicePage([{
        voice_line_id: 'line-1',
        title: 'Line one',
        variants: [voiceVariant('zh-1', 'zh')],
      }])),
    } as unknown as Response))
    render(
      <VoicePanel
        page={voicePage(
          [{ voice_line_id: 'line-1', title: 'Line one', variants: [voiceVariant('en-1', 'en')] }],
          { has_more: true, next_cursor: 'cursor-1' },
        )}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Select en for Line one' }))
    fireEvent.click(screen.getByRole('button', { name: 'Load more voice lines' }))

    expect(await screen.findByRole('button', { name: 'Select zh for Line one' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Select en for Line one' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('ignores a stale play rejection after a newer line starts', async () => {
    let rejectFirstPlay!: (error: Error) => void
    const { audio } = stubAudio()
    audio.play
      .mockReturnValueOnce(new Promise<void>((_resolve, reject) => {
        rejectFirstPlay = reject
      }))
      .mockResolvedValueOnce(undefined)
    render(
      <VoicePanel
        page={voicePage([
          { voice_line_id: 'line-a', title: 'Line A', variants: [voiceVariant('a-zh', 'zh')] },
          { voice_line_id: 'line-b', title: 'Line B', variants: [voiceVariant('b-zh', 'zh')] },
        ])}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Play Line A' }))
    fireEvent.click(screen.getByRole('button', { name: 'Play Line B' }))
    await act(async () => {
      rejectFirstPlay(new Error('stale failure'))
      await Promise.resolve()
    })

    expect(screen.getByRole('button', { name: 'Pause Line B' })).toBeInTheDocument()
  })

  it('ignores a stale ended callback after a newer line starts', () => {
    const { audio } = stubAudio()
    render(
      <VoicePanel
        page={voicePage([
          { voice_line_id: 'line-a', title: 'Line A', variants: [voiceVariant('a-zh', 'zh')] },
          { voice_line_id: 'line-b', title: 'Line B', variants: [voiceVariant('b-zh', 'zh')] },
        ])}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Play Line A' }))
    const staleEnded = audio.onended
    fireEvent.click(screen.getByRole('button', { name: 'Play Line B' }))
    act(() => staleEnded?.())

    expect(screen.getByRole('button', { name: 'Pause Line B' })).toBeInTheDocument()
  })

  it('keeps row columns shrinkable and wraps language controls within the panel width', () => {
    render(
      <VoicePanel
        page={voicePage([{
          voice_line_id: 'line-1',
          title: 'A line with a long title',
          variants: [
            voiceVariant('zh-1', 'zh'),
            voiceVariant('en-1', 'en'),
            voiceVariant('jp-1', 'jp'),
            voiceVariant('kr-1', 'kr'),
          ],
        }])}
      />,
    )

    expect(screen.getByTestId('voice-line')).toHaveStyle({
      gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr) auto',
    })
    expect(screen.getByRole('group', { name: 'Languages for A line with a long title' })).toHaveStyle({
      flexWrap: 'wrap',
      minWidth: '0',
      maxWidth: '100%',
    })
  })

  it('resets rows, overrides, cursor, loading, and audio for a different first-page identity', async () => {
    const { audio } = stubAudio()
    let resolveOldRequest!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn()
      .mockReturnValueOnce(new Promise<Response>((resolve) => {
        resolveOldRequest = resolve
      }))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue(voicePage([], { entity_id: 'char:next' })),
      } as unknown as Response))
    const firstPage = voicePage(
      [{
        voice_line_id: 'line-1',
        title: 'Old line',
        variants: [voiceVariant('old-zh', 'zh'), voiceVariant('old-en', 'en')],
      }],
      { entity_id: 'char:old', has_more: true, next_cursor: 'old-cursor', total_lines: 2 },
    )
    const { rerender } = render(<VoicePanel page={firstPage} />)

    fireEvent.click(screen.getByRole('button', { name: 'Select en for Old line' }))
    fireEvent.click(screen.getByRole('button', { name: 'Load more voice lines' }))
    fireEvent.click(screen.getByRole('button', { name: 'Play Old line' }))

    rerender(
      <VoicePanel
        page={voicePage(
          [{
            voice_line_id: 'line-1',
            title: 'New line',
            variants: [voiceVariant('new-en', 'en'), voiceVariant('new-zh', 'zh')],
          }],
          { entity_id: 'char:next', has_more: true, next_cursor: 'new-cursor', total_lines: 2 },
        )}
      />,
    )

    expect(screen.queryByText('Old line')).not.toBeInTheDocument()
    expect(screen.getByText('New line')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Select zh for New line' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Load more voice lines' })).toBeEnabled()
    expect(audio.pause).toHaveBeenCalledTimes(1)
    expect(audio.currentTime).toBe(0)

    fireEvent.click(screen.getByRole('button', { name: 'Load more voice lines' }))
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(vi.mocked(fetch).mock.calls[1][0]).toBe('/api/media/voice/page?cursor=new-cursor')

    resolveOldRequest({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(voicePage([
        { voice_line_id: 'late-old-line', title: 'Late old line', variants: [voiceVariant('late-zh', 'zh')] },
      ], { entity_id: 'char:old' })),
    } as unknown as Response)
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.queryByText('Late old line')).not.toBeInTheDocument()
  })

  it('clears a local page error when a different first page is received', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: vi.fn().mockResolvedValue({ detail: 'Invalid voice cursor' }),
    } as unknown as Response))
    const { rerender } = render(
      <VoicePanel
        page={voicePage(
          [{ voice_line_id: 'old-line', title: 'Old line', variants: [voiceVariant('old-zh', 'zh')] }],
          { entity_id: 'char:old', has_more: true, next_cursor: 'bad-cursor', total_lines: 2 },
        )}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Load more voice lines' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load more voice lines.')

    rerender(
      <VoicePanel
        page={voicePage(
          [{ voice_line_id: 'new-line', title: 'New line', variants: [voiceVariant('new-zh', 'zh')] }],
          { entity_id: 'char:new' },
        )}
      />,
    )

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('Old line')).not.toBeInTheDocument()
    expect(screen.getByText('New line')).toBeInTheDocument()
  })

  it('keeps panel-local state with stable identities when structured panels reorder', () => {
    const panelA = voicePage(
      [{
        voice_line_id: 'line-a',
        title: 'Line A',
        variants: [voiceVariant('a-zh', 'zh'), voiceVariant('a-en', 'en')],
      }],
      { entity_id: 'char:a' },
    )
    const panelB = voicePage(
      [{ voice_line_id: 'line-b', title: 'Line B', variants: [voiceVariant('b-zh', 'zh')] }],
      { entity_id: 'char:b' },
    )
    const { rerender } = render(<MessageAssets assets={[]} mediaPanels={[panelA, panelB]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Select en for Line A' }))
    rerender(<MessageAssets assets={[]} mediaPanels={[panelB, panelA]} />)

    expect(screen.getByRole('button', { name: 'Select en for Line A' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('shares one audio element across structured panels and cleans it up on unmount', () => {
    const { audio, constructor } = stubAudio()
    const panelA = voicePage(
      [{ voice_line_id: 'line-a', title: 'Line A', variants: [voiceVariant('a-zh', 'zh')] }],
      { entity_id: 'char:a' },
    )
    const panelB = voicePage(
      [{ voice_line_id: 'line-b', title: 'Line B', variants: [voiceVariant('b-zh', 'zh')] }],
      { entity_id: 'char:b' },
    )
    const { unmount } = render(<MessageAssets assets={[]} mediaPanels={[panelA, panelB]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Play Line A' }))
    fireEvent.click(screen.getByRole('button', { name: 'Play Line B' }))

    expect(constructor).toHaveBeenCalledTimes(1)
    expect(audio.pause).toHaveBeenCalledTimes(1)
    expect(audio.currentTime).toBe(0)
    expect(audio.src).toBe('/b-zh.mp3')

    unmount()
    expect(audio.pause).toHaveBeenCalledTimes(2)
    expect(audio.onended).toBeNull()
    expect(audio.removeAttribute).toHaveBeenCalledWith('src')
    expect(audio.load).toHaveBeenCalledTimes(1)
    expect(audio.src).toBe('')
  })

  it('releases audio owned by a keyed panel when MessageAssets replaces its identity', () => {
    const { audio, constructor } = stubAudio()
    const panelA = voicePage(
      [{ voice_line_id: 'line-a', title: 'Line A', variants: [voiceVariant('a-zh', 'zh')] }],
      { entity_id: 'char:a' },
    )
    const panelB = voicePage(
      [{ voice_line_id: 'line-b', title: 'Line B', variants: [voiceVariant('b-zh', 'zh')] }],
      { entity_id: 'char:b' },
    )
    const { rerender } = render(<MessageAssets assets={[]} mediaPanels={[panelA]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Play Line A' }))
    expect(audio.pause).not.toHaveBeenCalled()

    rerender(<MessageAssets assets={[]} mediaPanels={[panelB]} />)

    expect(audio.pause).toHaveBeenCalledTimes(1)
    expect(audio.currentTime).toBe(0)
    expect(audio.onended).toBeNull()
    expect(audio.removeAttribute).toHaveBeenCalledWith('src')
    expect(audio.load).toHaveBeenCalledTimes(1)
    expect(audio.src).toBe('')

    fireEvent.click(screen.getByRole('button', { name: 'Play Line B' }))
    expect(constructor).toHaveBeenCalledTimes(1)
    expect(audio.src).toBe('/b-zh.mp3')
  })

  it('does not stop active panel B when unrelated inactive panel A unmounts', () => {
    const { audio } = stubAudio()
    const panelA = voicePage(
      [{ voice_line_id: 'line-a', title: 'Line A', variants: [voiceVariant('a-zh', 'zh')] }],
      { entity_id: 'char:a' },
    )
    const panelB = voicePage(
      [{ voice_line_id: 'line-b', title: 'Line B', variants: [voiceVariant('b-zh', 'zh')] }],
      { entity_id: 'char:b' },
    )
    const { rerender } = render(<MessageAssets assets={[]} mediaPanels={[panelA, panelB]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Play Line B' }))
    expect(audio.pause).not.toHaveBeenCalled()

    rerender(<MessageAssets assets={[]} mediaPanels={[panelB]} />)

    expect(audio.pause).not.toHaveBeenCalled()
    expect(audio.removeAttribute).not.toHaveBeenCalled()
    expect(audio.load).not.toHaveBeenCalled()
    expect(audio.src).toBe('/b-zh.mp3')
    expect(screen.getByRole('button', { name: 'Pause Line B' })).toBeInTheDocument()
  })

  it('preserves rows and stops audio before a failed request and its local retry', async () => {
    const { audio } = stubAudio()
    vi.stubGlobal('fetch', vi.fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue(voicePage([
          { voice_line_id: 'line-2', title: 'Line two', variants: [voiceVariant('zh-2', 'zh')] },
        ])),
      } as unknown as Response))
    render(
      <VoicePanel
        page={voicePage(
          [{ voice_line_id: 'line-1', title: 'Line one', variants: [voiceVariant('zh-1', 'zh')] }],
          { has_more: true, next_cursor: 'cursor-1', total_lines: 2 },
        )}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Play Line one' }))
    fireEvent.click(screen.getByRole('button', { name: 'Load more voice lines' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load more voice lines.')
    expect(screen.getByText('Line one')).toBeInTheDocument()
    expect(audio.pause).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Play Line one' }))
    audio.pause.mockClear()
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading voice lines' }))

    expect(await screen.findByText('Line two')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(audio.pause).toHaveBeenCalledTimes(1)
    expect(audio.currentTime).toBe(0)
  })

  it('resubmits the preceding user question from the 409 reload command without clearing current content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: vi.fn().mockResolvedValue({ detail: 'Voice media build changed; reload first page' }),
    } as unknown as Response))
    const send = vi.fn().mockResolvedValue(undefined)
    const assistant: Message = {
      id: 'assistant-voice-409',
      role: 'assistant',
      content: 'Answer remains',
      sources: [{ name: 'Source one', category: 'character', source: 'source-1', score: 1 }],
      mediaPanels: [voicePage(
        [{ voice_line_id: 'line-1', title: 'Line one', variants: [voiceVariant('zh-1', 'zh')] }],
        { has_more: true, next_cursor: 'stale-cursor', total_lines: 2 },
      )],
    }
    useChatStore.setState({
      messages: [
        { id: 'user-before-voice', role: 'user', content: 'Show Matilda voice lines' },
        assistant,
      ],
      sending: false,
      send,
    })
    render(
      <MessageBubble message={assistant} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Load more voice lines' }))

    const reload = await screen.findByRole('button', { name: 'Reload voice first page' })
    expect(reload).toHaveAttribute('title', 'Reload voice first page')
    expect(screen.queryByRole('button', { name: 'Retry loading voice lines' })).not.toBeInTheDocument()
    expect(screen.getByText('Answer remains')).toBeInTheDocument()
    expect(screen.getByText('Source one')).toBeInTheDocument()
    expect(screen.getByText('Line one')).toBeInTheDocument()

    fireEvent.click(reload)
    expect(send).toHaveBeenCalledWith('Show Matilda voice lines')
    expect(screen.getByText('Line one')).toBeInTheDocument()

    useChatStore.setState({ sending: true })
    fireEvent.click(reload)
    expect(send).toHaveBeenCalledTimes(1)
  })

  it('renders structured voice once while preserving flat image and video media', () => {
    const { container } = render(
      <MessageBubble
        message={{
          id: 'assistant-structured-voice',
          role: 'assistant',
          content: 'Structured media',
          media: [
            voiceVariant('voice-zh', 'zh'),
            { media_id: 'image-1', asset_type: 'portrait', mime: 'image/png', url: '/image.png', alt: 'Portrait' },
            { media_id: 'video-1', asset_type: 'video', mime: 'video/mp4', url: '/video.mp4', title: 'Character video' },
          ],
          mediaPanels: [voicePage([{
            voice_line_id: 'line-1',
            title: 'Line one',
            variants: [voiceVariant('voice-zh', 'zh')],
          }])],
        }}
      />,
    )

    expect(container.querySelectorAll('[data-animation-slot="voice-line"]')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Play Line one' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Portrait' })).toBeInTheDocument()
    expect(screen.getByTitle('Character video')).toBeInTheDocument()
  })

  it('renders a structured legacy video panel without flat media', () => {
    render(
      <MessageBubble
        message={{
          id: 'assistant-structured-video',
          role: 'assistant',
          content: 'Structured video',
          mediaPanels: [{
            type: 'video',
            items: [{ media_id: 'video-1', asset_type: 'video', mime: 'video/mp4', url: '/video.mp4', title: 'Panel video' }],
          }],
        }}
      />,
    )

    expect(screen.getByTitle('Panel video')).toBeInTheDocument()
  })

  it('renders video panel with one primary video', () => {
    render(
      <VideoPanel
        items={[
          { media_id: 'm1', asset_type: 'video', mime: 'video/mp4', url: '/a.mp4', title: '角色PV' },
          { media_id: 'm2', asset_type: 'video', mime: 'video/mp4', url: '/b.mp4', title: '演示' },
        ]}
      />,
    )

    expect(screen.getByTestId('video-panel')).toHaveAttribute('data-animation-slot', 'video-panel')
    expect(screen.getByTitle('角色PV')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /更多视频/ })).toBeInTheDocument()
  })
})
