import { create } from 'zustand'
import type { ActionItem, MediaItem, Message, RouteOptions, SourceItem } from '../types'
import { clearConversation } from '../api/conversation'
import { streamAsk } from '../api/sse'
import { conversationSession } from '../session/conversationSession'

interface ChatState {
  messages: Message[]
  category: string | null
  routeOptions: RouteOptions
  sending: boolean
  abortController: AbortController | null
  send: (question: string, actionPayload?: ActionItem | null) => Promise<void>
  runAction: (action: ActionItem) => Promise<void>
  setRouteOption: (key: keyof RouteOptions, value: boolean) => void
  abort: () => void
  setCategory: (c: string | null) => void
  clear: () => Promise<void>
}

function makeId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  category: null,
  routeOptions: { expanded: false, freeSupplement: false },
  sending: false,
  abortController: null,
  send: async (question: string, actionPayload: ActionItem | null = null) => {
    if (get().sending) return
    const userMsg: Message = { id: makeId(), role: 'user', content: question }
    const assistantMsg: Message = { id: makeId(), role: 'assistant', content: '', streaming: true }
    const routeOptions = get().routeOptions
    set((s) => ({
      messages: [...s.messages, userMsg, assistantMsg],
      sending: true,
    }))
    const controller = new AbortController()
    set({ abortController: controller })
    const updateLast = (patch: Partial<Message>) =>
      set((s) => ({
        messages: s.messages.map((m, i) =>
          i === s.messages.length - 1 ? { ...m, ...patch } : m
        ),
      }))
    try {
      const conversationId = await conversationSession.ready()
      await streamAsk(question, get().category, {
        onSources: (sources: SourceItem[], assets = [], media: MediaItem[] = [], meta) =>
          updateLast({
            sources,
            assets,
            media,
            groundingMode: meta?.groundingMode,
            citationWarning: meta?.citationWarning ?? '',
            route: meta?.route,
            planningStatus: meta?.planningStatus ?? '',
            planningWarning: meta?.planningWarning ?? '',
            planningError: meta?.planningError ?? '',
            omittedActions: meta?.omittedActions ?? [],
            failureActions: meta?.failureActions ?? [],
            mediaPanels: meta?.mediaPanels ?? [],
            memory: meta?.memory,
            status: 'DeepSeek 正在根据检索来源生成回答...',
          }),
        onToken: (token: string) =>
          set((s) => ({
            messages: s.messages.map((m, i) =>
              i === s.messages.length - 1
                ? { ...m, content: m.content + token, status: undefined }
                : m
            ),
          })),
        onDone: (answer, sources, assets = [], media: MediaItem[] = [], meta) =>
          updateLast({
            content: answer,
            sources,
            assets,
            media,
            groundingMode: meta?.groundingMode,
            citationWarning: meta?.citationWarning ?? '',
            route: meta?.route,
            planningStatus: meta?.planningStatus ?? '',
            planningWarning: meta?.planningWarning ?? '',
            planningError: meta?.planningError ?? '',
            omittedActions: meta?.omittedActions ?? [],
            failureActions: meta?.failureActions ?? [],
            mediaPanels: meta?.mediaPanels ?? [],
            memory: meta?.memory,
            streaming: false,
            status: undefined,
          }),
        onError: (msg) => updateLast({ content: `错误: ${msg}`, streaming: false, status: undefined }),
      }, controller.signal, routeOptions, actionPayload, conversationId)
    } catch (e) {
      updateLast({ content: `请求失败: ${(e as Error).message}`, streaming: false, status: undefined })
    } finally {
      set({ sending: false, abortController: null })
    }
  },
  runAction: async (action: ActionItem) => {
    await get().send(action.query, action)
  },
  setRouteOption: (key, value) =>
    set((s) => ({
      routeOptions: { ...s.routeOptions, [key]: value },
    })),
  abort: () => {
    const c = get().abortController
    if (c) c.abort()
    set((s) => ({
      sending: false,
      abortController: null,
      messages: s.messages.map((m, i) =>
        i === s.messages.length - 1 ? { ...m, streaming: false, status: undefined } : m
      ),
    }))
  },
  setCategory: (c) => set({ category: c }),
  clear: async () => {
    const currentId = await conversationSession.ready()
    get().abort()
    try {
      await clearConversation(currentId)
    } catch {
      // Rotating below isolates later requests even when the server is offline.
    } finally {
      set({ messages: [], sending: false, abortController: null })
      conversationSession.rotate()
    }
  },
}))
