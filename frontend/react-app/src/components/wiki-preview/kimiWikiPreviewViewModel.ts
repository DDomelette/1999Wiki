import type { WikiMediaLink, WikiPageListItem } from '../../types/wiki'
import {
  buildCharacterDetailViewModel,
  type CharacterDetailViewModel,
  type CharacterMediaViewModel,
} from '../wiki/characterDetailViewModel'
import { isPublicHttpUrl, type WikiPageViewModel } from '../wiki/wikiViewModel'

export interface KimiPreviewMedia {
  id: string
  url: string
  title: string
  role: string
  variant: string
}

export interface KimiWikiSelectionEntry {
  pageId: string
  title: string
  subtitle: string
  summary: string
  summaryFacts: Array<{ label: string; value: string }>
  summaryParagraphs: string[]
  canonicalRoute: string
  thumbnail: string
  selected: boolean
}

export interface KimiWikiSelectionViewModel {
  entries: KimiWikiSelectionEntry[]
  selected: (KimiWikiSelectionEntry & {
    portrait: KimiPreviewMedia | null
    backdrop: KimiPreviewMedia | null
  }) | null
}

export interface KimiWikiDetailViewModel {
  character: CharacterDetailViewModel
  backdrop: KimiPreviewMedia | null
}

export interface KimiWikiPreviewViewModel extends KimiWikiSelectionViewModel {
  detail: KimiWikiDetailViewModel | null
}

export function buildKimiWikiPreviewViewModel(
  pages: WikiPageListItem[],
  selectedPageId: string,
  pageViewModel: WikiPageViewModel | null,
): KimiWikiPreviewViewModel {
  const detailMatchesSelection = Boolean(
    pageViewModel
    && (!selectedPageId || pageViewModel.page.pageId === selectedPageId),
  )
  const detail = pageViewModel?.page.pageType === 'character' && detailMatchesSelection
    ? buildKimiDetail(pageViewModel)
    : null

  const sourcePages = pages.length > 0
    ? pages
    : detail ? [detailPageListItem(pageViewModel as WikiPageViewModel)] : []
  const effectiveSelectedId = sourcePages.some((page) => page.pageId === selectedPageId)
    ? selectedPageId
    : detail?.character.identity.pageId ?? sourcePages[0]?.pageId ?? ''
  const entries = sourcePages.map((page) => toSelectionEntry(page, page.pageId === effectiveSelectedId))
  const selectedEntry = entries.find((entry) => entry.selected) ?? null
  const selectedHasDetail = Boolean(
    selectedEntry
    && detail
    && selectedEntry.pageId === detail.character.identity.pageId,
  )

  return {
    entries,
    selected: selectedEntry ? {
      ...selectedEntry,
      portrait: selectedHasDetail ? firstPortrait(detail?.character ?? null) : null,
      backdrop: selectedHasDetail ? detail?.backdrop ?? null : null,
    } : null,
    detail,
  }
}

function buildKimiDetail(pageViewModel: WikiPageViewModel): KimiWikiDetailViewModel {
  return {
    character: buildCharacterDetailViewModel(pageViewModel),
    backdrop: firstBackdrop(pageViewModel.page.mediaLinks),
  }
}

function detailPageListItem(view: WikiPageViewModel): WikiPageListItem {
  const page = view.page
  return {
    pageId: page.pageId,
    pageType: page.pageType,
    title: page.title,
    subtitle: page.subtitle,
    category: page.category,
    route: page.route,
    thumbnail: view.primaryMedia?.url,
    summary: page.summary,
  }
}

function toSelectionEntry(page: WikiPageListItem, selected: boolean): KimiWikiSelectionEntry {
  const structuredSummary = parseSelectionSummary(page.summary ?? '')
  return {
    pageId: page.pageId,
    title: page.title,
    subtitle: page.subtitle,
    summary: page.summary ?? '',
    summaryFacts: structuredSummary.facts,
    summaryParagraphs: structuredSummary.paragraphs,
    canonicalRoute: canonicalRoute(page.route),
    thumbnail: isPublicHttpUrl(page.thumbnail) ? page.thumbnail : '',
    selected,
  }
}

export function parseSelectionSummary(summary: string): {
  facts: Array<{ label: string; value: string }>
  paragraphs: string[]
} {
  const facts: Array<{ label: string; value: string }> = []
  const prose: string[] = []
  const lines = summary.replace(/\r\n?/g, '\n').split(/\n+/).map((line) => line.trim()).filter(Boolean)

  for (const line of lines) {
    if (/(?:角色资料|character profile)\s*$/i.test(line)) continue
    const match = line.match(/^([^:：]{1,28})\s*[:：]\s*(.+)$/)
    if (match) {
      facts.push({ label: match[1].trim(), value: match[2].trim() })
    } else {
      prose.push(line)
    }
  }

  const paragraphs = prose.flatMap((line) => {
    const sentences = line.match(/[^。！？!?.]+[。！？!?.]?/g) ?? []
    return sentences.map((sentence) => sentence.trim()).filter(Boolean)
  })
  return { facts, paragraphs }
}

function canonicalRoute(route: string): string {
  return route.replace(/^\/wiki-preview(?=\/|$)/, '/wiki')
}

function firstPortrait(character: CharacterDetailViewModel | null): KimiPreviewMedia | null {
  if (!character) return null
  const state = character.portraitStates.find((item) => item.variant === 'initial')
    ?? character.portraitStates[0]
  const media = state ? (state.portraitMedia ?? state.live2dMedia) : null
  return media ? fromCharacterMedia(media) : null
}

function firstBackdrop(items: WikiMediaLink[]): KimiPreviewMedia | null {
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index]
    if (!hasBackdropRole(item)) continue
    const media = fromWikiMedia(item, index)
    if (media) return media
  }
  return null
}

function hasBackdropRole(item: WikiMediaLink): boolean {
  const role = firstText(item.role).toLowerCase()
  const section = firstText(item.sectionKey, item.section_key).toLowerCase()
  return ['backdrop', 'background', 'scene', 'character_background', 'stage_background'].includes(role)
    || ['backdrop', 'background', 'scene', 'stage'].includes(section)
}

function fromCharacterMedia(item: CharacterMediaViewModel): KimiPreviewMedia | null {
  if (!isPublicHttpUrl(item.url)) return null
  return {
    id: item.id,
    url: item.url,
    title: item.title,
    role: item.role,
    variant: item.variant,
  }
}

function fromWikiMedia(item: WikiMediaLink, index: number): KimiPreviewMedia | null {
  if (!isPublicHttpUrl(item.url)) return null
  return {
    id: firstText(item.mediaId, item.assetId, `media-${index + 1}`),
    url: item.url,
    title: firstText(item.title, item.alt, `媒体 ${index + 1}`),
    role: firstText(item.role, item.assetType),
    variant: firstText(item.variant),
  }
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  }
  return ''
}
