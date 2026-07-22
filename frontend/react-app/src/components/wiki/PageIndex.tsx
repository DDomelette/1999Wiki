import { useEffect, useRef, useState, type UIEventHandler } from 'react'
import { ChevronDown, FileImage, RotateCcw } from 'lucide-react'
import type { WikiIndexItemViewModel } from './wikiViewModel'
import './PageIndex.css'

interface PageIndexProps {
  pages: WikiIndexItemViewModel[]
  selectedPageId: string
  query: string
  activeCategoryLabel: string
  loading: boolean
  loadingMore: boolean
  error: string
  loadedCount: number
  totalCount: number
  hasMore: boolean
  restoreScrollTop: number
  onQueryChange(query: string): void
  onSelect(pageId: string): void
  onScrollTopChange(scrollTop: number): void
  onLoadMore(): void
  onRetry(): void
}

export function PageIndex({
  pages,
  selectedPageId,
  query,
  activeCategoryLabel,
  loading,
  loadingMore,
  error,
  loadedCount,
  totalCount,
  hasMore,
  restoreScrollTop,
  onQueryChange,
  onSelect,
  onScrollTopChange,
  onLoadMore,
  onRetry,
}: PageIndexProps) {
  const rootRef = useRef<HTMLElement>(null)
  const frameRef = useRef<number | null>(null)
  const pendingScrollTopRef = useRef(restoreScrollTop)

  useEffect(() => {
    const root = rootRef.current
    if (root) root.scrollTop = restoreScrollTop
  }, [restoreScrollTop])

  useEffect(() => () => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
  }, [])

  const handleScroll: UIEventHandler<HTMLElement> = (event) => {
    pendingScrollTopRef.current = event.currentTarget.scrollTop
    if (frameRef.current !== null) return

    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null
      onScrollTopChange(pendingScrollTopRef.current)
    })
  }

  return (
    <section
      ref={rootRef}
      data-testid="wiki-page-index"
      className="wiki-page-index native-scrollbar-hidden"
      onScroll={handleScroll}
    >
      <header className="wiki-page-index__header">
        <div>
          <span className="archive-kicker">ARCHIVE INDEX</span>
          <h2>{activeCategoryLabel || '全部档案'}</h2>
        </div>
        <span className="wiki-page-index__count" aria-label={`已载入 ${loadedCount}，共 ${totalCount}`}>
          {String(loadedCount).padStart(2, '0')}
        </span>
      </header>

      <label className="wiki-page-index__search">
        <span className="sr-only">搜索页面</span>
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="搜索页面"
          aria-label="搜索页面"
          type="search"
        />
      </label>

      {error ? (
        <div className="wiki-page-index__status wiki-page-index__status--error" role="status">
          <span>条目列表暂不可用：{error}</span>
          <button type="button" aria-label="重试条目列表" onClick={onRetry}>
            <RotateCcw aria-hidden="true" />
            <span>重试</span>
          </button>
        </div>
      ) : null}

      {loading && pages.length === 0 ? (
        <p className="wiki-page-index__status">正在读取档案索引...</p>
      ) : null}

      {!loading && !error && pages.length === 0 ? (
        <p className="wiki-page-index__status">暂无匹配档案</p>
      ) : null}

      <div className="wiki-index-list">
        {pages.map((page) => (
          <button
            key={page.pageId}
            type="button"
            aria-label={page.title}
            aria-pressed={selectedPageId === page.pageId}
            onClick={() => onSelect(page.pageId)}
            className="wiki-index-item"
          >
            <WikiIndexThumbnail src={page.thumbnail} />
            <strong>{page.title}</strong>
            <span className="archive-meta">{page.meta}</span>
          </button>
        ))}
      </div>

      <footer className="wiki-page-index__footer">
        <span>已载入 {loadedCount} / {totalCount}</span>
        {hasMore ? (
          <button
            type="button"
            aria-label={loadingMore ? '正在加载更多档案' : '加载更多档案'}
            disabled={loadingMore}
            onClick={onLoadMore}
          >
            <ChevronDown aria-hidden="true" />
            <span>{loadingMore ? '正在加载...' : '加载更多'}</span>
          </button>
        ) : null}
      </footer>
    </section>
  )
}

function WikiIndexThumbnail({ src }: { src: string }) {
  const [failed, setFailed] = useState(false)

  useEffect(() => setFailed(false), [src])

  return (
    <span className="wiki-index-item__media" aria-hidden="true">
      {src && !failed ? (
        <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} />
      ) : (
        <span className="wiki-index-item__placeholder" data-testid="wiki-index-placeholder">
          <FileImage aria-hidden="true" />
        </span>
      )}
    </span>
  )
}
