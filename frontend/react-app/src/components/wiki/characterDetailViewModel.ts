import type { WikiContentBlock, WikiMediaLink } from '../../types/wiki'
import type { WikiMediaViewModel, WikiPageViewModel } from './wikiViewModel'
import { isPublicMediaUrl } from './wikiViewModel'

export interface CharacterIdentityViewModel {
  pageId: string
  entityId: string
  name: string
  exonym: string
  aliases: string[]
  category: string
  route: string
  sourceTitle: string
  sourcePageid: number | null
}

export interface CharacterSummaryCardViewModel {
  key: 'rarity' | 'profession' | 'damageType' | 'inspiration'
  label: string
  value: string
  detail?: string
}

export interface CharacterArchiveMetadataViewModel {
  activeEra: string
  birthday: string
}

export interface CharacterProfileRowViewModel {
  key: string
  label: string
  value: string
}

export interface CharacterMediaViewModel {
  id: string
  url: string
  title: string
  mime: string
  role: string
  sectionKey: string
  displayOrder: number
  width: number
  height: number
  variant: string
  sourceBindingToken?: string
  eventName?: string
  language?: string
  skinId?: string
  panelGroup?: string
}

export interface CharacterPortraitStateViewModel {
  id: string
  label: string
  variant: 'initial' | 'insight' | 'unclassified'
  description: string
  live2dMedia: CharacterMediaViewModel | null
  portraitMedia: CharacterMediaViewModel | null
  backdrop: CharacterMediaViewModel | null
}

export interface CharacterSkillLevelViewModel {
  level: string
  effect: string
}

export interface CharacterSkillViewModel {
  id: string
  name: string
  kind: 'skill' | 'ultimate'
  description: string
  levels: CharacterSkillLevelViewModel[]
  image: CharacterMediaViewModel | null
}

export interface CharacterProgressionViewModel {
  title: string
  description: string
  levels: CharacterSkillLevelViewModel[]
}

export interface CharacterVoiceLanguageViewModel {
  code: 'zh-CN' | 'zh-TW' | 'en' | 'ja' | 'ko'
  label: string
  text: string
  audio: CharacterMediaViewModel | null
}

export interface CharacterVoiceViewModel {
  id: string
  title: string
  languages: CharacterVoiceLanguageViewModel[]
}

export interface CharacterCultureEntryViewModel {
  id: string
  ordinal: number
  title: string
  titleEn: string
  tags: string[]
  paragraphs: string[]
}

export interface CharacterCollectionItemViewModel {
  id: string
  ordinal: number
  name: string
  nameEn: string
  value: string
  description: string
  image: CharacterMediaViewModel | null
}

export interface CharacterCollectionGroupViewModel {
  id: string
  name: string
  nameEn: string
  items: CharacterCollectionItemViewModel[]
}

export interface CharacterTechnicalDossierViewModel {
  contentVersion: number | null
  projectionVersion: number | null
  sourceTitle: string
  sourcePageid: number | null
  route: string
}

export interface CharacterDetailViewModel {
  identity: CharacterIdentityViewModel
  summary: string
  quote: string
  location: string
  archiveMetadata: CharacterArchiveMetadataViewModel
  udimoMedia: CharacterMediaViewModel | null
  summaryCards: CharacterSummaryCardViewModel[]
  profileRows: CharacterProfileRowViewModel[]
  portraitStates: CharacterPortraitStateViewModel[]
  live2dAvailable: false
  skills: CharacterSkillViewModel[]
  inheritance: CharacterProgressionViewModel | null
  portray: CharacterProgressionViewModel | null
  voices: CharacterVoiceViewModel[]
  cultureEntries: CharacterCultureEntryViewModel[]
  collectionGroups: CharacterCollectionGroupViewModel[]
  technicalDossier: CharacterTechnicalDossierViewModel
}

