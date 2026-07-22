import type { WikiContentBlock, WikiPageDetail } from '../../../types/wiki'
import { StructuredContentRenderer } from '../StructuredContentRenderer'
import { WikiScrollRevealText } from '../WikiScrollRevealText'
import { buildWikiPageViewModel } from '../wikiViewModel'

export function CharacterPage({ page }: { page: WikiPageDetail }) {
  const view = buildWikiPageViewModel(page)
  const crawlerProjected = page.content.crawlerProjectionVersion === 1

  return (
    <section className="wiki-character-body" data-testid="character-detail-panel">
      <div className="wiki-template__eyebrow">角色资料</div>
      <WikiScrollRevealText text={page.title} enabled as="h1" pageType={page.pageType} />
      {page.subtitle ? <p>{page.subtitle}</p> : null}
      <CharacterSection title="基本资料" blocks={view.characterSections.profile} page={page} />
      <CharacterSection title="技能" blocks={view.characterSections.skills} page={page} />
      <CharacterSection title="传承" blocks={view.characterSections.inheritance} page={page} required={crawlerProjected} />
      <CharacterSection title="塑造" blocks={view.characterSections.portray} page={page} required={crawlerProjected} />
      <CharacterSection title="语音档案" blocks={view.characterSections.voices} page={page} />
      <CharacterSection title="档案" blocks={view.characterSections.archive} page={page} />
      <CharacterSection title="正文" blocks={view.characterSections.remainder} page={page} />
    </section>
  )
}

function CharacterSection({
  title,
  blocks,
  page,
  required = false,
}: {
  title: string
  blocks: WikiContentBlock[]
  page: WikiPageDetail
  required?: boolean
}) {
  if (!blocks.length && !required) return null
  return (
    <section className="wiki-character-body__section">
      <h2 className="wiki-detail-slot-title">{title}</h2>
      {blocks.length ? (
        <StructuredContentRenderer
          blocks={blocks}
          linkSpans={page.linkSpans}
          pageType={page.pageType}
        />
      ) : (
        <p className="archive-error">补充数据链路缺少{title}资料</p>
      )}
    </section>
  )
}
