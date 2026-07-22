import type { WikiContentBlock, WikiPageLinkSpan } from '../../types/wiki'
import { KeywordText } from './KeywordText'
import { WikiErrorBoundary } from './WikiErrorBoundary'
import { WikiScrollRevealText } from './WikiScrollRevealText'
import { buildFallbackBlocks } from './wikiViewModel'
import './StructuredContentRenderer.css'

interface StructuredContentRendererProps {
  blocks?: WikiContentBlock[]
  fallback?: string
  linkSpans?: WikiPageLinkSpan[]
  pageType?: string
}

export function StructuredContentRenderer({
  blocks,
  fallback = '',
  linkSpans = [],
  pageType = '',
}: StructuredContentRendererProps) {
  const renderBlocks = blocks?.length ? blocks : buildFallbackBlocks(fallback)
  if (!renderBlocks.length) return null

  return (
    <div className="wiki-content">
      {renderBlocks.map((block) => (
        <WikiErrorBoundary
          key={block.id}
          resetKey={block.id}
          fallback={<p className="archive-error">该段资料暂不可用</p>}
        >
          <Block
            block={block}
            pageType={pageType}
            linkSpans={linkSpans.filter((span) => !span.sectionKey || span.sectionKey === block.section)}
          />
        </WikiErrorBoundary>
      ))}
    </div>
  )
}

function Block({
  block,
  linkSpans,
  pageType,
}: {
  block: WikiContentBlock
  linkSpans: WikiPageLinkSpan[]
  pageType: string
}) {
  if (block.type === 'heading') {
    const level = Math.min(4, Math.max(2, block.level ?? 2))
    const Tag = `h${level}` as 'h2' | 'h3' | 'h4'
    return linkSpans.length
      ? <Tag className="wiki-content__heading"><Linked text={block.text ?? ''} spans={linkSpans} /></Tag>
      : tagReveal(Tag, block.text ?? '', pageType)
  }

  if (block.type === 'facts') {
    return (
      <dl className="wiki-content__facts">
        {(block.items ?? []).map((item, index) => typeof item === 'string' ? (
          <div key={`${item}-${index}`}>
            <dd><Linked text={item} spans={linkSpans} /></dd>
          </div>
        ) : (
          <div key={`${item.label}-${index}`}>
            <dt><Linked text={item.label} spans={linkSpans} /></dt>
            <dd><Linked text={item.value} spans={linkSpans} /></dd>
          </div>
        ))}
      </dl>
    )
  }

  if (block.type === 'list') {
    return (
      <ul className="wiki-content__list">
        {(block.items ?? []).map((item, index) => {
          const text = typeof item === 'string' ? item : `${item.label}：${item.value}`
          return <li key={`${text}-${index}`}><Linked text={text} spans={linkSpans} /></li>
        })}
      </ul>
    )
  }

  if (block.type === 'quote') {
    return <blockquote><Linked text={block.text ?? ''} spans={linkSpans} /></blockquote>
  }

  if (block.type === 'table') {
    return (
      <div className="wiki-content__table-wrap">
        <table>
          <tbody>
            {(block.rows ?? []).map((row, rowIndex) => (
              <tr key={`${block.id}-row-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`${block.id}-${rowIndex}-${cellIndex}`}><Linked text={cell} spans={linkSpans} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (block.type === 'structured') return <StructuredValue value={block.value} depth={0} />

  if (block.type === 'voice_reference') {
    return (
      <section className="wiki-content__voice" id={`wiki-media-${block.id}`}>
        <h3>{block.text || '语音资料'}</h3>
        <span>{block.mediaIds.length} 条媒体</span>
      </section>
    )
  }

  if (block.type === 'paragraph') {
    return linkSpans.length
      ? <p className="wiki-content__paragraph"><Linked text={block.text ?? ''} spans={linkSpans} /></p>
      : <WikiScrollRevealText text={block.text ?? ''} enabled={Boolean(block.reveal)} pageType={pageType} />
  }

  return <p className="archive-error">该段资料暂不可用</p>
}

function Linked({ text, spans }: { text: string; spans: WikiPageLinkSpan[] }) {
  return spans.length ? <KeywordText text={text} spans={spans} /> : <>{text}</>
}

function StructuredValue({ value, depth }: { value: unknown; depth: number }): JSX.Element | null {
  if (!isDisplayable(value)) return null
  if (depth >= 3 && (Array.isArray(value) || isRecord(value))) {
    return (
      <details>
        <summary>展开更多资料</summary>
        <span>{summarizeNested(value) || '嵌套资料'}</span>
      </details>
    )
  }
  if (Array.isArray(value)) {
    return (
      <ul className="wiki-content__list">
        {value.map((item, index) => isDisplayable(item) ? (
          <li key={index}><StructuredValue value={item} depth={depth + 1} /></li>
        ) : null)}
      </ul>
    )
  }
  if (isRecord(value)) {
    return (
      <dl className="wiki-content__facts">
        {displayEntries(value).map(([key, item]) => isDisplayable(item) ? (
          <div key={key}>
            <dt>{key}</dt>
            <dd><StructuredValue value={item} depth={depth + 1} /></dd>
          </div>
        ) : null)}
      </dl>
    )
  }
  return <span>{String(value)}</span>
}

function displayEntries(value: Record<string, unknown>): Array<[string, unknown]> {
  return Object.entries(value).filter(([key]) => !isDiagnosticKey(key))
}

function isDiagnosticKey(key: string): boolean {
  const normalizedKey = key.toLowerCase().replace(/_/g, '')
  return ['raw', 'source', 'debug', 'diagnostic', 'localrelpath'].includes(normalizedKey)
}

function summarizeNested(value: unknown, depth = 0, seen = new WeakSet<object>()): string {
  if (value == null || value === '') return ''
  if (typeof value !== 'object') return String(value)
  if (depth >= 4 || seen.has(value)) return ''
  seen.add(value)

  if (Array.isArray(value)) {
    return value.map((item) => summarizeNested(item, depth + 1, seen)).filter(Boolean).join(' · ')
  }
  if (!isRecord(value)) return ''
  return displayEntries(value)
    .map(([key, item]) => {
      const summary = summarizeNested(item, depth + 1, seen)
      return summary ? `${key}：${summary}` : ''
    })
    .filter(Boolean)
    .join(' · ')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isDisplayable(value: unknown): boolean {
  if (value === '' || value == null) return false
  if (Array.isArray(value)) return value.some(isDisplayable)
  if (isRecord(value)) return displayEntries(value).some(([, item]) => isDisplayable(item))
  return true
}

function tagReveal(tag: 'h2' | 'h3' | 'h4', text: string, pageType: string) {
  if (tag === 'h4') return <h4 className="wiki-content__heading">{text}</h4>
  return <WikiScrollRevealText text={text} enabled as={tag} pageType={pageType} />
}
