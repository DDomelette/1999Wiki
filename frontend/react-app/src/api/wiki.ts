import type {
  WikiCategoryItem,
  WikiPageDetail,
  WikiPageListResponse,
  WikiRouteResolveResponse,
  WikiHealthResponse,
} from '../types/wiki'

export class WikiApiError extends Error {
  constructor(readonly status: number, readonly url: string) {
    super(`HTTP ${status}`)
    this.name = 'WikiApiError'
  }
}

export async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new WikiApiError(res.status, url)
  return res.json() as Promise<T>
}

export async function fetchWikiHealth(): Promise<WikiHealthResponse> {
  return fetchJson<WikiHealthResponse>('/api/wiki/health')
}

export async function fetchWikiCategories(): Promise<WikiCategoryItem[]> {
  const data = await fetchJson<{ categories: WikiCategoryItem[] }>('/api/wiki/categories')
  return data.categories
}

export async function fetchWikiPages(params: {
  category?: string
  q?: string
  type?: string
  limit?: number
  cursor?: string
} = {}): Promise<WikiPageListResponse> {
  const search = new URLSearchParams()
  if (params.category) search.set('category', params.category)
  if (params.q) search.set('q', params.q)
  if (params.type) search.set('type', params.type)
  if (params.limit) search.set('limit', String(params.limit))
  if (params.cursor) search.set('cursor', params.cursor)
  const suffix = search.toString()
  return fetchJson<WikiPageListResponse>(`/api/wiki/pages${suffix ? `?${suffix}` : ''}`)
}

export async function fetchWikiPage(pageId: string): Promise<WikiPageDetail> {
  return fetchJson<WikiPageDetail>(`/api/wiki/pages/${encodeURIComponent(pageId)}`)
}

export async function fetchWikiPageByRoute(route: string): Promise<WikiPageDetail> {
  const search = new URLSearchParams()
  search.set('route', route)
  return fetchJson<WikiPageDetail>(`/api/wiki/pages/by-route?${search.toString()}`)
}

export async function resolveWikiRoute(params: {
  sourceId?: string
  entityId?: string
  title?: string
}): Promise<WikiRouteResolveResponse> {
  const search = new URLSearchParams()
  if (params.sourceId) search.set('source_id', params.sourceId)
  if (params.entityId) search.set('entity_id', params.entityId)
  if (params.title) search.set('title', params.title)
  return fetchJson<WikiRouteResolveResponse>(`/api/wiki/routes/resolve?${search.toString()}`)
}
