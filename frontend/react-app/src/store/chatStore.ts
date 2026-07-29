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
  activeRequestId: string | null
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
  activeRequestId: null,
  send: async (question: string, actionPayload: ActionItem | null = null) => {
    if (get().sending) return
    const requestId = makeId()
    const userMsg: Message = { id: makeId(), role: 'user', content: question }
    const assistantId = makeId()
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      streaming: true,
      finalized: false,
      phase: 'understanding',
    }
    const routeOptions = get().routeOptions
    set((s) => ({
      messages: [...s.messages, userMsg, assistantMsg],
      sending: true,
      activeRequestId: requestId,
    }))
    const controller = new AbortController()
    set({ abortController: controller })
    const updateActive = (patch: Partial<Message>) =>
      set((s) => ({
        messages: s.activeRequestId === requestId
          ? s.messages.map(m => m.id === assistantId ? { ...m, ...patch } : m)
          : s.messages,
      }))
    const showCorrectionNotice = () => {
      const current = get().messages.find(m => m.id === assistantId)
      if (current?.correctionNotice) return
      updateActive({ corrected: true, correctionNotice: true })
      setTimeout(() => {
        set((s) => ({
          messages: s.messages.map(m =>
            m.id === assistantId && m.correctionNotice
              ? { ...m, correctionNotice: false }
              : m
          ),
        }))
      }, 2500)
    }
    try {
      const conversationId = await conversationSession.ready()
      await streamAsk(question, get().category, {
        onSources: (sources: SourceItem[], assets = [], media: MediaItem[] = [], meta) =>
          updateActive({
            pendingSources: sources,
            pendingAssets: assets,
            pendingMedia: media,
            pendingMediaPanels: meta?.mediaPanels ?? [],
            groundingMode: meta?.groundingMode,
            citationWarning: meta?.citationWarning ?? '',
            route: meta?.route,
            planningStatus: meta?.planningStatus ?? '',
            planningWarning: meta?.planningWarning ?? '',
            planningError: meta?.planningError ?? '',
            omittedActions: meta?.omittedActions ?? [],
            failureActions: meta?.failureActions ?? [],
            memory: meta?.memory,
          }),
        onStatus: (phase) => {
          updateActive({ phase })
          if (phase === 'corrected') showCorrectionNotice()
        },
        onToken: (token: string) =>
          set((s) => ({
            messages: s.activeRequestId === requestId
              ? s.messages.map(m =>
                m.id === assistantId
                  ? { ...m, content: m.content + token }
                  : m
              )
              : s.messages,
          })),
        onAnswerReplace: (answer, reason) => {
          updateActive({
            content: answer,
            corrected: reason === 'citation_validation',
          })
          if (reason === 'citation_validation') showCorrectionNotice()
        },
        onDone: (answer, sources, assets = [], media: MediaItem[] = [], meta) =>
          updateActive({
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
            pendingSources: undefined,
            pendingAssets: undefined,
            pendingMedia: undefined,
            pendingMediaPanels: undefined,
            finalized: true,
            streaming: false,
            phase: undefined,
            partialError: false,
            status: undefined,
          }),
        onError: (msg, info) =>
          updateActive({
            content: info?.partial
              ? get().messages.find(m => m.id === assistantId)?.content ?? ''
              : `错误: ${msg}`,
            streaming: false,
            phase: 'failed',
            partialError: info?.partial === true,
            pendingSources: undefined,
            pendingAssets: undefined,
            pendingMedia: undefined,
            pendingMediaPanels: undefined,
          }),
      }, controller.signal, routeOptions, actionPayload, conversationId)
    } catch (e) {
      if (!isAbortError(e)) {
        updateActive({
          content: `请求失败: ${(e as Error).message}`,
          streaming: false,
          phase: 'failed',
          pendingSources: undefined,
          pendingAssets: undefined,
          pendingMedia: undefined,
          pendingMediaPanels: undefined,
        })
      }
    } finally {
      set((s) => s.activeRequestId === requestId
        ? { sending: false, abortController: null, activeRequestId: null }
        : s
      )
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
      activeRequestId: null,
      messages: s.messages.map((m, i) =>
        i === s.messages.length - 1 && m.role === 'assistant' && m.streaming
          ? {
            ...m,
            streaming: false,
            phase: 'cancelled',
            pendingSources: undefined,
            pendingAssets: undefined,
            pendingMedia: undefined,
            pendingMediaPanels: undefined,
          }
          : m
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
      set({
        messages: [],
        sending: false,
        abortController: null,
        activeRequestId: null,
      })
      conversationSession.rotate()
    }
  },
}))

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === 'AbortError'
    : error instanceof Error && error.name === 'AbortError'
}
