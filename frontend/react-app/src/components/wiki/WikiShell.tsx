import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  WikiApiError,
  fetchWikiCategories,
  fetchWikiHealth,
  fetchWikiPage,
  fetchWikiPageByRoute,
  fetchWikiPages,
  resolveWikiRoute,
} from '../../api/wiki'
import type { WikiCategoryItem, WikiHealthResponse, WikiPageDetail, WikiPageListItem } from '../../types/wiki'
import { RouteAwareCardNav } from '../navigation/RouteAwareCardNav'
import { loadRecentWikiPages, rememberWikiPage } from '../navigation/recentWiki'
import { KimiWikiCharacterDetailPage } from '../wiki-preview/KimiWikiCharacterDetailPage'
import { KimiWikiCharacterSelectionPage } from '../wiki-preview/KimiWikiCharacterSelectionPage'
import { buildKimiWikiPreviewViewModel } from '../wiki-preview/kimiWikiPreviewViewModel'
import { PageIndex } from './PageIndex'
import { PageInfo } from './PageInfo'
import { StructuredContentRenderer } from './StructuredContentRenderer'
import { WikiCharacterDetailPage } from './WikiCharacterDetailPage'
import { WikiCharacterSelectionPage } from './WikiCharacterSelectionPage'
import { WikiErrorBoundary } from './WikiErrorBoundary'
import { WikiReaderHero } from './WikiReader'
import { buildCharacterDetailViewModel } from './characterDetailViewModel'
import { buildWikiIndexItem, buildWikiPageViewModel } from './wikiViewModel'
import {
  parseWikiLocation,
  pushWikiDetail,
  readWikiSelectionState,
  replaceWikiLocation,
  toCanonicalWikiRoute,
  toVisibleWikiRoute,
  type WikiLocation,
  type WikiRouteBase,
  type WikiSelectionHistoryState,
} from './wikiRoutes'

function messageFor(error: unknown): string {
  if (error instanceof WikiApiError) return `HTTP ${error.status}`
  if (error instanceof Error) return error.message
  return '未知错误'
}

function appendUniquePages(current: WikiPageListItem[], incoming: WikiPageListItem[]): WikiPageListItem[] {
  const seen = new Set(current.map((page) => page.pageId))
  return [...current, ...incoming.filter((page) => !seen.has(page.pageId) && seen.add(page.pageId))]
}

export type WikiShellVariant = 'current' | 'kimi-preview'

interface WikiShellProps {
  variant?: WikiShellVariant
}

