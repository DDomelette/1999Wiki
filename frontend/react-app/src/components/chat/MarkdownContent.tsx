import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

type MarkdownContentProps = {
  text: string
  streaming?: boolean
}

type MarkdownBlock =
  | { type: 'heading'; level: 1 | 2 | 3 | 4 | 5 | 6; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'unordered-list'; items: string[] }
  | { type: 'ordered-list'; items: string[] }
  | { type: 'blockquote'; text: string }
  | { type: 'code'; code: string }
  | { type: 'table'; headers: string[]; rows: string[][] }

const fencedCodePattern = /^```/
const headingPattern = /^(#{1,6})\s+(.+)$/
const unorderedListPattern = /^\s*[-*+]\s+(.+)$/
const orderedListPattern = /^\s*\d+[.)]\s+(.+)$/
const blockquotePattern = /^>\s?(.*)$/

export function MarkdownContent({ text, streaming = false }: MarkdownContentProps) {
  const blocks = parseMarkdownBlocks(text)

  return (
    <div className="markdown-message">
      {blocks.map((block, index) => renderBlock(block, `block-${index}`))}
      {streaming && (
        <motion.span
          className="markdown-message__cursor"
          animate={{ opacity: [0, 1, 0] }}
          transition={{ duration: 1, repeat: Infinity }}
        >
          |
        </motion.span>
      )}
    </div>
  )
}

function parseMarkdownBlocks(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const blocks: MarkdownBlock[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      index += 1
      continue
    }

    if (fencedCodePattern.test(line.trim())) {
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !fencedCodePattern.test(lines[index].trim())) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) {
        index += 1
      }
      blocks.push({ type: 'code', code: codeLines.join('\n') })
      continue
    }

    const headingMatch = line.match(headingPattern)
    if (headingMatch) {
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length as 1 | 2 | 3 | 4 | 5 | 6,
        text: headingMatch[2].trim(),
      })
      index += 1
      continue
    }

    if (isTableStart(lines, index)) {
      const table = parseTable(lines, index)
      blocks.push(table.block)
      index = table.nextIndex
      continue
    }

    const unorderedListMatch = line.match(unorderedListPattern)
    if (unorderedListMatch) {
      const items: string[] = []
      while (index < lines.length) {
        const match = lines[index].match(unorderedListPattern)
        if (!match) {
          break
        }
        items.push(match[1].trim())
        index += 1
      }
      blocks.push({ type: 'unordered-list', items })
      continue
    }

    const orderedListMatch = line.match(orderedListPattern)
    if (orderedListMatch) {
      const items: string[] = []
      while (index < lines.length) {
        const match = lines[index].match(orderedListPattern)
        if (!match) {
          break
        }
        items.push(match[1].trim())
        index += 1
      }
      blocks.push({ type: 'ordered-list', items })
      continue
    }

    const blockquoteMatch = line.match(blockquotePattern)
    if (blockquoteMatch) {
      const quoteLines: string[] = []
      while (index < lines.length) {
        const match = lines[index].match(blockquotePattern)
        if (!match) {
          break
        }
        quoteLines.push(match[1].trim())
        index += 1
      }
      blocks.push({ type: 'blockquote', text: quoteLines.join(' ') })
      continue
    }

    const paragraphLines: string[] = [line.trim()]
    index += 1
    while (
      index < lines.length &&
      lines[index].trim() &&
      !headingPattern.test(lines[index]) &&
      !fencedCodePattern.test(lines[index].trim()) &&
      !unorderedListPattern.test(lines[index]) &&
      !orderedListPattern.test(lines[index]) &&
      !blockquotePattern.test(lines[index]) &&
      !isTableStart(lines, index)
    ) {
      paragraphLines.push(lines[index].trim())
      index += 1
    }
    blocks.push({ type: 'paragraph', text: paragraphLines.join(' ') })
  }

  return blocks
}

function isTableStart(lines: string[], index: number) {
  if (index + 1 >= lines.length) {
    return false
  }
  return lines[index].includes('|') && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index + 1])
}

function parseTable(lines: string[], index: number): { block: MarkdownBlock; nextIndex: number } {
  const headers = splitTableRow(lines[index])
  const rows: string[][] = []
  let nextIndex = index + 2

  while (nextIndex < lines.length && lines[nextIndex].includes('|') && lines[nextIndex].trim()) {
    rows.push(splitTableRow(lines[nextIndex]))
    nextIndex += 1
  }

  return { block: { type: 'table', headers, rows }, nextIndex }
}

function splitTableRow(row: string) {
  return row
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function renderBlock(block: MarkdownBlock, key: string) {
  switch (block.type) {
    case 'heading':
      return renderHeading(block.level, block.text, key)
    case 'paragraph':
      return <p key={key}>{renderInline(block.text, key)}</p>
    case 'unordered-list':
      return (
        <ul key={key}>
          {block.items.map((item, index) => (
            <li key={`${key}-${index}`}>{renderInline(item, `${key}-${index}`)}</li>
          ))}
        </ul>
      )
    case 'ordered-list':
      return (
        <ol key={key}>
          {block.items.map((item, index) => (
            <li key={`${key}-${index}`}>{renderInline(item, `${key}-${index}`)}</li>
          ))}
        </ol>
      )
    case 'blockquote':
      return <blockquote key={key}>{renderInline(block.text, key)}</blockquote>
    case 'code':
      return (
        <pre key={key}>
          <code>{block.code}</code>
        </pre>
      )
    case 'table':
      return (
        <table key={key}>
          <thead>
            <tr>
              {block.headers.map((header, index) => (
                <th key={`${key}-header-${index}`}>{renderInline(header, `${key}-header-${index}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={`${key}-row-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`${key}-cell-${rowIndex}-${cellIndex}`}>
                    {renderInline(cell, `${key}-cell-${rowIndex}-${cellIndex}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )
  }
}

