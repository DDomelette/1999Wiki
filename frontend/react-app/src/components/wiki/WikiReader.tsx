import { useMemo } from 'react'
import type { WikiPageDetail } from '../../types/wiki'
import { CharacterPage } from './templates/CharacterPage'
import { CharacterMediaStage } from './templates/CharacterMediaStage'
import { GenericWikiPage } from './templates/GenericWikiPage'
import { PsychubePage } from './templates/PsychubePage'
import { StoryPage } from './templates/StoryPage'
import { WikiHeroStage } from './WikiHeroStage'
import { buildWikiPageViewModel, type WikiPageViewModel } from './wikiViewModel'
import './WikiReader.css'

interface WikiReaderProps {
  page: WikiPageDetail | null
  loading?: boolean
  error?: string
}

interface WikiReaderPartProps {
  view: WikiPageViewModel | null
  loading?: boolean
  error?: string
}

export function WikiReader({ page, loading = false, error = '' }: WikiReaderProps) {
  const view = useMemo(() => page ? buildWikiPageViewModel(page) : null, [page])

  return (
    <article data-testid="wiki-reader" id="wiki-content" className="wiki-reader">
      <WikiReaderHero view={view} loading={loading} error={error} />
      <WikiReaderBody view={view} loading={loading} error={error} />
    </article>
  )
}

export function WikiReaderHero({ view, loading = false, error = '' }: WikiReaderPartProps) {
  if (loading && !view) return <p className="archive-meta">正在读取主媒体...</p>
  if (error && !view) return <p className="archive-error">Wiki 媒体暂不可用：{error}</p>
  if (!view) return <p className="archive-empty">请选择一个页面</p>

  if (isCharacter(view)) {
    return (
      <CharacterMediaStage
        title={view.page.title}
        portraitSlots={view.portraitSlots}
        portraits={view.portraits}
        voices={view.voices}
      />
    )
  }

  const candidates = view.images.length
    ? view.images
    : view.primaryMedia && view.primaryMedia.kind !== 'voice'
      ? [view.primaryMedia]
      : []
  const emptyLabel = mediaEmptyLabel(view)
  return candidates.length
    ? <WikiHeroStage title={view.page.title} candidates={candidates} emptyLabel={emptyLabel} />
    : <p className="archive-empty wiki-reader__compact-empty">{emptyLabel}</p>
}

export function WikiReaderBody({ view, loading = false, error = '' }: WikiReaderPartProps) {
  if (loading && !view) return <p>加载中...</p>
  if (error && !view) return <p className="archive-error">Wiki 数据暂不可用：{error}</p>
  if (!view) return <p className="archive-empty">请选择一个页面</p>

  const page = view.page
  const key = `${page.pageType} ${page.category}`.toLowerCase()
  if (isCharacter(view)) return <CharacterPage page={page} />
  if (key.includes('psychube') || page.category === '心相') return <PsychubePage page={page} />
  if (key.includes('story') || page.category === '剧情') return <StoryPage page={page} />
  return <GenericWikiPage page={page} />
}

function isCharacter(view: WikiPageViewModel): boolean {
  const key = `${view.page.pageType} ${view.page.category}`.toLowerCase()
  return key.includes('character') || view.page.category === '角色'
}

function mediaEmptyLabel(view: WikiPageViewModel): string {
  const key = `${view.page.pageType} ${view.page.category}`.toLowerCase()
  if (key.includes('story') || view.page.category === '剧情') return '暂无剧情封面'
  if (key.includes('psychube') || view.page.category === '心相') return '暂无心相图片'
  return '暂无主媒体'
}
