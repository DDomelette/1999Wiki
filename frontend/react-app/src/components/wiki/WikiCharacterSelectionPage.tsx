import type { ReactNode } from 'react'
import './WikiCharacterSelectionPage.css'

export interface WikiCharacterSelectionPageProps {
  index: ReactNode
  preview: ReactNode
  summary: ReactNode
  canOpenDetail: boolean
  onOpenDetail(): void
  activeCategory?: string
  templateGroup?: string
  animationProfile?: string
  themeToken?: string
}

export function WikiCharacterSelectionPage({
  index,
  preview,
  summary,
  canOpenDetail,
  onOpenDetail,
  activeCategory = '',
  templateGroup = '',
  animationProfile = '',
  themeToken = '',
}: WikiCharacterSelectionPageProps) {
  return (
    <section
      className="wiki-character-selection"
      data-testid="wiki-character-selection"
      data-active-category={activeCategory}
      data-template-group={templateGroup}
      data-animation-profile={animationProfile}
      data-theme-token={themeToken}
    >
      <aside className="wiki-character-selection__index" data-testid="selection-index">
        {index}
      </aside>
      <section className="wiki-character-selection__preview" data-testid="selection-preview">
        {preview}
      </section>
      <aside className="wiki-character-selection__summary" data-testid="selection-summary">
        <div>{summary}</div>
        <button type="button" disabled={!canOpenDetail} onClick={onOpenDetail}>
          查看完整档案
        </button>
      </aside>
    </section>
  )
}
