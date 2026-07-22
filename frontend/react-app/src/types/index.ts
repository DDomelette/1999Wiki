export interface SourceItem {
  citation_id?: string
  name: string
  category: string
  source: string
  score: number
  heading_path?: string | null
  chunk_index?: number | null
  retrieval_stage?: string | null
  child_id?: string | null
  parent_id?: string | null
  section_kind?: string | null
  entity_type?: string
  entity_id?: string
}

export interface AssetItem {
  asset_id: string
  name?: string
  category?: string
  source?: string
  heading_path?: string | null
  role: string
  alt: string
  url: string
}

export interface MediaItem {
  binding_id?: string
  resource_id?: string
  media_id: string
  asset_id?: string
  asset_type?: string
  media_role?: string
  mime?: string
  url: string
  title?: string
  alt?: string
  role?: string
  attach_policy?: string
  child_id?: string | null
  parent_id?: string | null
  section?: string
  source_binding_token?: string
  owner_entity_id?: string
  owner_page_id?: string
  variant?: string
  skin_id?: string
  panel_group?: string
  sort_order?: number
  duration_ms?: number
  language?: string
  entity_type?: string
  entity_id?: string
}

export interface RouteOptions {
  expanded: boolean
  freeSupplement: boolean
}

export interface ActionItem {
  label: string
  query: string
  action_type?: '' | 'expand_search' | 'force_free_supplement' | 'expand_parent'
  entity?: string
  entity_type?: string
  entity_id?: string
  semantic_intents?: string[]
  intent?: string
  packet_policy?: string
  target_parent_id?: string | null
}

export interface RouteInfo {
  name: string
  confidence?: number
  intent?: string
  entity?: string | null
  requested_intents?: string[]
  semantic_intents?: string[]
  proposed_route?: 'rag_grounded' | 'expanded_rag' | 'llm_general'
  effective_route?: 'rag_grounded' | 'expanded_rag' | 'llm_general'
  retrieval_outcome?: 'sufficient' | 'partial' | 'empty' | 'failed'
  route_reason?: string
}

export interface MemoryInfo {
  status: 'disabled' | 'new' | 'hit' | 'expired'
  turns_used: number
  rewrite_mode: 'none' | 'planner' | 'fallback'
}

export interface VoiceLineGroup {
  voice_line_id: string
  title: string
  variants: MediaItem[]
}

export interface VoicePanelPage {
  type: 'voice'
  grouping: 'voice_line'
  entity_id: string
  entity_type?: string
  lines: VoiceLineGroup[]
  page_size: number
  total_lines: number
  has_more: boolean
  next_cursor: string | null
}

export interface LegacyVideoPanel {
  type: 'video'
  items: MediaItem[]
}

export type MediaPanel = VoicePanelPage | LegacyVideoPanel

export interface CategoryMeta {
  key: string
  title: string
  subtitle: string
  description: string
  doc_count: number
  cover_prompt: string
}

export interface CategoryDoc {
  name: string
  source: string
  snippet: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  groundingMode?: 'grounded' | 'ungrounded' | 'none'
  citationWarning?: string
  sources?: SourceItem[]
  assets?: AssetItem[]
  media?: MediaItem[]
  route?: RouteInfo | null
  omittedActions?: ActionItem[]
  failureActions?: ActionItem[]
  mediaPanels?: MediaPanel[]
  planningStatus?: string
  planningWarning?: string
  planningError?: string
  memory?: MemoryInfo
  streaming?: boolean
  status?: string
}

export type Theme = 'storm-dark' | 'manuscript-gold' | 'cold-archive'