function renderHeading(level: Extract<MarkdownBlock, { type: 'heading' }>['level'], text: string, key: string) {
  switch (level) {
    case 1:
      return <h1 key={key}>{renderInline(text, key)}</h1>
    case 2:
      return <h2 key={key}>{renderInline(text, key)}</h2>
    case 3:
      return <h3 key={key}>{renderInline(text, key)}</h3>
    case 4:
      return <h4 key={key}>{renderInline(text, key)}</h4>
    case 5:
      return <h5 key={key}>{renderInline(text, key)}</h5>
    case 6:
      return <h6 key={key}>{renderInline(text, key)}</h6>
  }
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let cursor = 0

  while (cursor < text.length) {
    const token = findNextInlineToken(text, cursor)

    if (!token) {
      nodes.push(text.slice(cursor))
      break
    }

    if (token.start > cursor) {
      nodes.push(text.slice(cursor, token.start))
    }

    const key = `${keyPrefix}-inline-${nodes.length}`
    nodes.push(token.node(key))
    cursor = token.end
  }

  return nodes
}

function findNextInlineToken(text: string, from: number): { start: number; end: number; node: (key: string) => ReactNode } | null {
  const candidates = [
    parseCodeSpan(text, from),
    parseImage(text, from),
    parseLink(text, from),
    parseStrong(text, from, '**'),
    parseStrong(text, from, '__'),
    parseEmphasis(text, from, '*'),
    parseEmphasis(text, from, '_'),
  ].filter(Boolean) as { start: number; end: number; node: (key: string) => ReactNode }[]

  if (candidates.length === 0) {
    return null
  }

  return candidates.sort((a, b) => a.start - b.start)[0]
}

function parseCodeSpan(text: string, from: number) {
  const start = text.indexOf('`', from)
  if (start === -1) {
    return null
  }
  const end = text.indexOf('`', start + 1)
  if (end === -1) {
    return null
  }
  const code = text.slice(start + 1, end)
  return {
    start,
    end: end + 1,
    node: (key: string) => <code key={key}>{code}</code>,
  }
}

function parseImage(text: string, from: number) {
  const start = text.indexOf('![', from)
  if (start === -1) {
    return null
  }
  const labelEnd = text.indexOf(']', start + 2)
  if (labelEnd === -1 || text[labelEnd + 1] !== '(') {
    return null
  }
  const srcEnd = text.indexOf(')', labelEnd + 2)
  if (srcEnd === -1) {
    return null
  }
  const alt = text.slice(start + 2, labelEnd)
  const src = sanitizeHref(text.slice(labelEnd + 2, srcEnd))
  return {
    start,
    end: srcEnd + 1,
    node: (key: string) =>
      src ? (
        <img
          key={key}
          src={src}
          alt={alt}
          loading="lazy"
          style={{
            display: 'block',
            maxWidth: '100%',
            maxHeight: 220,
            objectFit: 'contain',
            margin: '8px 0',
          }}
        />
      ) : (
        <span key={key}>{alt}</span>
      ),
  }
}

function parseLink(text: string, from: number) {
  const start = text.indexOf('[', from)
  if (start === -1) {
    return null
  }
  const labelEnd = text.indexOf(']', start + 1)
  if (labelEnd === -1 || text[labelEnd + 1] !== '(') {
    return null
  }
  const hrefEnd = text.indexOf(')', labelEnd + 2)
  if (hrefEnd === -1) {
    return null
  }
  const label = text.slice(start + 1, labelEnd)
  const href = text.slice(labelEnd + 2, hrefEnd)
  const safeHref = sanitizeHref(href)

  return {
    start,
    end: hrefEnd + 1,
    node: (key: string) =>
      safeHref ? (
        <a key={key} href={safeHref} target="_blank" rel="noreferrer">
          {renderInline(label, key)}
        </a>
      ) : (
        <span key={key}>{label}</span>
      ),
  }
}

function parseStrong(text: string, from: number, marker: '**' | '__') {
  const start = text.indexOf(marker, from)
  if (start === -1) {
    return null
  }
  const end = text.indexOf(marker, start + marker.length)
  if (end === -1) {
    return null
  }
  const content = text.slice(start + marker.length, end)
  return {
    start,
    end: end + marker.length,
    node: (key: string) => <strong key={key}>{renderInline(content, key)}</strong>,
  }
}

function parseEmphasis(text: string, from: number, marker: '*' | '_') {
  const start = text.indexOf(marker, from)
  if (start === -1 || text[start + 1] === marker || /\s/.test(text[start + 1] ?? '')) {
    return null
  }
  const end = text.indexOf(marker, start + 1)
  if (end === -1 || /\s/.test(text[end - 1] ?? '')) {
    return null
  }
  const content = text.slice(start + 1, end)
  return {
    start,
    end: end + 1,
    node: (key: string) => <em key={key}>{renderInline(content, key)}</em>,
  }
}

function sanitizeHref(href: string) {
  const trimmed = href.trim()
  if (/^(https?:|mailto:|#|\/)/i.test(trimmed)) {
    return trimmed
  }
  return ''
}