const PROFILE_ROW_FIELDS = [
  ['medium', '介质'],
  ['stars', '星级'],
  ['inspiration', '属性'],
  ['characterInspiration', '角色灵感'],
  ['damageType', '伤害类型'],
  ['inheritance', '传承'],
  ['udimo', 'Udimo'],
  ['birthday', '生日'],
  ['position', '定位标签'],
  ['fragrance', '香调'],
  ['initialOutfit', '初始衣着'],
  ['insightOutfit', '洞悉本色'],
] as const

const LANGUAGE_MARKERS = {
  中文: { code: 'zh-CN', label: '中文' },
  繁中: { code: 'zh-TW', label: '繁中' },
  EN: { code: 'en', label: 'English' },
  日: { code: 'ja', label: '日本語' },
  韩: { code: 'ko', label: '한국어' },
} as const

type LanguageMarker = keyof typeof LANGUAGE_MARKERS
type VoiceCode = CharacterVoiceLanguageViewModel['code']

export function buildCharacterDetailViewModel(source: WikiPageViewModel): CharacterDetailViewModel {
  const { page } = source
  const profile = asRecord(page.content.profile)
  const mediaById = buildMediaMap(page.mediaLinks)
  const facts = buildFactMap(source.blocks)
  const pageIdParts = page.pageId.split(':')
  const dossierSummary = firstBlockText(source.blocks, 'dossier')
  const summary = firstText(dossierSummary, page.summary, page.content.summary)

  return {
    identity: {
      pageId: page.pageId,
      entityId: pageIdParts[pageIdParts.length - 1] || page.pageId,
      name: firstText(profile.Name, page.title),
      exonym: firstText(profile.exonym),
      aliases: toStringArray(profile.aliases),
      category: page.category,
      route: page.route,
      sourceTitle: firstText(page.sourceTitle, page.subtitle),
      sourcePageid: typeof page.sourcePageid === 'number' ? page.sourcePageid : null,
    },
    summary,
    quote: firstText(profile.银行彩色相片, profile.造像),
    location: firstText(profile.地点, extractLocation(dossierSummary)),
    archiveMetadata: {
      activeEra: extractActiveEra(summary),
      birthday: formatArchiveBirthday(firstText(profile.生日), summary),
    },
    udimoMedia: uniqueMediaValues(mediaById).find((item) => item.role === 'udimo') ?? null,
    summaryCards: buildSummaryCards(profile, facts),
    profileRows: buildProfileRows(profile),
    portraitStates: buildPortraitStates(source.portraits, page.mediaLinks, profile, page.content.skins),
    live2dAvailable: false,
    skills: buildSkills(source.characterSections.skills, mediaById),
    inheritance: buildProgression(source.characterSections.inheritance),
    portray: buildProgression(source.characterSections.portray),
    voices: buildVoices(source.characterSections.voices, mediaById),
    cultureEntries: buildCultureEntries(source.blocks),
    collectionGroups: buildCollectionGroups(source.blocks, page.mediaLinks, mediaById),
    technicalDossier: {
      contentVersion: typeof page.content.contentVersion === 'number' ? page.content.contentVersion : null,
      projectionVersion: typeof page.content.crawlerProjectionVersion === 'number'
        ? page.content.crawlerProjectionVersion
        : null,
      sourceTitle: firstText(page.sourceTitle, page.subtitle),
      sourcePageid: typeof page.sourcePageid === 'number' ? page.sourcePageid : null,
      route: page.route,
    },
  }
}

