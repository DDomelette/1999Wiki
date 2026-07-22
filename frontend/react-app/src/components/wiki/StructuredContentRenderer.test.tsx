import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { WikiContentBlock } from '../../types/wiki'
import { StructuredContentRenderer } from './StructuredContentRenderer'

describe('StructuredContentRenderer', () => {
  it('renders semantic headings, facts, lists, tables and paragraphs', () => {
    render(<StructuredContentRenderer blocks={[
      { id: 'h', type: 'heading', section: 'profile', mediaIds: [], level: 2, text: '档案' },
      { id: 'f', type: 'facts', section: 'profile', mediaIds: [], items: [{ label: '稀有度', value: '5' }] },
      { id: 'l', type: 'list', section: 'profile', mediaIds: [], items: ['一', '二'] },
      { id: 't', type: 'table', section: 'profile', mediaIds: [], rows: [['名称', '值'], ['职业', '3']] },
      { id: 'p', type: 'paragraph', section: 'profile', mediaIds: [], text: '正文', reveal: false },
    ]} />)
    expect(screen.getByRole('heading', { name: '档案' })).toBeInTheDocument()
    expect(screen.getByText('稀有度')).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('正文')).toBeInTheDocument()
  })

  it('renders nested JSON semantically without a raw JSON pre block', () => {
    const { container } = render(<StructuredContentRenderer blocks={[{ id: 's', type: 'structured', section: 'profile', mediaIds: [], value: { zero: 0, enabled: false, empty: '', nested: { a: { b: { c: 'kept' } } } } }]} />)
    expect(screen.getByText('0')).toBeInTheDocument()
    expect(screen.getByText('false')).toBeInTheDocument()
    expect(screen.queryByText('empty')).not.toBeInTheDocument()
    expect(container.querySelector('pre')).not.toBeInTheDocument()
    expect(container.querySelector('details')).toBeInTheDocument()
  })

  it('applies every matching link span inside a block', () => {
    render(<StructuredContentRenderer blocks={[{ id: 'p', type: 'paragraph', section: 'culture', mediaIds: [], text: '维尔汀与十四行诗同行。' }]} linkSpans={[
      { sectionKey: 'culture', text: '维尔汀', targetRoute: '/wiki/character/1' },
      { sectionKey: 'culture', text: '十四行诗', targetRoute: '/wiki/character/2' },
    ]} />)
    expect(screen.getByRole('link', { name: '维尔汀' })).toHaveAttribute('href', '/wiki/character/1')
    expect(screen.getByRole('link', { name: '十四行诗' })).toHaveAttribute('href', '/wiki/character/2')
  })

  it('splits a long fallback into readable semantic paragraphs', () => {
    const fallback = [
      '第一段资料用于说明角色的基础背景。'.repeat(12),
      '第二段资料保留自然段边界，并且不会重新推断任何人物关系。'.repeat(10),
    ].join('\n\n')
    const { container } = render(<StructuredContentRenderer fallback={fallback} />)

    expect(container.querySelectorAll('p').length).toBeGreaterThan(2)
    expect(container).toHaveTextContent('第一段资料')
    expect(container).toHaveTextContent('第二段资料')
  })

  it('keeps rendering after an unknown or exceptional block', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const brokenValue: Record<string, unknown> = {}
    Object.defineProperty(brokenValue, 'broken', {
      enumerable: true,
      get() {
        throw new Error('broken block')
      },
    })
    const blocks = [
      { id: 'unknown', type: 'future_block', section: 'archive', mediaIds: [] },
      { id: 'broken', type: 'structured', section: 'archive', mediaIds: [], value: brokenValue },
      { id: 'after', type: 'paragraph', section: 'archive', mediaIds: [], text: '后续正文' },
    ] as unknown as WikiContentBlock[]

    render(<StructuredContentRenderer blocks={blocks} />)

    expect(screen.getAllByText('该段资料暂不可用')).toHaveLength(2)
    expect(screen.getByText('后续正文')).toBeInTheDocument()
    consoleError.mockRestore()
  })

  it('does not expose diagnostic raw or source objects from structured blocks', () => {
    render(<StructuredContentRenderer blocks={[{
      id: 'diagnostic',
      type: 'structured',
      section: 'archive',
      mediaIds: [],
      value: {
        title: '可展示资料',
        raw: { hidden: true },
        source: { local_relpath: 'D:\\private\\page.md' },
        debug: 'internal',
      },
    }]} />)

    expect(screen.getByText('可展示资料')).toBeInTheDocument()
    expect(screen.queryByText('raw')).not.toBeInTheDocument()
    expect(screen.queryByText('source')).not.toBeInTheDocument()
    expect(screen.queryByText(/private/)).not.toBeInTheDocument()
  })

  it('preserves variable inheritance rows and all portray levels', () => {
    render(<StructuredContentRenderer blocks={[
      {
        id: 'inheritance',
        type: 'table',
        section: 'inheritance',
        mediaIds: [],
        rows: [['洞悉', '效果'], ['洞悉 I', '效果一'], ['洞悉 III', '效果三']],
      },
      {
        id: 'portray',
        type: 'table',
        section: 'portray',
        mediaIds: [],
        rows: [['等级', '效果'], ['LV.1', '一阶'], ['LV.5', '五阶']],
      },
    ]} />)

    expect(screen.getByText('洞悉 III')).toBeInTheDocument()
    expect(screen.getByText('LV.1')).toBeInTheDocument()
    expect(screen.getByText('LV.5')).toBeInTheDocument()
  })

  it('keeps reveal markup opt-in while preserving readable static text', () => {
    const { container } = render(<StructuredContentRenderer blocks={[
      { id: 'animated', type: 'paragraph', section: 'archive', mediaIds: [], text: '需要 动效', reveal: true },
      { id: 'static', type: 'paragraph', section: 'archive', mediaIds: [], text: '静态文本', reveal: false },
    ]} />)

    expect(container.querySelectorAll('[data-reveal-word]').length).toBeGreaterThan(0)
    expect(screen.getByText('静态文本')).toBeInTheDocument()
  })
})
