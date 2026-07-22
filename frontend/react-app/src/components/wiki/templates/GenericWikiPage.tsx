import type { WikiPageDetail } from '../../../types/wiki'
import { StructuredContentRenderer } from '../StructuredContentRenderer'
import { WikiScrollRevealText } from '../WikiScrollRevealText'

export function GenericWikiPage({ page }: { page: WikiPageDetail }) {
  return <section><div className="wiki-template__eyebrow">{page.pageType}</div><WikiScrollRevealText text={page.title} enabled as="h1" pageType={page.pageType} /><section><h2>来源</h2><p>{page.sourceTitle || page.sourcePageid || 'unknown'}</p></section><StructuredContentRenderer blocks={page.content.blocks} linkSpans={page.linkSpans} pageType={page.pageType} fallback={String(page.content.summary || page.summary || '暂无正文')} /></section>
}
