import type { WikiPageListItem } from '../../types/wiki'

const STORAGE_KEY = 'reverse1999.wiki.recent.v1'
const LIMIT = 5

export type RecentWikiPage = Pick<WikiPageListItem, 'pageId' | 'pageType' | 'title' | 'route'>

export function loadRecentWikiPages(storage: Pick<Storage, 'getItem'> = localStorage): RecentWikiPage[] {
  try {
    const value = JSON.parse(storage.getItem(STORAGE_KEY) || '[]')
    if (!Array.isArray(value)) return []
    return value.filter(isRecentWikiPage).slice(0, LIMIT)
  } catch {
    return []
  }
}

export function rememberWikiPage(page: WikiPageListItem, storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage): RecentWikiPage[] {
  const next = [toRecent(page), ...loadRecentWikiPages(storage).filter((item) => item.pageId !== page.pageId)].slice(0, LIMIT)
  storage.setItem(STORAGE_KEY, JSON.stringify(next))
  return next
}

function toRecent(page: WikiPageListItem): RecentWikiPage {
  return { pageId: page.pageId, pageType: page.pageType, title: page.title, route: page.route }
}

function isRecentWikiPage(value: unknown): value is RecentWikiPage {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  return ['pageId', 'pageType', 'title', 'route'].every((key) => typeof item[key] === 'string') && String(item.route).startsWith('/wiki/')
}