export function WikiShell({ variant = 'current' }: WikiShellProps) {
  const basePath: WikiRouteBase = variant === 'kimi-preview' ? '/wiki-preview' : '/wiki'
  const selectionRoute = `${basePath}/character`
  const restoredSelection = useMemo(() => readWikiSelectionState(window.history.state), [])
  const [location, setLocation] = useState<WikiLocation>(() => parseWikiLocation(window.location.pathname, basePath))
  const [categories, setCategories] = useState<WikiCategoryItem[]>([])
  const [pages, setPages] = useState<WikiPageListItem[]>([])
  const [activeCategory, setActiveCategory] = useState(restoredSelection?.category || 'character')
  const [query, setQuery] = useState(restoredSelection?.query || '')
  const [selectedPageId, setSelectedPageId] = useState(restoredSelection?.selectedPageId || '')
  const [selectedPage, setSelectedPage] = useState<WikiPageDetail | null>(null)
  const [categoryError, setCategoryError] = useState('')
  const [categoryRetryEpoch, setCategoryRetryEpoch] = useState(0)
  const [listError, setListError] = useState('')
  const [listCursor, setListCursor] = useState<string | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [listLoadingMore, setListLoadingMore] = useState(false)
  const [listRetryEpoch, setListRetryEpoch] = useState(0)
  const [previewError, setPreviewError] = useState('')
  const [previewRetryEpoch, setPreviewRetryEpoch] = useState(0)
  const [detailError, setDetailError] = useState('')
  const [detailRetryEpoch, setDetailRetryEpoch] = useState(0)
  const [detailLoading, setDetailLoading] = useState(false)
  const [previewHealth, setPreviewHealth] = useState<WikiHealthResponse | null>(null)
  const [previewHealthError, setPreviewHealthError] = useState('')
  const [healthRetryEpoch, setHealthRetryEpoch] = useState(0)
  const [listScrollTop, setListScrollTop] = useState(restoredSelection?.listScrollTop || 0)
  const [recentPages, setRecentPages] = useState(loadRecentWikiPages)
  const categoryRequestRef = useRef(0)
  const listGenerationRef = useRef(0)
  const previewRequestRef = useRef(0)
  const detailRequestRef = useRef(0)
  const healthRequestRef = useRef(0)
  const locationKey = location.kind === 'detail' ? `detail:${location.route}` : location.kind
  const previousLocationKeyRef = useRef(locationKey)

  useEffect(() => {
    if (variant !== 'kimi-preview') return
    const requestId = ++healthRequestRef.current
    fetchWikiHealth()
      .then((health) => {
        if (requestId !== healthRequestRef.current) return
        setPreviewHealth(health)
        setPreviewHealthError('')
      })
      .catch((error: unknown) => {
        if (requestId !== healthRequestRef.current) return
        setPreviewHealth(null)
        setPreviewHealthError(messageFor(error))
      })
  }, [healthRetryEpoch, variant])

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'auto'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [])

  useEffect(() => {
    if (previousLocationKeyRef.current === locationKey) return
    previousLocationKeyRef.current = locationKey
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [locationKey])

  useEffect(() => {
    if (window.location.pathname.replace(/\/+$/, '') === basePath) {
      replaceWikiLocation(selectionRoute, window.history.state)
    }
  }, [basePath, selectionRoute])

  useEffect(() => {
    const handlePopState = (event: PopStateEvent) => {
      const nextLocation = parseWikiLocation(window.location.pathname, basePath)
      const selection = readWikiSelectionState(event.state)
      if (selection && nextLocation.kind === 'character-selection') {
        setActiveCategory(selection.category)
        setQuery(selection.query)
        setSelectedPageId(selection.selectedPageId)
        setListScrollTop(selection.listScrollTop)
      }
      setLocation(nextLocation)
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [basePath])

  useEffect(() => {
    if (location.kind !== 'character-selection') return
    const requestId = ++categoryRequestRef.current
    fetchWikiCategories()
      .then((items) => {
        if (requestId !== categoryRequestRef.current) return
        setCategories(items)
        setCategoryError('')
      })
      .catch((error: unknown) => {
        if (requestId === categoryRequestRef.current) setCategoryError(messageFor(error))
      })
  }, [categoryRetryEpoch, location.kind])

  useEffect(() => {
    if (location.kind !== 'character-selection') return
    const generation = ++listGenerationRef.current
    setPages([])
    setListCursor(null)
    setListError('')
    setListLoading(true)
    setListLoadingMore(false)
    fetchWikiPages({ category: activeCategory, q: query, limit: 30 })
      .then((data) => {
        if (generation !== listGenerationRef.current) return
        setPages(data.items)
        setListCursor(data.nextCursor ?? null)
        setSelectedPageId((current) => (
          current && data.items.some((page) => page.pageId === current)
            ? current
            : data.items[0]?.pageId ?? ''
        ))
      })
      .catch((error: unknown) => {
        if (generation === listGenerationRef.current) setListError(messageFor(error))
      })
      .finally(() => {
        if (generation === listGenerationRef.current) setListLoading(false)
      })
  }, [activeCategory, listRetryEpoch, location.kind, query])

  const loadMore = useCallback(() => {
    if (location.kind !== 'character-selection' || !listCursor || listLoadingMore) return
    const generation = listGenerationRef.current
    const cursor = listCursor
    setListLoadingMore(true)
    fetchWikiPages({ category: activeCategory, q: query, limit: 30, cursor })
      .then((data) => {
        if (generation !== listGenerationRef.current) return
        setPages((current) => appendUniquePages(current, data.items))
        setListCursor(data.nextCursor ?? null)
        setListError('')
      })
      .catch((error: unknown) => {
        if (generation === listGenerationRef.current) setListError(messageFor(error))
      })
      .finally(() => {
        if (generation === listGenerationRef.current) setListLoadingMore(false)
      })
  }, [activeCategory, listCursor, listLoadingMore, location.kind, query])

  const retryList = useCallback(() => {
    if (pages.length > 0 && listCursor) {
      loadMore()
      return
    }
    setListRetryEpoch((current) => current + 1)
  }, [listCursor, loadMore, pages.length])

  useEffect(() => {
    if (location.kind !== 'character-selection') return
    const requestId = ++previewRequestRef.current
    if (!selectedPageId) {
      setSelectedPage(null)
      setPreviewError('')
      return
    }
    setSelectedPage(null)
    setDetailLoading(true)
    setPreviewError('')
    fetchWikiPage(selectedPageId)
      .then((page) => {
        if (requestId !== previewRequestRef.current) return
        setSelectedPage(page)
        setRecentPages(rememberWikiPage(page))
      })
      .catch((error: unknown) => {
        if (requestId === previewRequestRef.current) setPreviewError(messageFor(error))
      })
      .finally(() => {
        if (requestId === previewRequestRef.current) setDetailLoading(false)
      })
  }, [location.kind, previewRetryEpoch, selectedPageId])

  useEffect(() => {
    if (location.kind !== 'detail') return
    const requestId = ++detailRequestRef.current
    setSelectedPage(null)
    setDetailLoading(true)
    setDetailError('')

    const acceptPage = (page: WikiPageDetail) => {
      if (requestId !== detailRequestRef.current) return
      setSelectedPage(page)
      setSelectedPageId(page.pageId)
      setRecentPages(rememberWikiPage(page))
      const visibleRoute = page.route ? toVisibleWikiRoute(page.route, basePath) : ''
      if (visibleRoute && visibleRoute !== window.location.pathname) {
        replaceWikiLocation(visibleRoute, window.history.state)
      }
    }

    const load = async () => {
      try {
        acceptPage(await fetchWikiPageByRoute(toCanonicalWikiRoute(location.route, basePath)))
        return
      } catch (error) {
        if (!(error instanceof WikiApiError) || error.status !== 404 || !location.resolverHint) throw error
      }

      const hint = location.resolverHint
      let resolved = await resolveWikiRoute({ entityId: hint })
      if (!resolved.route && !/^\d+$/.test(hint)) {
        resolved = await resolveWikiRoute({ title: hint })
      }
      if (!resolved.route) throw new WikiApiError(404, location.route)
      const canonicalRoute = toCanonicalWikiRoute(resolved.route, basePath)
      replaceWikiLocation(toVisibleWikiRoute(canonicalRoute, basePath), window.history.state)
      acceptPage(await fetchWikiPageByRoute(canonicalRoute))
    }

    load()
      .catch((error: unknown) => {
        if (requestId === detailRequestRef.current) setDetailError(messageFor(error))
      })
      .finally(() => {
        if (requestId === detailRequestRef.current) setDetailLoading(false)
      })
  }, [basePath, detailRetryEpoch, location])

  useEffect(() => {
    if (location.kind !== 'character-selection') return
    const selection: WikiSelectionHistoryState = {
      category: activeCategory,
      query,
      selectedPageId,
      listScrollTop,
    }
    replaceWikiLocation(selectionRoute, { wikiSelection: selection })
  }, [activeCategory, listScrollTop, location.kind, query, selectedPageId, selectionRoute])

  const activeCategoryLabel = useMemo(() => {
    if (location.kind === 'detail') return selectedPage?.category || 'Wiki'
    if (!activeCategory) return 'Wiki'
    return categories.find((item) => item.key === activeCategory)?.label ?? activeCategory
  }, [activeCategory, categories, location.kind, selectedPage])

  const activeCategoryMeta = useMemo(
    () => categories.find((item) => item.key === activeCategory),
    [activeCategory, categories],
  )
  const selectedListItem = useMemo(
    () => pages.find((page) => page.pageId === selectedPageId) ?? null,
    [pages, selectedPageId],
  )
  const indexPages = useMemo(
    () => pages.map(buildWikiIndexItem),
    [pages],
  )
  const pageViewModel = useMemo(
    () => selectedPage ? buildWikiPageViewModel(selectedPage) : null,
    [selectedPage],
  )
  const characterDetailViewModel = useMemo(
    () => pageViewModel?.page.pageType === 'character'
      ? buildCharacterDetailViewModel(pageViewModel)
      : null,
    [pageViewModel],
  )
  const kimiPreviewViewModel = useMemo(
    () => buildKimiWikiPreviewViewModel(pages, selectedPageId, pageViewModel),
    [pageViewModel, pages, selectedPageId],
  )
  const availableAnchors = useMemo(() => {
    const anchors = new Set<'content' | 'media' | 'info'>()
    if (selectedPage) {
      anchors.add('content')
      anchors.add('info')
      if ((selectedPage.mediaLinks ?? []).length > 0) anchors.add('media')
    }
    return anchors
  }, [selectedPage])

  // 大舞台只展示正式立绘；切换角色时保留上一张立绘，避免回退到列表缩略头像造成"闪现大头像"
  const lastPortraitUrlRef = useRef('')
  const stagePortraitUrl = pageViewModel?.primaryMedia?.url || ''
  useEffect(() => {
    if (stagePortraitUrl) lastPortraitUrlRef.current = stagePortraitUrl
  }, [stagePortraitUrl])
  const stageImageUrl = stagePortraitUrl || lastPortraitUrlRef.current

  const openSelectedDetail = () => {
    const selected = pages.find((page) => page.pageId === selectedPageId)
    if (!selected?.route) return
    const visibleRoute = toVisibleWikiRoute(selected.route, basePath)
    const selection: WikiSelectionHistoryState = {
      category: activeCategory,
      query,
      selectedPageId,
      listScrollTop,
    }
    pushWikiDetail(visibleRoute, selection)
    setLocation(parseWikiLocation(visibleRoute, basePath))
  }

  const returnToSelection = () => {
    if (readWikiSelectionState(window.history.state)) {
      window.history.back()
      return
    }
    replaceWikiLocation(selectionRoute, { wikiSelection: {
      category: 'character',
      query: '',
      selectedPageId: '',
      listScrollTop: 0,
    } })
    setLocation({ kind: 'character-selection' })
  }

  const readerError = location.kind === 'detail' ? detailError : previewError

  return (
    <main
      className={`wiki-shell wiki-shell--${location.kind === 'detail' ? 'detail' : 'selection'} wiki-shell--${variant}`}
      data-wiki-variant={variant}
      data-testid="wiki-shell"
      style={{
        minHeight: '100vh',
        background: 'color-mix(in srgb, var(--bg-base) 82%, transparent)',
        color: 'var(--text-primary)',
        fontFamily: 'var(--font-body)',
        padding: location.kind === 'detail' || variant === 'kimi-preview' ? 0 : '24px 20px',
        overflow: 'visible',
      }}
    >
      <RouteAwareCardNav
        mode="wiki"
        categories={location.kind === 'character-selection' ? categories : []}
        activeCategory={activeCategory}
        onCategorySelect={setActiveCategory}
        availableAnchors={availableAnchors}
        pageType={selectedPage?.pageType}
        recentPages={recentPages}
        onBack={location.kind === 'detail' ? returnToSelection : undefined}
      />
      {variant === 'kimi-preview' && (previewHealthError || previewHealth?.stale) ? (
        <aside className="kimi-wiki-diagnostic" role="status">
          <strong>
            {previewHealthError
              ? 'WIKI HEALTH UNAVAILABLE'
              : 'WIKI SNAPSHOT STALE'}
          </strong>
          <span>{previewHealthError || '页面继续使用当前爬虫快照，数据可能不是最新版本。'}</span>
          {previewHealthError ? (
            <button
              type="button"
              aria-label="重试 Wiki 健康检查"
              onClick={() => setHealthRetryEpoch((current) => current + 1)}
            >
              重试健康检查
            </button>
          ) : null}
        </aside>
      ) : null}
      {categoryError && location.kind === 'character-selection' ? (
        variant === 'kimi-preview' ? (
          <div className="kimi-wiki-category-failure" role="status">
            <span>分类入口暂不可用：{categoryError}</span>
            <button
              type="button"
              aria-label="重试 Wiki 分类"
              onClick={() => setCategoryRetryEpoch((current) => current + 1)}
            >
              重试分类
            </button>
          </div>
        ) : <p role="status">分类暂不可用：{categoryError}</p>
      ) : null}
      {location.kind === 'character-selection' ? (
        variant === 'kimi-preview' ? (
          <WikiErrorBoundary
            resetKey={`kimi-selection:${selectedPageId}`}
            fallback={<p>当前角色预览无法渲染</p>}
          >
            <KimiWikiCharacterSelectionPage
              model={kimiPreviewViewModel}
              query={query}
              activeCategoryLabel={activeCategoryLabel}
              loading={listLoading}
              loadingMore={listLoadingMore}
              error={listError}
              previewError={previewError}
              loadedCount={pages.length}
              totalCount={activeCategoryMeta?.count ?? pages.length}
              hasMore={Boolean(listCursor)}
              restoreScrollTop={listScrollTop}
              canOpenDetail={Boolean(selectedListItem?.route)}
              onQueryChange={setQuery}
              onSelect={setSelectedPageId}
              onScrollTopChange={setListScrollTop}
              onLoadMore={loadMore}
              onRetry={retryList}
              onRetryPreview={() => setPreviewRetryEpoch((current) => current + 1)}
              onOpenDetail={openSelectedDetail}
            />
          </WikiErrorBoundary>
        ) : (
          <WikiCharacterSelectionPage
          activeCategory={activeCategory}
          templateGroup={activeCategoryMeta?.templateGroup}
          animationProfile={activeCategoryMeta?.animationProfile}
          themeToken={activeCategoryMeta?.themeToken}
          canOpenDetail={Boolean(selectedListItem?.route)}
          onOpenDetail={openSelectedDetail}
          index={(
            <PageIndex
              pages={indexPages}
              selectedPageId={selectedPageId}
              query={query}
              activeCategoryLabel={activeCategoryLabel}
              loading={listLoading}
              loadingMore={listLoadingMore}
              error={listError}
              loadedCount={pages.length}
              totalCount={activeCategoryMeta?.count ?? pages.length}
              hasMore={Boolean(listCursor)}
              restoreScrollTop={listScrollTop}
              onQueryChange={setQuery}
              onSelect={setSelectedPageId}
              onScrollTopChange={setListScrollTop}
              onLoadMore={loadMore}
              onRetry={retryList}
            />
          )}
          preview={(
            <WikiErrorBoundary
              resetKey={`preview:${selectedPageId}`}
              fallback={<p>当前角色预览无法渲染</p>}
            >
              <div className="wiki-selection-preview">
                {detailLoading ? <p>加载中...</p> : null}
                {readerError ? <p role="status">Wiki 数据暂不可用：{readerError}</p> : null}
                {stageImageUrl ? (
                  <img
                    src={stageImageUrl}
                    alt={selectedPage?.title || selectedListItem?.title || ''}
                  />
                ) : null}
                <div>
                  <h1>{selectedPage?.title || selectedListItem?.title || '请选择角色'}</h1>
                  <p>{selectedPage?.subtitle || selectedListItem?.subtitle || ''}</p>
                </div>
              </div>
            </WikiErrorBoundary>
          )}
          summary={(
            <div>
              <p className="archive-kicker">Personnel Preview</p>
              <h2>{selectedListItem?.title || '未选择角色'}</h2>
              <p className="wiki-selection-summary__text">{selectedListItem?.summary || '从左侧档案索引选择角色。'}</p>
            </div>
          )}
          />
        )
      ) : (
        <WikiErrorBoundary
          resetKey={`detail:${selectedPageId}`}
          fallback={<p>当前 Wiki 内容无法渲染</p>}
        >
          {detailLoading && !pageViewModel ? <p role="status">正在加载 Wiki 档案...</p> : null}
          {detailError ? (
            variant === 'kimi-preview' ? (
              <div className="kimi-wiki-detail-failure" role="status">
                <p>
                  {detailError === 'HTTP 404'
                    ? '未找到对应 Wiki 档案（HTTP 404）'
                    : `Wiki 详情服务暂不可用（${detailError}）`}
                </p>
                {detailError === 'HTTP 404' ? (
                  <button type="button" aria-label="返回角色索引" onClick={returnToSelection}>返回角色索引</button>
                ) : (
                  <button
                    type="button"
                    aria-label="重试 Wiki 详情"
                    onClick={() => setDetailRetryEpoch((current) => current + 1)}
                  >
                    重试 Wiki 详情
                  </button>
                )}
              </div>
            ) : <p role="status">Wiki 数据暂不可用：{detailError}</p>
          ) : null}
          {!detailLoading && !detailError && characterDetailViewModel ? (
            variant === 'kimi-preview' && kimiPreviewViewModel.detail ? (
              <KimiWikiCharacterDetailPage
                model={kimiPreviewViewModel.detail}
                onBack={returnToSelection}
              />
            ) : (
              <WikiCharacterDetailPage
                viewModel={characterDetailViewModel}
                onBack={returnToSelection}
              />
            )
          ) : null}
          {!detailLoading && !detailError && pageViewModel && !characterDetailViewModel ? (
            <article className="wiki-generic-detail" data-testid="wiki-generic-detail">
              <WikiReaderHero view={pageViewModel} loading={false} error="" />
              <StructuredContentRenderer
                blocks={pageViewModel.blocks}
                linkSpans={selectedPage?.linkSpans}
                pageType={selectedPage?.pageType}
              />
              <PageInfo view={pageViewModel} />
            </article>
          ) : null}
        </WikiErrorBoundary>
      )}
    </main>
  )
}
