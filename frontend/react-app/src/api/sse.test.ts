import { describe, it, expect, vi, beforeEach } from 'vitest'
import { streamAsk } from './sse'
import type { AssetItem, MediaItem, SourceItem, VoicePanelPage } from '../types'

function mockFetchResponse(chunks: string[]) {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      chunks.forEach(c => controller.enqueue(encoder.encode(c)))
      controller.close()
    },
  })
  return {
    ok: true,
    body: stream,
    status: 200,
  } as Response
}

describe('streamAsk SSE 解析', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('正确解析 sources → tokens → done 事件序列', async () => {
    const chunks = [
      'event: sources\ndata: {"sources":[{"name":"塞梅尔维斯","category":"人物","source":"x.md","score":0.6}],"assets":[{"asset_id":"a2","role":"skill","alt":"神秘术","url":"http://minio/a2.png"}],"media":[{"media_id":"m2","asset_id":"a2","asset_type":"skill","mime":"image/png","title":"神秘术","alt":"神秘术","url":"http://minio/a2.png"}]}\n\n',
      'event: token\ndata: {"token":"6"}\n\n',
      'event: token\ndata: {"token":"是"}\n\n',
      'event: done\ndata: {"answer":"6是","sources":[],"assets":[{"asset_id":"a2","role":"skill","alt":"神秘术","url":"http://minio/a2.png"}],"media":[{"media_id":"m2","asset_id":"a2","asset_type":"skill","mime":"image/png","title":"神秘术","alt":"神秘术","url":"http://minio/a2.png"}]}\n\n',
    ]
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse(chunks))

    const tokens: string[] = []
    let sources: SourceItem[] = []
    let assets: AssetItem[] = []
    let media: MediaItem[] = []
    let doneAssets: AssetItem[] = []
    let doneMedia: MediaItem[] = []
    let doneAnswer = ''
    await streamAsk('6', null, {
      onSources: (s, a = [], m = []) => {
        sources = s
        assets = a
        media = m
      },
      onToken: t => { tokens.push(t) },
      onDone: (a, _s, returnedAssets = [], returnedMedia = []) => {
        doneAnswer = a
        doneAssets = returnedAssets
        doneMedia = returnedMedia
      },
      onError: () => {},
    })
    expect(sources).toHaveLength(1)
    expect(sources[0].name).toBe('塞梅尔维斯')
    expect(assets[0].asset_id).toBe('a2')
    expect(media[0].media_id).toBe('m2')
    expect(tokens).toEqual(['6', '是'])
    expect(doneAnswer).toBe('6是')
    expect(doneAssets[0].url).toBe('http://minio/a2.png')
    expect(doneMedia[0].url).toBe('http://minio/a2.png')
  })

  it('正确处理跨 chunk 拼接的事件块', async () => {
    const chunks = [
      'event: tok',
      'en\ndata: {"token":"6"}\n\nevent: do',
      'ne\ndata: {"answer":"6","sources":[]}\n\n',
    ]
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse(chunks))
    const tokens: string[] = []
    let done = false
    await streamAsk('q', null, {
      onSources: () => {},
      onToken: t => tokens.push(t),
      onDone: () => { done = true },
      onError: () => {},
    })
    expect(tokens).toEqual(['6'])
    expect(done).toBe(true)
  })

  it('HTTP 错误抛异常', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 503 } as Response)
    await expect(streamAsk('q', null, {
      onSources: () => {}, onToken: () => {}, onDone: () => {}, onError: () => {}
    })).rejects.toThrow('HTTP 503')
  })

  it('sends route options and action payload in request body', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse([
      'event: done\ndata: {"answer":"ok","sources":[]}\n\n',
    ]))

    await streamAsk('介绍一下十四行诗', null, {
      onSources: () => {},
      onToken: () => {},
      onDone: () => {},
      onError: () => {},
    }, undefined, { expanded: true, freeSupplement: false }, {
      label: '全部技能',
      query: '介绍十四行诗的全部技能',
      intent: 'skill',
    })

    const fetchBody = vi.mocked(fetch).mock.calls[0][1]?.body
    expect(JSON.parse(fetchBody as string)).toMatchObject({
      question: '介绍一下十四行诗',
      route_options: { expanded: true, free_supplement: false },
      action_payload: { label: '全部技能', query: '介绍十四行诗的全部技能', intent: 'skill' },
    })
  })

  it('sends ownership and semantic fields for an explicit action', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse([
      'event: done\ndata: {"answer":"ok","sources":[]}\n\n',
    ]))

    await streamAsk('question', null, {
      onSources: () => {},
      onToken: () => {},
      onDone: () => {},
      onError: () => {},
    }, undefined, undefined, {
      label: 'Expand',
      query: 'question',
      action_type: 'expand_parent',
      entity_id: 'char:3023',
      semantic_intents: ['skill'],
    })

    const fetchBody = vi.mocked(fetch).mock.calls[0][1]?.body
    expect(JSON.parse(fetchBody as string).action_payload).toMatchObject({
      action_type: 'expand_parent',
      entity_id: 'char:3023',
      semantic_intents: ['skill'],
    })
  })

  it('parses planning diagnostics and source debug fields from stream metadata', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse([
      'event: sources\ndata: {"sources":[{"name":"十四行诗","category":"人物","source":"Data:Char/3023.json","score":1,"child_id":"char:3023/profile:0000","parent_id":"char:3023/profile","section_kind":"profile"}],"planning_status":"fallback_timeout","planning_warning":"LLM 规划超时","planning_error":"timeout","omitted_actions":[],"failure_actions":[],"media_panels":[]}\n\n',
      'event: done\ndata: {"answer":"ok","sources":[],"planning_status":"fallback_timeout","planning_warning":"LLM 规划超时","planning_error":"timeout","omitted_actions":[],"failure_actions":[],"media_panels":[]}\n\n',
    ]))

    let sourceDebug: SourceItem | undefined
    let sourceMeta: any
    let doneMeta: any
    await streamAsk('介绍一下十四行诗', null, {
      onSources: (sources, _assets, _media, meta) => {
        sourceDebug = sources[0]
        sourceMeta = meta
      },
      onToken: () => {},
      onDone: (_answer, _sources, _assets, _media, meta) => {
        doneMeta = meta
      },
      onError: () => {},
    })

    expect(sourceDebug?.child_id).toBe('char:3023/profile:0000')
    expect(sourceDebug?.parent_id).toBe('char:3023/profile')
    expect(sourceDebug?.section_kind).toBe('profile')
    expect(sourceMeta.planningStatus).toBe('fallback_timeout')
    expect(sourceMeta.planningWarning).toBe('LLM 规划超时')
    expect(sourceMeta.planningError).toBe('timeout')
    expect(doneMeta.planningStatus).toBe('fallback_timeout')
  })

  it('parses a nonempty structured voice panel from sources and done metadata', async () => {
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
      total_lines: 2,
      has_more: true,
      next_cursor: 'cursor-1',
    }
    const wirePanel = JSON.stringify([panel])
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse([
      `event: sources\ndata: {"sources":[],"media_panels":${wirePanel}}\n\n`,
      `event: done\ndata: {"answer":"ok","sources":[],"media_panels":${wirePanel}}\n\n`,
    ]))

    let sourcePanel: VoicePanelPage | undefined
    let donePanel: VoicePanelPage | undefined
    await streamAsk('voice', null, {
      onSources: (_sources, _assets, _media, meta) => {
        const candidate = meta?.mediaPanels?.[0]
        if (candidate?.type === 'voice') sourcePanel = candidate
      },
      onToken: () => {},
      onDone: (_answer, _sources, _assets, _media, meta) => {
        const candidate = meta?.mediaPanels?.[0]
        if (candidate?.type === 'voice') donePanel = candidate
      },
      onError: () => {},
    })

    expect(sourcePanel).toEqual(panel)
    expect(donePanel).toEqual(panel)
  })

  it('sends conversation_id and parses memory metadata', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse([
      'event: sources\ndata: {"sources":[],"memory":{"status":"hit","turns_used":1,"rewrite_mode":"planner"}}\n\n',
      'event: done\ndata: {"answer":"ok","sources":[],"memory":{"status":"hit","turns_used":1,"rewrite_mode":"planner"}}\n\n',
    ]))
    let doneMeta: any

    await streamAsk(
      '技能呢',
      null,
      {
        onSources: () => {},
        onToken: () => {},
        onDone: (_answer, _sources, _assets, _media, meta) => { doneMeta = meta },
        onError: () => {},
      },
      undefined,
      { expanded: false, freeSupplement: false },
      null,
      '00000000-0000-4000-8000-000000000001',
    )

    const fetchBody = vi.mocked(fetch).mock.calls[0][1]?.body
    expect(JSON.parse(fetchBody as string)).toMatchObject({
      conversation_id: '00000000-0000-4000-8000-000000000001',
    })
    expect(doneMeta.memory).toEqual({
      status: 'hit',
      turns_used: 1,
      rewrite_mode: 'planner',
    })
  })
})
