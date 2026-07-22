import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  CharacterDetailViewModel,
  CharacterMediaViewModel,
} from '../wiki/characterDetailViewModel'
import type { KimiWikiDetailViewModel } from './kimiWikiPreviewViewModel'
import { KimiWikiCharacterDetailPage } from './KimiWikiCharacterDetailPage'

const media = (id: string, variant = ''): CharacterMediaViewModel => ({
  id,
  url: `https://media.test/${id}.webp`,
  title: id,
  mime: 'image/webp',
  role: id.startsWith('portrait') ? 'portrait' : 'skill',
  sectionKey: id.startsWith('portrait') ? 'portrait' : 'skill',
  displayOrder: 1,
  width: 1024,
  height: 1536,
  variant,
})

function character(): CharacterDetailViewModel {
  const initial = media('portrait-initial', 'initial')
  const insight = media('portrait-insight', 'insight')
  return {
    identity: {
      pageId: 'char:3003',
      entityId: '3003',
      name: '槲寄生',
      exonym: 'Druvis III',
      aliases: ['槲寄生', 'Druvis III'],
      category: '角色',
      route: '/wiki/char/3003',
      sourceTitle: 'Data:Char/3003.json',
      sourcePageid: 3003,
    },
    summary: '神秘学家艺术品，展出于20世纪初叶。',
    quote: '漫游于林间的术杖制造师。',
    location: 'Washington / Europe',
    archiveMetadata: { activeEra: '20th Century Early', birthday: 'Oct 23 (Autumn)' },
    udimoMedia: null,
    summaryCards: [
      { key: 'rarity', label: '稀有度', value: '5' },
      { key: 'profession', label: '职业', value: '3' },
      { key: 'damageType', label: 'DAMAGE_TYPE', value: 'Mental', detail: '精神创伤' },
      { key: 'inspiration', label: 'INSPIRATION', value: 'Plant', detail: '木' },
    ],
    profileRows: [
      { key: 'medium', label: '介质', value: '树木' },
      { key: 'stars', label: '星级', value: '✦✦✦✦✦✦' },
      { key: 'damageType', label: '伤害类型', value: 'Mental' },
    ],
    portraitStates: [
      { id: initial.id, label: '初始', variant: 'initial', description: '初始衣着', live2dMedia: null, portraitMedia: initial, backdrop: null },
      { id: insight.id, label: '洞悉', variant: 'insight', description: '洞悉本色', live2dMedia: null, portraitMedia: insight, backdrop: null },
    ],
    live2dAvailable: false,
    skills: [
      { id: 'skill-1', name: '风入林', kind: 'skill', description: '单体攻击', levels: [], image: media('skill-1') },
      { id: 'skill-2', name: '露渐白', kind: 'skill', description: '群体攻击', levels: [], image: media('skill-2') },
      { id: 'ultimate', name: '林间，静默将至', kind: 'ultimate', description: '至终的仪式', levels: [], image: media('ultimate') },
    ],
    inheritance: {
      title: '木秀于林',
      description: '',
      levels: [{ level: '洞悉 I', effect: '造成伤害提升。' }, { level: '洞悉 III', effect: '进入特殊状态。' }],
    },
    portray: {
      title: '塑造',
      description: '弯月与橡树。',
      levels: [{ level: 'LV.1', effect: '风入林提升。' }, { level: 'LV.5', effect: '穿透率提升。' }],
    },
    voices: [{
      id: 'voice-1',
      title: '初遇',
      languages: [{ code: 'zh-CN', label: '中文', text: '我是槲寄生。', audio: null }],
    }],
    cultureEntries: [{
      id: 'culture-1',
      ordinal: 1,
      title: '咆哮的1920年代',
      titleEn: 'Roaring Twenties',
      tags: [],
      paragraphs: ['文化档案正文。'],
    }],
    collectionGroups: [{
      id: 'collection-1',
      name: '熟识橡树之人',
      nameEn: 'The Druid',
      items: [{
        id: 'item-1',
        ordinal: 1,
        name: '1900橡木铃',
        nameEn: 'Lugus Samildánach',
        value: '20 纯雨滴',
        description: '百年纪念款。',
        image: media('collection-1'),
      }],
    }],
    technicalDossier: {
      contentVersion: 2,
      projectionVersion: 1,
      sourceTitle: 'Data:Char/3003.json',
      sourcePageid: 3003,
      route: '/wiki/char/3003',
    },
  }
}

const model: KimiWikiDetailViewModel = {
  character: character(),
  backdrop: {
    id: 'backdrop-library',
    url: 'https://media.test/backdrop.webp',
    title: '档案室背景',
    role: 'backdrop',
    variant: '',
  },
}

