import type { MouseEvent, ReactNode } from 'react'

export interface WikiLinkSpan {
  text: string
  targetRoute?: string
  confidence?: number
}

interface KeywordTextProps {
  text: string
  spans: WikiLinkSpan[]
  validateRoute?: (span: WikiLinkSpan) => Promise<string | null> | string | null
  onNavigate?: (route: string) => void
}

export function KeywordText({ text, spans, validateRoute, onNavigate }: KeywordTextProps) {
  const nodes: ReactNode[] = []
  let cursor = 0

  const navigate = (route: string) => {
    if (onNavigate) {
      onNavigate(route)
      return
    }
    window.location.assign(route)
  }

  const handleValidatedClick = async (event: MouseEvent<HTMLAnchorElement>, span: WikiLinkSpan) => {
    if (!validateRoute) return
    event.preventDefault()
    let route: string | null = null
    try {
      route = await validateRoute(span)
    } catch {
      route = null
    }
    navigate(route || `/wiki?q=${encodeURIComponent(span.text)}`)
  }

  spans.forEach((span, index) => {
    if (!span.text) return
    const start = text.indexOf(span.text, cursor)
    if (start < 0) return
    if (start > cursor) nodes.push(text.slice(cursor, start))
    const value = text.slice(start, start + span.text.length)
    if (span.targetRoute) {
      nodes.push(
        <a
          key={`${span.text}-${index}`}
          href={span.targetRoute}
          onClick={validateRoute ? (event) => { void handleValidatedClick(event, span) } : undefined}
          style={{ color: '#2f7ddf', textDecoration: 'none', fontWeight: 600 }}
        >
          {value}
        </a>,
      )
    } else {
      nodes.push(<span key={`${span.text}-${index}`}>{value}</span>)
    }
    cursor = start + span.text.length
  })

  if (cursor < text.length) nodes.push(text.slice(cursor))

  return <>{nodes}</>
}
