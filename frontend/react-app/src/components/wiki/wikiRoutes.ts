export type WikiLocation =
  | { kind: 'character-selection' }
  | { kind: 'detail'; route: string; resolverHint?: string }

export interface WikiSelectionHistoryState {
  category: string
  query: string
  selectedPageId: string
  listScrollTop: number
}

interface WikiHistoryEnvelope {
  wikiSelection: WikiSelectionHistoryState
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function parseWikiLocation(pathname: string): WikiLocation {
  const basePath = '/wiki'
  const normalized = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  if (normalized === basePath || normalized === `${basePath}/character`) {
    return { kind: 'character-selection' }
  }
  const characterMatch = normalized.match(new RegExp(`^${escapeRegExp(basePath)}/character/([^/]+)$`))
  if (characterMatch) {
    return {
      kind: 'detail',
      route: normalized,
      resolverHint: decodeURIComponent(characterMatch[1]),
    }
  }
  return { kind: 'detail', route: normalized }
}

export function replaceWikiLocation(route: string, state: unknown = window.history.state): void {
  window.history.replaceState(state, '', route)
}

export function pushWikiDetail(route: string, selection: WikiSelectionHistoryState): void {
  const state: WikiHistoryEnvelope = { wikiSelection: selection }
  window.history.pushState(state, '', route)
}

export function readWikiSelectionState(state: unknown): WikiSelectionHistoryState | null {
  if (!state || typeof state !== 'object') return null
  const candidate = (state as { wikiSelection?: unknown }).wikiSelection
  if (!candidate || typeof candidate !== 'object') return null
  const value = candidate as Partial<WikiSelectionHistoryState>
  if (
    typeof value.category !== 'string'
    || typeof value.query !== 'string'
    || typeof value.selectedPageId !== 'string'
    || typeof value.listScrollTop !== 'number'
    || !Number.isFinite(value.listScrollTop)
    || value.listScrollTop < 0
  ) return null
  return {
    category: value.category,
    query: value.query,
    selectedPageId: value.selectedPageId,
    listScrollTop: value.listScrollTop,
  }
}