function setMobile(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(max-width: 760px)' ? matches : false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

describe('KimiWikiCharacterDetailPage', () => {
  beforeEach(() => setMobile(false))

  it('renders the approved desktop dossier geometry and all structured modules', () => {
    render(<KimiWikiCharacterDetailPage model={model} onBack={vi.fn()} />)

    expect(screen.getByTestId('kimi-desktop-character-dossier')).toBeInTheDocument()
    expect(screen.getByTestId('kimi-character-stage')).toHaveStyle({
      backgroundImage: 'url("https://media.test/backdrop.webp")',
    })
    expect(screen.getByText('木秀于林')).toBeInTheDocument()
    expect(screen.getByText('LV.5')).toBeInTheDocument()
    expect(screen.getAllByTestId('character-skill-card')).toHaveLength(3)
    expect(screen.getByText('咆哮的1920年代')).toBeInTheDocument()
    expect(screen.getByText('1900橡木铃')).toBeInTheDocument()
    const dossier = screen.getByTestId('kimi-desktop-character-dossier')
    const leftRail = dossier.querySelector('.kimi-desktop-character-dossier__left')
    expect(leftRail).toContainElement(screen.getByRole('navigation', { name: '详情页快捷操作' }))
  })

  it('keeps initial and insight portraits mutually exclusive and exposes disabled Live2D', () => {
    render(<KimiWikiCharacterDetailPage model={model} onBack={vi.fn()} />)

    const portraits = screen.getAllByTestId('kimi-character-portrait')
    expect(portraits[0]).toHaveClass('is-active')
    expect(portraits[1]).toHaveClass('is-inactive')
    fireEvent.click(screen.getByRole('button', { name: '切换到洞悉' }))
    expect(portraits[0]).toHaveClass('is-inactive')
    expect(portraits[1]).toHaveClass('is-active')
    expect(screen.getByRole('button', { name: 'Live2D 播放器未就绪' })).toBeDisabled()
  })

  it('switches the stage backdrop with the explicitly mapped crawler skin', () => {
    const skinnedModel: KimiWikiDetailViewModel = {
      ...model,
      character: {
        ...model.character,
        portraitStates: model.character.portraitStates.map((state, index) => ({
          ...state,
          backdrop: {
            ...media(index === 0 ? 'backdrop-initial' : 'backdrop-insight'),
            role: 'backdrop',
            sectionKey: 'backdrop',
          },
        })),
      },
    }

    render(<KimiWikiCharacterDetailPage model={skinnedModel} onBack={vi.fn()} />)

    const stage = screen.getByTestId('kimi-character-stage')
    expect(stage).toHaveStyle({
      backgroundImage: 'url("https://media.test/backdrop-initial.webp")',
    })

    const skinButtons = stage.querySelectorAll<HTMLButtonElement>('.kimi-character-stage__wardrobe [role="group"] button')
    fireEvent.click(skinButtons[1])

    expect(stage).toHaveStyle({
      backgroundImage: 'url("https://media.test/backdrop-insight.webp")',
    })
  })

  it('shows a character-local fallback when the active portrait fails without revealing another skin', () => {
    render(<KimiWikiCharacterDetailPage model={model} onBack={vi.fn()} />)

    const portraits = screen.getAllByTestId('kimi-character-portrait')
    fireEvent.error(portraits[0])
    expect(screen.getByLabelText('当前立绘加载失败')).toBeInTheDocument()
    expect(portraits[1]).toHaveClass('is-inactive')

    fireEvent.click(screen.getByRole('button', { name: '切换到洞悉' }))
    expect(screen.queryByLabelText('当前立绘加载失败')).not.toBeInTheDocument()
    expect(portraits[1]).toHaveClass('is-active')
  })

  it('renders the complete mobile document order with voice as the only nested scroll owner', () => {
    setMobile(true)
    render(<KimiWikiCharacterDetailPage model={model} onBack={vi.fn()} />)

    const mobile = screen.getByTestId('kimi-mobile-character-dossier')
    expect(screen.queryByTestId('kimi-desktop-character-dossier')).not.toBeInTheDocument()
    expect([...mobile.querySelectorAll('[data-mobile-module]')].map((item) => item.getAttribute('data-mobile-module'))).toEqual([
      'hero',
      'summary',
      'profile',
      'inheritance',
      'portray',
      'skills',
      'ultimate',
      'voices',
      'culture',
      'collection',
      'technical',
    ])
    expect(mobile.querySelectorAll('.character-detail__nested-scroll')).toHaveLength(1)
  })
})
