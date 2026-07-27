import type { WikiContentBlock, WikiPageDetail, WikiPageListItem } from '../../types/wiki'

export interface WikiIndexItemViewModel {
  pageId: string
  title: string
  meta: string
  thumbnail: string
  route: string
}

export interface WikiMediaViewModel {
  id: string
  title: string
  url: string
  kind: 'portrait' | 'image' | 'voice'
  variant: 'initial' | 'insight' | 'unspecified'
  priority: number
}

export interface WikiPortraitSlots {
  initial: WikiMediaViewModel | null
  insight: WikiMediaViewModel | null
  extras: WikiMediaViewModel[]
}

export interface WikiCharacterSectionGroups {
  profile: WikiContentBlock[]
  skills: WikiContentBlock[]
  inheritance: WikiContentBlock[]
  portray: WikiContentBlock[]
  voices: WikiContentBlock[]
  archive: WikiContentBlock[]
  remainder: WikiContentBlock[]
}

export interface WikiDossierField {
  label: string
  value: string
  href?: string
}

export interface WikiPageViewModel {
  page: WikiPageDetail
  portraits: WikiMediaViewModel[]
  portraitSlots: WikiPortraitSlots
  images: WikiMediaViewModel[]
  voices: WikiMediaViewModel[]
  primaryMedia: WikiMediaViewModel | null
  live2dAvailable: false
  profileFacts: WikiDossierField[]
  dossier: WikiDossierField[]
  blocks: WikiContentBlock[]
  characterSections: WikiCharacterSectionGroups
  fallbackText: string
}

const PROFILE_FIELDS = [
  '介质',
  '星级',
  '属性',
  '角色灵感',
  '伤害类型',
  '传承',
  'Udimo',
  '生日',
  '定位标签',
  '香调',
  '初始衣着',
  '洞悉本色',
  '出场章节',
] as const

const UNSAFE_MEDIA_URL_CHARACTERS = /[\s\\\u0000-\u001f\u007f]/