function buildSummaryCards(
  profile: Record<string, unknown>,
  facts: Map<string, string>,
): CharacterSummaryCardViewModel[] {
  const cards: CharacterSummaryCardViewModel[] = []
  const rarity = facts.get('稀有度') ?? ''
  const profession = facts.get('职业') ?? ''
  const rawDamage = firstText(profile.伤害类型, facts.get('伤害类型'))
  const damageCode = facts.get('伤害类型') ?? ''
  const damage = normalizeDamageType(rawDamage, damageCode)
  const inspiration = normalizeInspiration(firstText(profile.属性))

  if (rarity) cards.push({ key: 'rarity', label: '稀有度', value: rarity })
  if (profession) cards.push({ key: 'profession', label: '职业', value: profession })
  if (damage.value) {
    cards.push({
      key: 'damageType',
      label: 'DAMAGE_TYPE',
      value: damage.value,
      ...(damage.detail ? { detail: damage.detail } : {}),
    })
  }
  if (inspiration.value) {
    cards.push({
      key: 'inspiration',
      label: 'INSPIRATION',
      value: inspiration.value,
      ...(inspiration.detail ? { detail: inspiration.detail } : {}),
    })
  }
  return cards
}

function buildProfileRows(profile: Record<string, unknown>): CharacterProfileRowViewModel[] {
  const rows: CharacterProfileRowViewModel[] = []
  for (const [key, label] of PROFILE_ROW_FIELDS) {
    const value = displayValue(profile[label])
    if (!value) continue
    if (label === '伤害类型') {
      const normalized = normalizeDamageType(value, '')
      if (normalized.value) rows.push({ key, label, value: normalized.value })
      continue
    }
    rows.push({ key, label, value })
  }
  return rows
}

function buildPortraitStates(
  portraits: WikiMediaViewModel[],
  mediaLinks: WikiMediaLink[],
  profile: Record<string, unknown>,
  skinsValue: unknown,
): CharacterPortraitStateViewModel[] {
  const direct = buildMediaMap(mediaLinks)
  const crawlerSkins = Array.isArray(skinsValue)
    ? skinsValue.map(asRecord).filter((skin) => Object.keys(skin).length > 0)
    : []
  const crawlerStates = crawlerSkins.flatMap((skin, index) => {
    const mediaIds = asRecord(skin.mediaIds)
    const skinId = firstText(skin.id)
    const live2d = resolveMediaReference(direct, firstText(mediaIds.stage_live2d))
      ?? findSkinMedia(direct, skinId, 'stage_live2d')
    const portrait = resolveMediaReference(direct, firstText(mediaIds.stage_portrait))
      ?? findSkinMedia(direct, skinId, 'stage_portrait')
    if (!live2d && !portrait) return []
    const backdrop = resolveMediaReference(direct, firstText(mediaIds.skin_background))
      ?? findSkinMedia(direct, skinId, 'skin_background')
    const variant: CharacterPortraitStateViewModel['variant'] = index === 0
      ? 'initial'
      : index === 1 ? 'insight' : 'unclassified'
    const label = firstText(
      skin.name,
      skin.nameEng,
      index === 0 ? '初始' : index === 1 ? '洞悉' : `立绘 ${index + 1}`,
    )
    return [{
      id: live2d?.id ?? portrait?.id ?? '',
      label,
      variant,
      description: firstText(skin.description),
      live2dMedia: live2d,
      portraitMedia: portrait,
      backdrop,
    }]
  })
  if (crawlerStates.length > 0) return crawlerStates

  const candidates = portraits.flatMap((portrait) => {
    const media = resolveMediaReference(direct, portrait.id)
    return media ? [{ portrait, media }] : []
  })
  const explicit = candidates.filter(({ portrait }) => portrait.variant === 'initial' || portrait.variant === 'insight')
  const selected = explicit.length > 0
    ? ['initial', 'insight'].flatMap((variant) => {
        const match = explicit.find(({ portrait }) => portrait.variant === variant)
        return match ? [match] : []
      })
    : candidates.slice(0, 2)

  return selected.map(({ portrait, media }, index) => {
    const variant = portrait.variant === 'initial' || portrait.variant === 'insight'
      ? portrait.variant
      : 'unclassified'
    const description = variant === 'initial'
      ? firstText(profile.初始衣着)
      : variant === 'insight' ? firstText(profile.洞悉本色) : ''
    const label = variant === 'initial'
      ? '初始'
      : variant === 'insight' ? '洞悉' : selected.length === 1 ? '立绘' : `立绘 ${index + 1}`
    return {
      id: portrait.id,
      label,
      variant,
      description,
      live2dMedia: null,
      portraitMedia: media,
      backdrop: null,
    }
  })
}

