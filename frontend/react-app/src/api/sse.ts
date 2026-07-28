import type { ActionItem, AssetItem, MediaItem, MediaPanel, MemoryInfo, RouteInfo, RouteOptions, SourceItem } from '../types'

export type StreamPhase =
  | 'understanding'
  | 'retrieving'
  | 'generating'
  | 'validating'
  | 'corrected'
  | 'cancelled'
  | 'failed'

export type AnswerReplaceReason = 'citation_validation' | 'safe_fallback'

export interface StreamErrorInfo {
  phase?: StreamPhase
  partial: boolean
}

export interface StreamMeta {
  groundingMode?: 'grounded' | 'ungrounded' | 'none'
  citationWarning?: string
  route?: RouteInfo | null
  planningStatus?: string
  planningWarning?: string
  planningError?: string
  omittedActions?: ActionItem[]
  failureActions?: ActionItem[]
  mediaPanels?: MediaPanel[]
  memory?: MemoryInfo
}

export interface StreamCallbacks {
  onSources: (sources: SourceItem[], assets?: AssetItem[], media?: MediaItem[], meta?: StreamMeta) => void
  onStatus?: (phase: StreamPhase) => void
  onToken: (token: string) => void
  onAnswerReplace?: (answer: string, reason: AnswerReplaceReason) => void
  onDone: (answer: string, sources: SourceItem[], assets?: AssetItem[], media?: MediaItem[], meta?: StreamMeta) => void
  onError: (msg: string, info?: StreamErrorInfo) => void
}

const STREAM_PHASES = new Set<StreamPhase>([
  'understanding',
  'retrieving',
  'generating',
  'validating',
  'corrected',
  'cancelled',
  'failed',
])

const ANSWER_REPLACE_REASONS = new Set<AnswerReplaceReason>([
  'citation_validation',
  'safe_fallback',
])

function metaFromPayload(data: Record<string, unknown>): StreamMeta {
  return {
    groundingMode: data.grounding_mode as StreamMeta['groundingMode'],
    citationWarning: (data.citation_warning as string | undefined) ?? '',
    route: (data.route as RouteInfo | null | undefined) ?? null,
    planningStatus: (data.planning_status as string | undefined) ?? '',
    planningWarning: (data.planning_warning as string | undefined) ?? '',
    planningError: (data.planning_error as string | undefined) ?? '',
    omittedActions: (data.omitted_actions as ActionItem[] | undefined) ?? [],
    failureActions: (data.failure_actions as ActionItem[] | undefined) ?? [],
    mediaPanels: (data.media_panels as MediaPanel[] | undefined) ?? [],
    memory: data.memory as MemoryInfo | undefined,
  }
}

function actionPayloadToWire(action?: ActionItem | null) {
  if (!action) return null
  return {
    label: action.label,
    query: action.query,
    action_type: action.action_type ?? '',
    entity: action.entity ?? '',
    entity_type: action.entity_type ?? '',
    entity_id: action.entity_id ?? '',
    semantic_intents: action.semantic_intents ?? [],
    intent: action.intent ?? '',
    packet_policy: action.packet_policy ?? '',
    target_parent_id: action.target_parent_id ?? null,
  }
}

export async function streamAsk(
  question: string,
  category: string | null,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  routeOptions: RouteOptions = { expanded: false, freeSupplement: false },
  actionPayload?: ActionItem | null,
  conversationId?: string | null,
): Promise<void> {
  const res = await fetch('/api/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      category,
      route_options: {
        expanded: routeOptions.expanded,
        free_supplement: routeOptions.freeSupplement,
      },
      action_payload: actionPayloadToWire(actionPayload),
      conversation_id: conversationId ?? null,
    }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminal = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      buffer += decoder.decode()
    }
    else {
      buffer += decoder.decode(value, { stream: true })
    }
    buffer = buffer.replace(/\r\n/g, '\n')
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      if (terminal || !block.trim() || block.trimStart().startsWith(':')) continue
      const eventMatch = block.match(/^event: (.+)$/m)
      const dataMatch = block.match(/^data: (.+)$/m)
      const event = eventMatch ? eventMatch[1] : 'message'
      const data = dataMatch ? JSON.parse(dataMatch[1]) : {}
      if (event === 'status') {
        const phase = data.phase as StreamPhase
        if (STREAM_PHASES.has(phase)) callbacks.onStatus?.(phase)
      }
      else if (event === 'sources') {
        callbacks.onSources(
          data.sources as SourceItem[],
          data.assets as AssetItem[] | undefined,
          data.media as MediaItem[] | undefined,
          metaFromPayload(data),
        )
      }
      else if (event === 'token') callbacks.onToken(data.token as string)
      else if (event === 'answer_replace') {
        const reason = data.reason as AnswerReplaceReason
        if (ANSWER_REPLACE_REASONS.has(reason)) {
          callbacks.onAnswerReplace?.(data.answer as string, reason)
        }
      }
      else if (event === 'done') {
        callbacks.onDone(
          data.answer as string,
          data.sources as SourceItem[],
          data.assets as AssetItem[] | undefined,
          data.media as MediaItem[] | undefined,
          metaFromPayload(data),
        )
        terminal = true
      }
      else if (event === 'error') {
        const phase = data.phase as StreamPhase | undefined
        callbacks.onError(data.message as string, {
          phase: phase && STREAM_PHASES.has(phase) ? phase : undefined,
          partial: data.partial === true,
        })
        terminal = true
      }
    }
    if (done) break
  }
}
