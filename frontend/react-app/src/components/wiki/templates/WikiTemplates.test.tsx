import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CharacterPage } from './CharacterPage'
import { GenericWikiPage } from './GenericWikiPage'
import { PsychubePage } from './PsychubePage'
import { StoryPage } from './StoryPage'
import type { WikiPageDetail } from '../../../types/wiki'
import { WikiReaderHero } from '../WikiReader'
import { buildWikiPageViewModel } from '../wikiViewModel'

const basePage: WikiPageDetail = {
  pageId: 'char:3074',
  pageType: 'character',
  title: '爱兹拉',
  subtitle: 'Ezra Theodore',
  category: '角色',
  route: '/wiki/char/3074',
  thumbnail: '',
  summary: '角色摘要',
  sourceTitle: 'Data:Char/3074.json',
  content: { summary: '角色正文', rarity: '6' },
  mediaLinks: [
    {
      mediaId: 'portrait-1',
      assetType: 'portrait',
      role: 'portrait',
      url: 'http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/ezra.webp',
      title: '爱兹拉立绘',
    },
  ],
  relations: [],
  linkSpans: [],
}

describe('wiki templates', () => {
  it('keeps the character primary media in the reader hero only', () => {
    render(<WikiReaderHero view={buildWikiPageViewModel(basePage)} />)

    expect(screen.getByTestId('character-media-stage')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-hero-stage')).toBeInTheDocument()
  })

  it('renders psychube and story body templates without a second hero stage', () => {
    render(<PsychubePage page={{ ...basePage, pageType: 'psychube', title: '第二次生命', category: '心相', mediaLinks: [] }} />)
    expect(screen.getByText('心相资料')).toBeInTheDocument()
    expect(screen.queryByTestId('wiki-hero-stage')).not.toBeInTheDocument()

    render(<StoryPage page={{ ...basePage, pageType: 'story', title: '此即明日', category: '剧情', mediaLinks: [] }} />)
    expect(screen.getByText('剧情资料')).toBeInTheDocument()
    expect(screen.queryByTestId('wiki-hero-stage')).not.toBeInTheDocument()
  })

  it('reuses the transparent reader hero for non-character primary media', () => {
    const page: WikiPageDetail = {
      ...basePage,
      pageType: 'story',
      title: '此即明日',
      category: '剧情',
      mediaLinks: [{
        mediaId: 'story-cover',
        assetType: 'image',
        role: 'image',
        url: 'https://example.test/story.webp',
        title: '剧情封面',
      }],
    }
    render(<WikiReaderHero view={buildWikiPageViewModel(page)} />)

    expect(screen.getByTestId('wiki-hero-stage')).toBeInTheDocument()
    expect(screen.getByTestId('tilted-image-card')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '剧情封面' })).toHaveAttribute('src', 'https://example.test/story.webp')
  })

  it('preserves raw supplement inheritance and portray tables in character body content', () => {
    render(<CharacterPage page={{
      ...basePage,
      content: {
        crawlerProjectionVersion: 1,
        blocks: [
          { id: 'inherit-heading', type: 'heading', section: 'inheritance', mediaIds: [], text: '传承：木秀于林', level: 2 },
          { id: 'inherit-table', type: 'table', section: 'inheritance', mediaIds: [], rows: [['洞悉', '效果'], ['洞悉 III', '效果三']] },
          { id: 'portray-heading', type: 'heading', section: 'portray', mediaIds: [], text: '塑造', level: 2 },
          { id: 'portray-table', type: 'table', section: 'portray', mediaIds: [], rows: [['等级', '效果'], ['LV.1', '一阶'], ['LV.5', '五阶']] },
          { id: 'remainder', type: 'paragraph', section: 'culture', mediaIds: [], text: '后续正文' },
        ],
      },
    }} />)

    expect(screen.getByText('传承：木秀于林')).toBeInTheDocument()
    expect(screen.getByText('洞悉 III')).toBeInTheDocument()
    expect(screen.getByText('LV.5')).toBeInTheDocument()
    expect(screen.getByText('后续正文')).toBeInTheDocument()
    expect(screen.queryByTestId('character-media-stage')).not.toBeInTheDocument()
  })

  it('renders generic pages without exposing raw JSON text', () => {
    render(<GenericWikiPage page={{ ...basePage, pageType: 'generic', content: { raw: { hidden: true }, summary: '整理后的摘要' } }} />)

    expect(screen.getByText('来源')).toBeInTheDocument()
    expect(screen.getByText('整理后的摘要')).toBeInTheDocument()
    expect(screen.queryByText(/"raw"/)).not.toBeInTheDocument()
  })
})