function buildSkills(
  blocks: WikiContentBlock[],
  mediaById: Map<string, CharacterMediaViewModel>,
): CharacterSkillViewModel[] {
  const groups = new Map<string, WikiContentBlock[]>()
  const order: string[] = []
  for (const contentBlock of blocks) {
    const mediaId = contentBlock.mediaIds.find((id) => resolveMediaReference(mediaById, id)?.role === 'skill')
      ?? contentBlock.mediaIds.find((id) => resolveMediaReference(mediaById, id))
      ?? ''
    if (!mediaId) continue
    if (!groups.has(mediaId)) {
      groups.set(mediaId, [])
      order.push(mediaId)
    }
    groups.get(mediaId)?.push(contentBlock)
  }

  const explicit = order.flatMap((mediaId) => {
    const group = groups.get(mediaId) ?? []
    const media = resolveMediaReference(mediaById, mediaId)
    return buildSkillFromBlocks(group, media)
  })
  if (explicit.length > 0) return explicit

  const media = uniqueMediaValues(mediaById)
    .filter((item) => item.role === 'skill')
    .sort((left, right) => left.displayOrder - right.displayOrder)
  const used = new Set<string>()
  return buildImplicitSkillGroups(blocks).flatMap((group, index) => {
    const heading = group.find((item) => item.type === 'heading')
    const paragraph = group.find((item) => item.type === 'paragraph')
    const paragraphLines = firstText(paragraph?.text).split('\n').map((item) => item.trim()).filter(Boolean)
    const name = firstText(heading?.text, paragraphLines[0])
    if (!name) return []
    const matched = media.find((item) => (
      !used.has(item.id) && comparableText(item.title) === comparableText(name)
    )) ?? media.find((item) => !used.has(item.id)) ?? null
    if (matched) used.add(matched.id)
    const description = paragraphLines.slice(1).join('\n')
    const levels = group.flatMap((item) => item.type === 'table' ? tableLevels(item.rows) : [])
    const kind: CharacterSkillViewModel['kind'] = /^ultimate:/i.test(matched?.sourceBindingToken ?? '')
      || /至终的仪式|ultimate/i.test(`${name}\n${description}`)
      ? 'ultimate'
      : 'skill'
    return [{ id: matched?.id ?? `skill-${index + 1}`, name, kind, description, levels, image: matched }]
  })
}

function buildSkillFromBlocks(
  group: WikiContentBlock[],
  media: CharacterMediaViewModel | null,
): CharacterSkillViewModel[] {
  const heading = group.find((item) => item.type === 'heading')
  const paragraph = group.find((item) => item.type === 'paragraph')
  const paragraphLines = firstText(paragraph?.text).split('\n').map((item) => item.trim()).filter(Boolean)
  const name = firstText(heading?.text, paragraphLines[0], media?.title)
  if (!name) return []
  const description = paragraphLines.slice(1).join('\n')
  const levels = group.flatMap((item) => item.type === 'table' ? tableLevels(item.rows) : [])
  const kind: CharacterSkillViewModel['kind'] = /^ultimate:/i.test(media?.sourceBindingToken ?? '')
    || /至终的仪式|ultimate/i.test(`${name}\n${description}`)
    ? 'ultimate'
    : 'skill'
  return [{ id: media?.id ?? group[0]?.id ?? name, name, kind, description, levels, image: media }]
}

