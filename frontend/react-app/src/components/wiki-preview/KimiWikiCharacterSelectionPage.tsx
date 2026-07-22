import { useEffect, useRef, useState, type UIEventHandler } from 'react'
import {
  Archive,
  BrainCircuit,
  ChevronDown,
  Database,
  FolderOpen,
  ImageOff,
  RotateCcw,
  Search,
  Shirt,
  Sparkles,
} from 'lucide-react'
import type { KimiPreviewMedia, KimiWikiPreviewViewModel } from './kimiWikiPreviewViewModel'
import './KimiWikiPreview.css'

export interface KimiWikiCharacterSelectionPageProps {
  model: KimiWikiPreviewViewModel
  query: string
  activeCategoryLabel: string
  loading: boolean
  loadingMore: boolean
  error: string
  previewError: string
  loadedCount: number
  totalCount: number
  hasMore: boolean
  restoreScrollTop: number
  canOpenDetail: boolean
  onQueryChange(query: string): void
  onSelect(pageId: string): void
  onScrollTopChange(scrollTop: number): void
  onLoadMore(): void
  onRetry(): void
  onRetryPreview(): void
  onOpenDetail(): void
}

const ARCHIVE_SECTIONS = [
  { label: 'DOSSIER', icon: FolderOpen, active: true },
  { label: 'PSYCHUBE', icon: BrainCircuit, active: false },
  { label: 'INSIGHT', icon: Sparkles, active: false },
  { label: 'RESONATE', icon: Archive, active: false },
  { label: 'WARDROBE', icon: Shirt, active: false },
] as const

