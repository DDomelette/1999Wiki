export interface WikiCategoryItem {
  key: string
  label: string
  count: number
  templateGroup?: string
  animationProfile?: string
  themeToken?: string
}

export interface WikiPageListItem {
  pageId: string
  pageType: string
  title: string
  subtitle: string
  category: string
  route: string
  thumbnail?: string
  summary?: string
}

export interface WikiPageListResponse {
  items: WikiPageListItem[]
  nextCursor?: string | null
}

export interface WikiPageDetail extends WikiPageListItem {
  content: Record<string, unknown> & { contentVersion?: number; blocks?: WikiContentBlock[] }
  mediaLinks: WikiMediaLink[]
  relations: Record<string, unknown>[]
  linkSpans: WikiPageLinkSpan[]
  sourcePageid?: number | null
  sourceTitle?: string
}

export interface WikiMediaLink extends Record<string, unknown> {
  bindingId?: string
  resourceId?: string
  mediaId?: string
  assetId?: string
  assetType?: string
  mime?: string
  url?: string
  title?: string
  alt?: string
  role?: string
  sectionKey?: string
  displayOrder?: number
  sha1?: string
  width?: number
  height?: number
  variant?: string
  attachPolicy?: string
  childId?: string
  parentId?: string
  panelGroup?: string
  sortOrder?: number
  durationMs?: number
  ownerEntityId?: string
  ownerPageId?: string
  skinId?: string
  eventName?: string
  language?: string
  sourceBindingToken?: string
  bindingStatus?: string
}

export interface WikiPageLinkSpan {
  sectionKey?: string
  text: string
  targetRoute?: string
  confidence?: number
}

export type WikiContentBlock = {
  id: string
  type: 'heading' | 'facts' | 'list' | 'quote' | 'table' | 'structured' | 'paragraph' | 'voice_reference'
  section: string
  mediaIds: string[]
  level?: number
  text?: string
  items?: Array<string | { label: string; value: string }>
  rows?: string[][]
  value?: unknown
  collapsed?: boolean
  reveal?: boolean
  title?: string
  titleEn?: string
  kind?: string
  ordinal?: number
  group?: string
  groupEn?: string
  name?: string
  nameEn?: string
  description?: string
  paragraphs?: string[]
  tags?: string[]
}

export interface WikiRouteResolveResponse {
  route?: string | null
  query: string
}

export interface WikiHealthResponse {
  ready: boolean
  pageCount: number
  categoryCount: number
  mediaLinkCount: number
  linkSpanCount: number
  aliasCount: number
  sourceMode: string
  buildVersion: string
  artifactSchemaVersion: string
  activationEpoch?: number | null
  manifestSha256Prefix: string
  stale: boolean
  error: string
}