function buildImplicitSkillGroups(blocks: WikiContentBlock[]): WikiContentBlock[][] {
  const groups: WikiContentBlock[][] = []
  let current: WikiContentBlock[] = []
  const flush = () => {
    if (current.length > 0) groups.push(current)
    current = []
  }
  for (const block of blocks) {
    if (block.type === 'heading') {
      flush()
      current = [block]
    } else if (block.type === 'paragraph') {
      flush()
      groups.push([block])
    } else if (current.length > 0) {
      current.push(block)
    }
  }
  flush()
  return groups
}

function buildProgression(blocks: WikiContentBlock[]): CharacterProgressionViewModel | null {
  const title = firstText(blocks.find((item) => item.type === 'heading')?.text)
  const description = firstText(blocks.find((item) => item.type === 'paragraph')?.text)
  const levels = blocks.flatMap((item) => item.type === 'table' ? tableLevels(item.rows) : [])
  if (!title && !description && levels.length === 0) return null
  return { title, description, levels }
}

function buildVoices(
  blocks: WikiContentBlock[],
  mediaById: Map<string, CharacterMediaViewModel>,
): CharacterVoiceViewModel[] {
  const seen = new Set<string>()
  const titleOccurrences = new Map<string, number>()
  const voiceMedia = uniqueMediaValues(mediaById)
    .filter((item) => item.role === 'voice')
    .sort((left, right) => left.displayOrder - right.displayOrder)
  const voices: CharacterVoiceViewModel[] = []
  for (const contentBlock of blocks) {
    const title = firstText(contentBlock.title, firstText(contentBlock.text).split('\n')[0])
    const languages = parseVoiceLanguages(firstText(contentBlock.text), title)
    if (!title || languages.length === 0) continue
    const signature = JSON.stringify([title, languages.map((item) => [item.code, item.text])])
    if (seen.has(signature)) continue
    seen.add(signature)

    const audioByLanguage = new Map<VoiceCode, CharacterMediaViewModel>()
    for (const mediaId of contentBlock.mediaIds) {
      const item = resolveMediaReference(mediaById, mediaId)
      const code = item ? voiceLanguageFromMedia(item) : null
      if (item && code && !audioByLanguage.has(code)) audioByLanguage.set(code, item)
    }
    const titleKey = comparableText(title)
    const occurrence = titleOccurrences.get(titleKey) ?? 0
    titleOccurrences.set(titleKey, occurrence + 1)
    for (const language of languages) {
      if (audioByLanguage.has(language.code)) continue
      const candidates = voiceMedia.filter((item) => (
        comparableText(item.title) === titleKey && voiceLanguageFromMedia(item) === language.code
      ))
      const item = candidates[occurrence] ?? candidates[0]
      if (item) audioByLanguage.set(language.code, item)
    }
    voices.push({
      id: contentBlock.id,
      title,
      languages: languages.map((item) => ({ ...item, audio: audioByLanguage.get(item.code) ?? null })),
    })
  }
  return voices
}

function buildCultureEntries(blocks: WikiContentBlock[]): CharacterCultureEntryViewModel[] {
  return blocks
    .filter((item) => item.section === 'culture_dossier' && item.type === 'structured')
    .flatMap((item) => {
      const title = firstText(item.title)
      const paragraphs = toStringArray(item.paragraphs)
      if (!title && paragraphs.length === 0) return []
      return [{
        id: item.id,
        ordinal: numberValue(item.ordinal),
        title,
        titleEn: firstText(item.titleEn),
        tags: toStringArray(item.tags),
        paragraphs,
      }]
    })
    .sort((left, right) => left.ordinal - right.ordinal)
}