export function KimiWikiCharacterSelectionPage({
  model,
  query,
  activeCategoryLabel,
  loading,
  loadingMore,
  error,
  previewError,
  loadedCount,
  totalCount,
  hasMore,
  restoreScrollTop,
  canOpenDetail,
  onQueryChange,
  onSelect,
  onScrollTopChange,
  onLoadMore,
  onRetry,
  onRetryPreview,
  onOpenDetail,
}: KimiWikiCharacterSelectionPageProps) {
  const rosterRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<number | null>(null)
  const pendingScrollTopRef = useRef(restoreScrollTop)

  useEffect(() => {
    if (rosterRef.current) rosterRef.current.scrollTop = restoreScrollTop
  }, [restoreScrollTop])

  useEffect(() => () => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
  }, [])

  const handleRosterScroll: UIEventHandler<HTMLDivElement> = (event) => {
    pendingScrollTopRef.current = event.currentTarget.scrollTop
    if (frameRef.current !== null) return
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null
      onScrollTopChange(pendingScrollTopRef.current)
    })
  }

  return (
    <section className="kimi-wiki-selection" data-testid="wiki-character-selection-preview">
      <aside className="kimi-wiki-selection__rail" aria-label="角色档案工作区">
        <header>
          <p>STRATEGIST_01</p>
          <span>SESSION_ID: 1999-077</span>
        </header>
        <nav aria-label="角色档案分区">
          {ARCHIVE_SECTIONS.map(({ label, icon: Icon, active }) => (
            <div key={label} className={active ? 'is-active' : ''} aria-current={active ? 'page' : undefined}>
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </div>
          ))}
        </nav>
        <footer>
          <span><Archive aria-hidden="true" /> ARCHIVE</span>
          <span><Database aria-hidden="true" /> DATABASE</span>
          <strong>DEPLOY UNIT</strong>
        </footer>
      </aside>

      <aside className="kimi-wiki-selection__index" aria-label="角色索引">
        <header className="kimi-wiki-selection__index-header">
          <div>
            <span>ARCHIVE INDEX</span>
            <h1>{activeCategoryLabel || '角色'}</h1>
          </div>
          <strong>{totalCount}</strong>
        </header>
        <label className="kimi-wiki-selection__search">
          <Search aria-hidden="true" />
          <span className="sr-only">搜索页面</span>
          <input
            aria-label="搜索页面"
            type="search"
            value={query}
            placeholder="搜索页面"
            onChange={(event) => onQueryChange(event.target.value)}
          />
        </label>

        {error ? (
          <div className="kimi-wiki-selection__status is-error" role="status">
            <span>条目列表暂不可用：{error}</span>
            <button type="button" aria-label="重试条目列表" onClick={onRetry}>
              <RotateCcw aria-hidden="true" />
              重试
            </button>
          </div>
        ) : null}
        {loading && model.entries.length === 0 ? (
          <p className="kimi-wiki-selection__status">正在读取档案索引...</p>
        ) : null}
        {!loading && !error && model.entries.length === 0 ? (
          <p className="kimi-wiki-selection__status">暂无匹配档案</p>
        ) : null}

        <div
          ref={rosterRef}
          className="kimi-wiki-selection__roster native-scrollbar-hidden"
          data-testid="kimi-character-roster"
          data-scroll-owner="character-roster"
          onScroll={handleRosterScroll}
          tabIndex={0}
        >
          {model.entries.map((entry) => (
            <button
              key={entry.pageId}
              type="button"
              aria-label={entry.title}
              aria-pressed={entry.selected}
              className="kimi-wiki-selection__roster-item"
              onClick={() => onSelect(entry.pageId)}
            >
              <RosterThumbnail src={entry.thumbnail} title={entry.title} />
              <span>{entry.title}</span>
              <small>{entry.subtitle || entry.canonicalRoute}</small>
            </button>
          ))}
        </div>

        <footer className="kimi-wiki-selection__index-footer">
          <span>{loadedCount} / {totalCount}</span>
          {hasMore ? (
            <button
              type="button"
              aria-label={loadingMore ? '正在加载更多档案' : '加载更多档案'}
              disabled={loadingMore}
              onClick={onLoadMore}
            >
              <ChevronDown aria-hidden="true" />
              {loadingMore ? '正在加载...' : '加载更多'}
            </button>
          ) : null}
        </footer>
      </aside>

      <CharacterStage
        selected={model.selected}
        previewError={previewError}
        onRetryPreview={onRetryPreview}
      />

      <aside className="kimi-wiki-selection__summary" data-testid="kimi-personnel-summary">
        <div>
          <p>PERSONNEL_FILE / INDEX_03</p>
          <h2>{model.selected?.title || '未选择角色'}</h2>
          <em>{model.selected?.subtitle || 'ARCHIVE ENTRY'}</em>
          <span>{model.selected?.canonicalRoute || 'NO CANONICAL ROUTE'}</span>
        </div>
        {model.selected?.summaryFacts.length ? (
          <dl className="kimi-wiki-selection__summary-facts" data-testid="kimi-personnel-facts">
            {model.selected.summaryFacts.map((fact) => (
              <div key={`${fact.label}:${fact.value}`}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <div className="kimi-wiki-selection__summary-copy" data-testid="kimi-personnel-copy">
          {model.selected?.summaryParagraphs.length
            ? model.selected.summaryParagraphs.map((paragraph, index) => (
              <p key={`${index}:${paragraph}`}>{paragraph}</p>
            ))
            : <p>{model.selected?.summary || '从档案索引选择角色后读取概述。'}</p>}
        </div>
        <div className="kimi-wiki-selection__cta-block">
          <Archive aria-hidden="true" />
          <strong>查看完整档案</strong>
          <span>ACCESS FULL DOSSIER</span>
          <button
            type="button"
            aria-label="查看完整档案"
            disabled={!canOpenDetail}
            onClick={onOpenDetail}
          >
            INITIALIZE
          </button>
        </div>
      </aside>
    </section>
  )
}

function CharacterStage({
  selected,
  previewError,
  onRetryPreview,
}: {
  selected: KimiWikiPreviewViewModel['selected']
  previewError: string
  onRetryPreview(): void
}) {
  const backdropStyle = selected?.backdrop
    ? { backgroundImage: `url("${selected.backdrop.url}")` }
    : undefined

  return (
    <section className="kimi-wiki-selection__stage" data-testid="kimi-character-stage" style={backdropStyle}>
      <div className="kimi-wiki-selection__stage-shade" aria-hidden="true" />
      <header>
        <span>WIKI · PERSONNEL</span>
        <span>{selected ? '01 / ACTIVE' : '00 / STANDBY'}</span>
      </header>
      <span className="kimi-wiki-selection__watermark" aria-hidden="true">CONFIDENTIAL</span>
      {previewError ? (
        <div className="kimi-wiki-selection__preview-status" role="status">
          <span>角色预览暂不可用：{previewError}</span>
          <button type="button" aria-label="重试角色预览" onClick={onRetryPreview}>
            <RotateCcw aria-hidden="true" />
            重试
          </button>
        </div>
      ) : null}
      {selected?.portrait ? (
        <StagePortrait media={selected.portrait} />
      ) : (
        <div className="kimi-wiki-selection__media-fallback">
          <ImageOff aria-hidden="true" />
          <strong>MEDIA UNAVAILABLE</strong>
        </div>
      )}
      <footer>
        <strong>{selected?.title || 'NO SUBJECT'}</strong>
        <span>{selected?.subtitle || 'PERSONNEL ARCHIVE'}</span>
      </footer>
    </section>
  )
}

function StagePortrait({ media }: { media: KimiPreviewMedia }) {
  const [failed, setFailed] = useState(false)

  useEffect(() => setFailed(false), [media.url])

  if (failed) {
    return (
      <div className="kimi-wiki-selection__media-fallback">
        <ImageOff aria-hidden="true" />
        <strong>MEDIA UNAVAILABLE</strong>
      </div>
    )
  }

  return (
    <img
      className="kimi-wiki-selection__portrait"
      src={media.url}
      alt={media.title}
      onError={() => setFailed(true)}
    />
  )
}

function RosterThumbnail({ src, title }: { src: string; title: string }) {
  const [failed, setFailed] = useState(false)

  useEffect(() => setFailed(false), [src])

  return (
    <span className="kimi-wiki-selection__thumb" aria-hidden="true">
      {src && !failed ? (
        <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} />
      ) : (
        <span><ImageOff aria-hidden="true" /><small>{title.slice(0, 1)}</small></span>
      )}
    </span>
  )
}
