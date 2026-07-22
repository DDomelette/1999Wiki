import type { WikiPageDetail } from '../../../types/wiki'
import { StructuredContentRenderer } from '../StructuredContentRenderer'
import { WikiScrollRevealText } from '../WikiScrollRevealText'

export function PsychubePage({ page }: { page: WikiPageDetail }) {
  return <section className="wiki-psychube-body"><div className="wiki-template__eyebrow">心相资料</div><WikiScrollRevealText text={page.title} enabled as="h1" pageType={page.pageType} /><StructuredContentRenderer blocks={page.content.blocks} linkSpans={page.linkSpans} pageType={page.pageType} fallback={String(page.content.summary || page.summary || '暂无心相正文')} /></section>
}