function buildCollectionGroups(
  blocks: WikiContentBlock[],
  mediaLinks: WikiMediaLink[],
  mediaById: Map<string, CharacterMediaViewModel>,
): CharacterCollectionGroupViewModel[] {
  const collectionMedia = mediaLinks
    .filter((item) => firstText(item.sectionKey, item.section_key) === 'collection')
    .filter((item) => firstText(item.role, item.assetType, item.asset_type) === 'collection_item')
    .sort((left, right) => numberValue(left.displayOrder ?? left.display_order) - numberValue(right.displayOrder ?? right.display_order))
  const groups = new Map<string, CharacterCollectionGroupViewModel>()

  for (const contentBlock of blocks) {
    if (contentBlock.section !== 'collection'
      || contentBlock.type !== 'structured'
      || contentBlock.kind !== 'collection_item') continue
    const name = firstText(contentBlock.name)
    const groupName = firstText(contentBlock.group)
    if (!name || !groupName) continue
    const ordinal = numberValue(contentBlock.ordinal)
    const linkedMedia = contentBlock.mediaIds
      .map((id) => resolveMediaReference(mediaById, id))
      .find((item): item is CharacterMediaViewModel => Boolean(item))
      ?? uniqueMediaValues(mediaById).find((item) => (
        item.role === 'collection_item' && comparableText(item.title) === comparableText(name)
      ))
      ?? resolveMediaReference(
        mediaById,
        firstText(collectionMedia[ordinal - 1]?.bindingId, collectionMedia[ordinal - 1]?.mediaId),
      )
    const groupKey = `${groupName}\0${firstText(contentBlock.groupEn)}`
    if (!groups.has(groupKey)) {
      groups.set(groupKey, {
        id: `collection-group-${groups.size + 1}`,
        name: groupName,
        nameEn: firstText(contentBlock.groupEn),
        items: [],
      })
    }
    groups.get(groupKey)?.items.push({
      id: contentBlock.id,
      ordinal,
      name,
      nameEn: firstText(contentBlock.nameEn),
      value: firstText(contentBlock.value),
      description: firstText(contentBlock.description),
      image: linkedMedia,
    })
  }

  return [...groups.values()].map((group) => ({
    ...group,
    items: [...group.items].sort((left, right) => left.ordinal - right.ordinal),
  }))
}

function buildMediaMap(items: WikiMediaLink[]): Map<string, CharacterMediaViewModel> {
  const result = new Map<string, CharacterMediaViewModel>()
  for (const item of items) {
    const bindingId = firstText(item.bindingId, item.binding_id)
    const compatibilityId = firstText(item.mediaId, item.media_id, item.assetId, item.asset_id)
    const id = firstText(bindingId, compatibilityId)
    const url = firstText(item.url)
    if (!id || !isPublicMediaUrl(url)) continue
    const viewModel = {
      id,
      url,
      title: firstText(item.title, item.alt, id),
      mime: firstText(item.mime),
      role: firstText(item.role, item.assetType, item.asset_type),
      sectionKey: firstText(item.sectionKey, item.section_key),
      displayOrder: numberValue(item.displayOrder ?? item.display_order),
      width: numberValue(item.width),
      height: numberValue(item.height),
      variant: firstText(item.variant),
      sourceBindingToken: firstText(item.sourceBindingToken, item.source_binding_token),
      eventName: firstText(item.eventName, item.event_name),
      language: firstText(item.language),
      skinId: firstText(item.skinId, item.skin_id),
      panelGroup: firstText(item.panelGroup, item.panel_group),
    }
    const aliases = [
      id,
      bindingId,
      compatibilityId,
      firstText(item.resourceId, item.resource_id),
      viewModel.sourceBindingToken,
    ].filter(Boolean)
    for (const alias of aliases) {
      if (!result.has(alias)) result.set(alias, viewModel)
      const canonical = canonicalMediaReference(alias)
      if (canonical && !result.has(canonical)) result.set(canonical, viewModel)
    }
  }
  return result
}

function resolveMediaReference(
  mediaById: Map<string, CharacterMediaViewModel>,
  reference: string,
): CharacterMediaViewModel | null {
  if (!reference) return null
  return mediaById.get(reference) ?? mediaById.get(canonicalMediaReference(reference)) ?? null
}

