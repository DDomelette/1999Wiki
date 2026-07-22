import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { WikiPageDetail } from '../../types/wiki'
import { PageInfo } from './PageInfo'
import { buildWikiPageViewModel } from './wikiViewModel'

const detail: WikiPageDetail = {
  pageId: 'char:3074',
  pageType: 'character',
  title: '爱兹拉',
  subtitle: 'Ezra Theodore',
  category: '角色',
  route: '/wiki/char/3074',
  thumbnail: '',
  summary: '角色摘要',
  sourcePageid: 3074,
  sourceTitle: 'Data:Char/3074.json',
  content: {
    aliases: [],
    profile: {
      介质: '树木',
      传承: '木秀于林',
      定位标签: ['输出', '控制'],
    },
  },
  mediaLinks: [{ assetType: 'image', role: 'image', url: 'https://example.test/a.webp' }],
  relations: [
    { title: '十四行诗', targetRoute: '/wiki/char/3002' },
    { title: '未解析关系' },
  ],
  linkSpans: [{ text: '维尔汀', targetRoute: '/wiki/char/3001' }],
}

describe('PageInfo', () => {
  it('renders profile facts and complete traceable dossier fields from the view model', () => {
    render(<PageInfo view={buildWikiPageViewModel(detail)} />)

    const info = screen.getByTestId('wiki-page-info')
    expect(info).toBeInTheDocument()
    expect(screen.getByText('介质')).toBeInTheDocument()
    expect(screen.getByText('树木')).toBeInTheDocument()
    expect(screen.getByText('木秀于林')).toBeInTheDocument()
    expect(screen.getByText('char:3074')).toBeInTheDocument()
    expect(screen.getByText('角色')).toBeInTheDocument()
    expect(screen.getByText('character')).toBeInTheDocument()
    expect(screen.getAllByText('无').length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: '/wiki/char/3074' })).toHaveAttribute('href', '/wiki/char/3074')
    expect(info).not.toHaveTextContent('undefined')
    expect(info).not.toHaveAttribute('style')
  })

  it('links only relations that already contain an API route', () => {
    render(<PageInfo view={buildWikiPageViewModel(detail)} />)

    const relations = screen.getByRole('list', { name: '关联页面' })
    expect(within(relations).getByRole('link', { name: '十四行诗' })).toHaveAttribute('href', '/wiki/char/3002')
    expect(within(relations).getByText('未解析关系')).toBeInTheDocument()
    expect(within(relations).queryByRole('link', { name: '未解析关系' })).not.toBeInTheDocument()
  })

  it('uses a stable empty state when no page is selected', () => {
    render(<PageInfo view={null} />)

    expect(screen.getByText('未选择页面')).toBeInTheDocument()
    expect(screen.queryByText('undefined')).not.toBeInTheDocument()
  })
})
