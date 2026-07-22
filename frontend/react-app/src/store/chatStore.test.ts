import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'
import * as sse from '../api/sse'
import * as conversationApi from '../api/conversation'
import { conversationSession } from '../session/conversationSession'
import type { VoicePanelPage } from '../types'

const UUID_A = '00000000-0000-4000-8000-000000000001'
const UUID_B = '00000000-0000-4000-8000-000000000002'

describe('chatStore', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useChatStore.setState({
      messages: [],
      category: null,
      routeOptions: { expanded: false, freeSupplement: false },
      sending: false,
      abortController: null,
    })
    vi.spyOn(conversationSession, 'ready').mockResolvedValue(UUID_A)
    vi.spyOn(conversationSession, 'rotate').mockReturnValue(UUID_B)
    vi.spyOn(conversationApi, 'clearConversation').mockResolvedValue(undefined)
  })

  it('send 推入用户消息后流式追加 assistant 消息', async () => {
    vi.spyOn(sse, 'streamAsk').mockImplementation(async (_q, _c, cb) => {
      const assets = [{ asset_id: 'a2', role: 'skill', alt: '神秘术', url: 'http://minio/a2.png' }]
      cb.onSources([{ name: '塞梅尔维斯', category: '人物', source: 'x.md', score: 0.6 }], assets)
      cb.onToken('6')
      cb.onToken('是')
      cb.onDone('6是', [{ name: '塞梅尔维斯', category: '人物', source: 'x.md', score: 0.6 }], assets)
    })
    await useChatStore.getState().send('6是谁')
    const msgs = useChatStore.getState().messages
    expect(msgs).toHaveLength(2)
    expect(msgs[0].role).toBe('user')
    expect(msgs[0].content).toBe('6是谁')
    expect(msgs[1].role).toBe('assistant')
    expect(msgs[1].content).toBe('6是')
    expect(msgs[1].streaming).toBe(false)
    expect(msgs[1].sources).toHaveLength(1)
    expect(msgs[1].assets?.[0].url).toBe('http://minio/a2.png')
    expect(useChatStore.getState().sending).toBe(false)
  })

  it('marks assistant as generating after sources arrive before tokens', async () => {
    let callbacks: any
    let finishStream!: () => void
    vi.spyOn(sse, 'streamAsk').mockImplementation(async (_q, _c, cb) => {
      callbacks = cb
      await new Promise<void>((resolve) => {
        finishStream = resolve
      })
    })

    const pending = useChatStore.getState().send('who is Matilda')
    await Promise.resolve()
    callbacks.onSources([{ name: 'Matilda', category: '人物', source: 'x.md', score: 0.6 }])

    let assistant = useChatStore.getState().messages[1]
    expect(assistant.status).toBe('DeepSeek 正在根据检索来源生成回答...')

    callbacks.onToken('M')
    assistant = useChatStore.getState().messages[1]
    expect(assistant.status).toBeUndefined()

    callbacks.onDone('Matilda', assistant.sources ?? [])
    finishStream()
    await pending
  })

  it('setCategory 更新 category', () => {
    useChatStore.getState().setCategory('人物')
    expect(useChatStore.getState().category).toBe('人物')
    useChatStore.getState().setCategory(null)
    expect(useChatStore.getState().category).toBeNull()
  })

  it('clear 清空消息', async () => {
    useChatStore.setState({ messages: [{ id: '1', role: 'user', content: 'x' }] })
    await useChatStore.getState().clear()
    expect(useChatStore.getState().messages).toHaveLength(0)
  })

  it('keeps expanded and free supplement toggles independent', () => {
    useChatStore.getState().setRouteOption('expanded', true)
    expect(useChatStore.getState().routeOptions.expanded).toBe(true)
    expect(useChatStore.getState().routeOptions.freeSupplement).toBe(false)

    useChatStore.getState().setRouteOption('freeSupplement', true)
    expect(useChatStore.getState().routeOptions.expanded).toBe(true)
    expect(useChatStore.getState().routeOptions.freeSupplement).toBe(true)

    useChatStore.getState().setRouteOption('expanded', false)
    expect(useChatStore.getState().routeOptions.expanded).toBe(false)
    expect(useChatStore.getState().routeOptions.freeSupplement).toBe(true)
  })

  it('stores planning diagnostics from stream metadata on assistant messages', async () => {
    vi.spyOn(sse, 'streamAsk').mockImplementation(async (_q, _c, cb) => {
      cb.onSources(
        [{
          name: '十四行诗',
          category: '人物',
          source: 'Data:Char/3023.json',
          score: 1,
          child_id: 'char:3023/profile:0000',
          parent_id: 'char:3023/profile',
          section_kind: 'profile',
        }],
        [],
        [],
        {
          planningStatus: 'fallback_timeout',
          planningWarning: 'LLM 规划超时，已降级。',
          planningError: 'timeout',
        },
      )
      cb.onDone(
        'ok',
        [],
        [],
        [],
        {
          planningStatus: 'fallback_timeout',
          planningWarning: 'LLM 规划超时，已降级。',
          planningError: 'timeout',
        },
      )
    })

    await useChatStore.getState().send('介绍一下十四行诗')

    const assistant = useChatStore.getState().messages[1]
    expect(assistant.planningStatus).toBe('fallback_timeout')
    expect(assistant.planningWarning).toBe('LLM 规划超时，已降级。')
    expect(assistant.planningError).toBe('timeout')
  })

  it('stores a nonempty structured voice panel through sources and done updates', async () => {
    const panel: VoicePanelPage = {
      type: 'voice',
      grouping: 'voice_line',
      entity_id: 'char:test',
      lines: [{
        voice_line_id: 'char:test/voice:0001',
        title: 'Line one',
        variants: [{ media_id: 'voice-zh', asset_type: 'voice', language: 'zh', url: '/voice-zh.mp3' }],
      }],
      page_size: 1,
      total_lines: 1,
      has_more: false,
      next_cursor: null,
    }
    vi.spyOn(sse, 'streamAsk').mockImplementation(async (_q, _c, callbacks) => {
      callbacks.onSources([], [], [], { mediaPanels: [panel] })
      callbacks.onDone('ok', [], [], [], { mediaPanels: [panel] })
    })

    await useChatStore.getState().send('voice')

    const assistant = useChatStore.getState().messages[1]
    expect(assistant.mediaPanels).toEqual([panel])
    expect(assistant.mediaPanels?.[0].type).toBe('voice')
  })

  it('uses one conversation id for send and stores memory metadata', async () => {
    const memory = { status: 'hit' as const, turns_used: 1, rewrite_mode: 'planner' as const }
    vi.spyOn(sse, 'streamAsk').mockImplementation(async (_q, _c, callbacks) => {
      callbacks.onSources([], [], [], { memory })
      callbacks.onDone('ok', [], [], [], { memory })
    })

    await useChatStore.getState().send('技能呢')

    expect(sse.streamAsk).toHaveBeenCalledWith(
      '技能呢',
      null,
      expect.anything(),
      expect.anything(),
      { expanded: false, freeSupplement: false },
      null,
      UUID_A,
    )
    expect(useChatStore.getState().messages[1].memory).toEqual(memory)
  })

  it('clear aborts, deletes, clears and rotates even when DELETE fails', async () => {
    const order: string[] = []
    const controller = { abort: () => order.push('abort') } as unknown as AbortController
    useChatStore.setState({
      messages: [{ id: 'a', role: 'assistant', content: 'answer' }],
      category: '人物',
      routeOptions: { expanded: true, freeSupplement: true },
      sending: true,
      abortController: controller,
    })
    const unsubscribe = useChatStore.subscribe((state, previous) => {
      if (previous.messages.length > 0 && state.messages.length === 0) order.push('clear')
    })
    vi.mocked(conversationApi.clearConversation).mockImplementation(async () => {
      order.push('delete')
      throw new Error('offline')
    })
    vi.mocked(conversationSession.rotate).mockImplementation(() => {
      order.push('rotate')
      return UUID_B
    })

    await useChatStore.getState().clear()
    unsubscribe()

    expect(order).toEqual(['abort', 'delete', 'clear', 'rotate'])
    expect(useChatStore.getState().messages).toEqual([])
    expect(useChatStore.getState().category).toBe('人物')
    expect(useChatStore.getState().routeOptions).toEqual({
      expanded: true,
      freeSupplement: true,
    })
  })

  it('clear rotates before the next send and the old id is never reused', async () => {
    let currentId = UUID_A
    vi.mocked(conversationSession.ready).mockImplementation(async () => currentId)
    vi.mocked(conversationSession.rotate).mockImplementation(() => {
      currentId = UUID_B
      return currentId
    })
    vi.spyOn(sse, 'streamAsk').mockImplementation(async (_q, _c, callbacks) => {
      callbacks.onDone('ok', [])
    })

    await useChatStore.getState().clear()
    await useChatStore.getState().send('新问题')

    expect(conversationApi.clearConversation).toHaveBeenCalledWith(UUID_A)
    expect(sse.streamAsk).toHaveBeenCalledTimes(1)
    expect(vi.mocked(sse.streamAsk).mock.calls[0][6]).toBe(UUID_B)
  })

  it('keeps the existing sending gate for concurrent sends', async () => {
    let release!: () => void
    vi.spyOn(sse, 'streamAsk').mockImplementation(
      async () => new Promise<void>((resolve) => { release = resolve }),
    )

    const first = useChatStore.getState().send('first')
    const second = useChatStore.getState().send('second')
    await Promise.resolve()

    expect(sse.streamAsk).toHaveBeenCalledTimes(1)
    release()
    await Promise.all([first, second])
  })
})