function canonicalMediaReference(reference: string): string {
  let value = reference.trim()
  const crawlerMarker = '/crawler:'
  const crawlerIndex = value.indexOf(crawlerMarker)
  if (crawlerIndex >= 0) value = value.slice(crawlerIndex + crawlerMarker.length)

  const collection = value.match(/^collection_item:(.+)$/i)
  if (collection) return `collection:${collection[1]}`
  const live2d = value.match(/^stage_live2d:([^:]+)$/i)
  if (live2d) return `skin:${live2d[1]}:live2d`
  const portrait = value.match(/^stage_portrait:([^:]+)$/i)
  if (portrait) return `skin:${portrait[1]}:portrait`
  const background = value.match(/^skin_background:([^:]+)$/i)
  if (background) return `skin:${background[1]}:background`
  const skin = value.match(/^skin:([^:]+):(.+)$/i)
  if (skin) {
    const kind = skin[2].toLowerCase()
    if (kind === 'verticaldrawing' || kind === 'drawing') return `skin:${skin[1]}:portrait`
    if (kind === 'live2dbg') return `skin:${skin[1]}:background`
  }
  return value
}

function findSkinMedia(
  mediaById: Map<string, CharacterMediaViewModel>,
  skinId: string,
  role: string,
): CharacterMediaViewModel | null {
  if (!skinId) return null
  return uniqueMediaValues(mediaById).find((item) => item.skinId === skinId && item.role === role) ?? null
}

function uniqueMediaValues(mediaById: Map<string, CharacterMediaViewModel>): CharacterMediaViewModel[] {
  return [...new Map([...mediaById.values()].map((item) => [item.id, item])).values()]
}

function comparableText(value: string): string {
  return value.normalize('NFKC').replace(/[\s·・]/g, '').toLocaleLowerCase()
}

function buildFactMap(blocks: WikiContentBlock[]): Map<string, string> {
  const result = new Map<string, string>()
  for (const contentBlock of blocks) {
    if (contentBlock.type !== 'facts') continue
    for (const item of contentBlock.items ?? []) {
      if (typeof item !== 'string' && item.label.trim() && item.value.trim() && !result.has(item.label.trim())) {
        result.set(item.label.trim(), item.value.trim())
      }
    }
  }
  return result
}

function tableLevels(rows: string[][] | undefined): CharacterSkillLevelViewModel[] {
  return (rows ?? []).slice(1).flatMap((row) => {
    const level = firstText(row[0])
    const effect = row.slice(1).map((item) => item.trim()).filter(Boolean).join(' ')
    return level && effect ? [{ level, effect }] : []
  })
}

function parseVoiceLanguages(text: string, title: string): Omit<CharacterVoiceLanguageViewModel, 'audio'>[] {
  const result: Array<{ code: VoiceCode; label: string; text: string }> = []
  let current: { code: VoiceCode; label: string; lines: string[] } | null = null
  const lines = text.split('\n')
  if (lines[0]?.trim() === title) lines.shift()

  const flush = () => {
    if (!current) return
    const value = current.lines.join('\n').trim()
    if (value) result.push({ code: current.code, label: current.label, text: value })
  }
  for (const line of lines) {
    const match = line.match(/^(中文|繁中|EN|日|韩):\s*(.*)$/)
    if (match) {
      flush()
      const marker = match[1] as LanguageMarker
      current = { ...LANGUAGE_MARKERS[marker], lines: match[2] ? [match[2]] : [] }
    } else if (current) {
      current.lines.push(line)
    }
  }
  flush()
  return result
}

function voiceLanguageFromMedia(media: CharacterMediaViewModel): VoiceCode | null {
  const language = media.language?.toLowerCase()
  if (language === 'zh' || language === 'zh-cn') return 'zh-CN'
  if (language === 'tw' || language === 'zh-tw') return 'zh-TW'
  if (language === 'en') return 'en'
  if (language === 'jp' || language === 'ja') return 'ja'
  if (language === 'kr' || language === 'ko') return 'ko'
  const prefix = media.title.match(/(?:^|:)\s*(Zh|En|Jp|Kr)\b/i)?.[1]?.toLowerCase()
  if (prefix === 'zh') return 'zh-CN'
  if (prefix === 'en') return 'en'
  if (prefix === 'jp') return 'ja'
  if (prefix === 'kr') return 'ko'
  return null
}