function decodedMediaPath(value: string): string | null {
  const schemeIndex = value.indexOf('://')
  const pathIndex = schemeIndex >= 0 ? value.indexOf('/', schemeIndex + 3) : 0
  const rawPath = pathIndex >= 0 ? value.slice(pathIndex) : '/'

  try {
    const decodedPath = decodeURIComponent(rawPath)
    if (UNSAFE_MEDIA_URL_CHARACTERS.test(decodedPath) || /[?#]/.test(decodedPath)) return null
    if (decodedPath.split('/').some((segment) => segment === '.' || segment === '..')) return null
    return decodedPath
  } catch {
    return null
  }
}

export function isPublicMediaUrl(value: unknown): value is string {
  if (
    typeof value !== 'string'
    || value.length === 0
    || UNSAFE_MEDIA_URL_CHARACTERS.test(value)
    || /[?#]/.test(value)
    || value.startsWith('//')
  ) {
    return false
  }

  const decodedPath = decodedMediaPath(value)
  if (!decodedPath) return false

  if (value.startsWith('/')) {
    const segments = decodedPath.slice(1).split('/')
    return value.startsWith('/media/')
      && decodedPath.startsWith('/media/')
      && segments.length >= 3
      && segments.every(Boolean)
  }

  try {
    const url = new URL(value)
    return (url.protocol === 'http:' || url.protocol === 'https:') && Boolean(url.hostname)
  } catch {
    return false
  }
}

function isPublicImageUrl(value: unknown): value is string {
  if (!isPublicMediaUrl(value)) return false
  const path = decodedMediaPath(value)
  return path !== null && /\.(?:avif|bmp|gif|jpe?g|png|svg|webp)$/i.test(path)
}

export function buildWikiIndexItem(page: WikiPageListItem): WikiIndexItemViewModel {
  const metaParts = [page.category || page.pageType, page.subtitle].filter(Boolean)
  return {
    pageId: page.pageId,
    title: page.title,
    meta: metaParts.join(' · '),
    thumbnail: isPublicImageUrl(page.thumbnail) ? page.thumbnail : '',
    route: page.route,
  }
}

export function buildWikiPageViewModel(page: WikiPageDetail): WikiPageViewModel {
  const media = page.mediaLinks
    .map(toMediaViewModel)
    .filter((item): item is WikiMediaViewModel => item !== null)
  const portraits = media
    .filter((item) => item.kind === 'portrait')
    .sort((left, right) => left.priority - right.priority)
  const images = media.filter((item) => item.kind === 'image')
  const voices = media.filter((item) => item.kind === 'voice')
  const initial = portraits.find((item) => item.variant === 'initial') ?? null
  const insight = portraits.find((item) => item.variant === 'insight') ?? null
  const portraitSlots: WikiPortraitSlots = {
    initial,
    insight,
    extras: portraits.filter((item) => item !== initial && item !== insight),
  }
  const fallbackText = firstText(page.content.fallbackText, page.content.body, page.content.text, page.summary)
  const sourceBlocks = Array.isArray(page.content.blocks) ? page.content.blocks : []
  const blocks = sourceBlocks.length > 0
    ? deduplicateContentBlocks(sourceBlocks)
    : buildFallbackBlocks(fallbackText)

  return {
    page,
    portraits,
    portraitSlots,
    images,
    voices,
    primaryMedia:
      initial
      ?? portraits.find((item) => item.variant === 'unspecified')
      ?? insight
      ?? images[0]
      ?? null,
    live2dAvailable: false,
    profileFacts: buildProfileFacts(page.content.profile),
    dossier: buildDossier(page),
    blocks,
    characterSections: groupCharacterSections(blocks),
    fallbackText,
  }
}

export function buildFallbackBlocks(text: string): WikiContentBlock[] {
  const normalized = String(text ?? '').replace(/\r\n?/g, '\n').trim()
  if (!normalized) return []

  const blocks: WikiContentBlock[] = []
  const push = (block: Omit<WikiContentBlock, 'id' | 'section' | 'mediaIds'>) => {
    blocks.push({
      ...block,
      id: `fallback-${String(blocks.length + 1).padStart(4, '0')}`,
      section: 'fallback',
      mediaIds: [],
    })
  }

  for (const segment of normalized.split(/\n\s*\n+/).map((item) => item.trim()).filter(Boolean)) {
    const heading = segment.match(/^(#{1,6})\s+(.+)$/s)
    if (heading) {
      push({ type: 'heading', level: Math.min(4, heading[1].length + 1), text: heading[2].trim() })
      continue
    }

    const lines = segment.split('\n').map((item) => item.trim()).filter(Boolean)
    const facts = lines.map(parseFactLine)
    if (facts.every((item) => item !== null)) {
      push({ type: 'facts', items: facts as Array<{ label: string; value: string }> })
      continue
    }

    for (const paragraph of splitLongParagraph(lines.join('\n'))) {
      push({ type: 'paragraph', text: paragraph })
    }
  }

  return blocks
}

function toMediaViewModel(item: Record<string, unknown>, index: number): WikiMediaViewModel | null {
  if (!isPublicMediaUrl(item.url)) return null
  const kind = mediaKind(item)
  if (!kind) return null
  const variant = kind === 'portrait' ? portraitVariant(item) : 'unspecified'
  const priority = kind === 'portrait'
    ? variant === 'initial' ? 0 : variant === 'unspecified' ? 10 : 20
    : kind === 'image' ? 30 : 100

  return {
    id: wikiMediaBindingKey(item, index),
    title: firstText(item.title, item.alt, item.mediaId, `媒体 ${index + 1}`),
    url: item.url,
    kind,
    variant,
    priority: priority + index / 10000,
  }
}

export function wikiMediaBindingKey(item: Record<string, unknown>, index = 0): string {
  return firstText(
    item.bindingId,
    item.binding_id,
    item.mediaId,
    item.media_id,
    item.assetId,
    item.asset_id,
    item.url,
    `media-${index}`,
  )
}

function portraitVariant(item: Record<string, unknown>): WikiMediaViewModel['variant'] {
  const variant = firstText(item.variant).toLowerCase()
  if (variant === 'initial' || variant === 'insight') return variant
  const role = firstText(item.role, item.assetType, item.asset_type).toLowerCase()
  if (['initial_portrait', 'portrait_initial'].includes(role)) return 'initial'
  if (['insight_portrait', 'portrait_insight'].includes(role)) return 'insight'
  return 'unspecified'
}

function mediaKind(item: Record<string, unknown>): WikiMediaViewModel['kind'] | null {
  const role = firstText(item.role, item.mediaRole, item.media_role).toLowerCase()
  if (role === 'roster_avatar') return null
  const kind = `${firstText(item.role)} ${firstText(item.assetType, item.asset_type)} ${firstText(item.mime)}`.toLowerCase()
  if (/voice|audio/.test(kind)) return 'voice'
  if (/portrait|standee|initial_portrait|portrait_initial|insight_portrait|portrait_insight/.test(kind)) return 'portrait'
  if (/image|skill/.test(kind)) return 'image'
  return null
}

function buildProfileFacts(value: unknown): WikiDossierField[] {
  if (!isRecord(value)) return []
  return PROFILE_FIELDS.flatMap((label) => {
    const display = displayValue(value[label])
    return display ? [{ label, value: display }] : []
  })
}

function buildDossier(page: WikiPageDetail): WikiDossierField[] {
  const aliases = Array.isArray(page.content.aliases)
    ? page.content.aliases.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
  return [
    { label: 'Source', value: firstText(page.sourceTitle, page.sourcePageid, 'unknown') },
    { label: 'Category', value: page.category || 'unknown' },
    { label: 'Type', value: page.pageType || 'unknown' },
    { label: 'Page ID', value: page.pageId || 'unknown' },
    { label: 'Assets', value: String(page.mediaLinks.length) },
    { label: 'Relations', value: String(page.relations.length) },
    { label: 'Links', value: String(page.linkSpans.length) },
    { label: 'Aliases', value: aliases.length > 0 ? aliases.join('\n') : '无' },
    { label: 'Route', value: page.route, href: page.route },
  ]
}

function groupCharacterSections(blocks: WikiContentBlock[]): WikiCharacterSectionGroups {
  const groups: WikiCharacterSectionGroups = {
    profile: [],
    skills: [],
    inheritance: [],
    portray: [],
    voices: [],
    archive: [],
    remainder: [],
  }
  for (const block of blocks) {
    const section = String(block.section ?? '').trim().toLowerCase()
    if (section === 'profile') groups.profile.push(block)
    else if (section === 'skill' || section === 'ultimate') groups.skills.push(block)
    else if (section === 'inheritance') groups.inheritance.push(block)
    else if (section === 'portray') groups.portray.push(block)
    else if (section === 'voice') groups.voices.push(block)
    else if (['dossier', 'culture', 'culture_dossier', 'collection', 'item', 'items'].includes(section)) groups.archive.push(block)
    else groups.remainder.push(block)
  }
  return groups
}

function copyBlock(block: WikiContentBlock): WikiContentBlock {
  return {
    ...block,
    mediaIds: [...block.mediaIds],
    items: block.items?.map((item) => typeof item === 'string' ? item : { ...item }),
    rows: block.rows?.map((row) => [...row]),
    paragraphs: block.paragraphs ? [...block.paragraphs] : undefined,
    tags: block.tags ? [...block.tags] : undefined,
  }
}

function deduplicateContentBlocks(source: WikiContentBlock[]): WikiContentBlock[] {
  const result: WikiContentBlock[] = []
  const bySignature = new Map<string, WikiContentBlock>()

  for (const sourceBlock of source) {
    const block = copyBlock(sourceBlock)
    const signature = JSON.stringify({
      type: block.type,
      section: block.section.trim().toLowerCase(),
      level: block.level ?? null,
      text: block.text?.trim() ?? '',
      items: block.items ?? null,
      rows: block.rows ?? null,
      value: block.value ?? null,
      title: block.title?.trim() ?? '',
      titleEn: block.titleEn?.trim() ?? '',
      kind: block.kind?.trim() ?? '',
      ordinal: block.ordinal ?? null,
      group: block.group?.trim() ?? '',
      groupEn: block.groupEn?.trim() ?? '',
      name: block.name?.trim() ?? '',
      nameEn: block.nameEn?.trim() ?? '',
      description: block.description?.trim() ?? '',
      paragraphs: block.paragraphs ?? null,
      tags: block.tags ?? null,
    })
    const existing = bySignature.get(signature)
    if (!existing) {
      bySignature.set(signature, block)
      result.push(block)
      continue
    }

    existing.mediaIds = [...new Set([...existing.mediaIds, ...block.mediaIds])]
    existing.reveal = Boolean(existing.reveal || block.reveal)
  }

  return result
}

function parseFactLine(line: string): { label: string; value: string } | null {
  const match = line.match(/^([^：:\n]{1,40})[：:]\s*(.+)$/s)
  if (!match) return null
  return { label: match[1].trim(), value: match[2].trim() }
}

function splitLongParagraph(text: string): string[] {
  if (text.length <= 240) return [text]
  const sentences = text.match(/[^。！？!?]+[。！？!?]?/g)?.map((item) => item.trim()).filter(Boolean) ?? [text]
  const result: string[] = []
  let current = ''
  for (const sentence of sentences) {
    if (current && current.length + sentence.length > 240) {
      result.push(current)
      current = sentence
    } else {
      current += sentence
    }
  }
  if (current) result.push(current)
  return result
}

function displayValue(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(displayValue).filter(Boolean).join('\n')
  return ''
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  }
  return ''
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
