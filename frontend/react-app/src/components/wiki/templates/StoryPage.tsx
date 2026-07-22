import type { WikiPageDetail } from '../../../types/wiki'
import { StructuredContentRenderer } from '../StructuredContentRenderer'
import { WikiScrollRevealText } from '../WikiScrollRevealText'

export function StoryPage({ page }: { page: WikiPageDetail }) {
  return <section className="wiki-story-body"><div className="wiki-template__eyebrow">剧情资料</div><WikiScrollRevealText text={page.title} enabled as="h1" pageType={page.pageType} /><StructuredContentRenderer blocks={page.content.blocks} linkSpans={page.linkSpans} pageType={page.pageType} fallback={String(page.content.summary || page.summary || '暂无剧情正文')} /></section>
}