function normalizeDamageType(value: string, code: string): { value: string; detail: string } {
  const normalized = value.trim()
  if (!normalized && !code) return { value: '', detail: '' }
  if (/精神|mental/i.test(normalized) || code === '2') {
    return { value: 'Mental', detail: /精神/.test(normalized) ? normalized : '' }
  }
  if (/现实|reality/i.test(normalized) || code === '1') {
    return { value: 'Reality', detail: /现实/.test(normalized) ? normalized : '' }
  }
  return { value: normalized, detail: '' }
}

function normalizeInspiration(value: string): { value: string; detail: string } {
  const parts = value.split(/[｜|]/).map((item) => item.trim()).filter(Boolean)
  if (parts.length >= 2) return { value: parts[1], detail: parts[0] }
  const translated: Record<string, string> = {
    木: 'Plant',
    兽: 'Beast',
    星: 'Star',
    岩: 'Mineral',
    灵: 'Spirit',
    智: 'Intellect',
  }
  return { value: translated[value] ?? value, detail: translated[value] ? value : '' }
}

function firstBlockText(blocks: WikiContentBlock[], section: string): string {
  return firstText(blocks.find((item) => item.section === section && item.text)?.text)
}

function extractLocation(text: string): string {
  const match = text.match(/(?:原参展地点为|原产地为)([^，。]+)[，,]\s*(?:后保藏于|现保藏于)([^，。]+)[。]?/)
  return match ? `${match[1].trim()} / ${match[2].trim()}` : ''
}

function extractActiveEra(text: string): string {
  const match = text.match(/(\d{1,2})世纪(初叶|初期|中叶|中期|末叶|晚期)?/)
  if (!match) return ''
  const century = Number(match[1])
  const remainder = century % 100
  const suffix = remainder >= 11 && remainder <= 13
    ? 'th'
    : century % 10 === 1 ? 'st' : century % 10 === 2 ? 'nd' : century % 10 === 3 ? 'rd' : 'th'
  const period = match[2]?.startsWith('初')
    ? ' Early'
    : match[2]?.startsWith('中') ? ' Mid' : match[2] ? ' Late' : ''
  return `${century}${suffix} Century${period}`
}

function formatArchiveBirthday(value: string, summary: string): string {
  const iso = value.match(/(?:\d{4}-)?(\d{1,2})-(\d{1,2})/)
  const chinese = value.match(/(\d{1,2})月(\d{1,2})日/)
    ?? summary.match(/(?:诞生自|生日[^\d]*)?(\d{1,2})月(\d{1,2})日/)
  const month = Number(iso?.[1] ?? chinese?.[1])
  const day = Number(iso?.[2] ?? chinese?.[2])
  if (!month || !day || month > 12 || day > 31) return value
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const explicitSeason = summary.match(new RegExp(`${month}月${day}日[（(]?([春夏秋冬])`))?.[1]
  const seasonNames: Record<string, string> = { 春: 'Spring', 夏: 'Summer', 秋: 'Autumn', 冬: 'Winter' }
  const season = explicitSeason
    ? seasonNames[explicitSeason]
    : month >= 3 && month <= 5 ? 'Spring' : month <= 8 ? 'Summer' : month <= 11 ? 'Autumn' : 'Winter'
  return `${monthNames[month - 1]} ${day} (${season})`
}

function displayValue(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(displayValue).filter(Boolean).join('\n')
  return ''
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => typeof item === 'string' && item.trim() ? [item.trim()] : [])
    : []
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  }
  return ''
}

function numberValue(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}
