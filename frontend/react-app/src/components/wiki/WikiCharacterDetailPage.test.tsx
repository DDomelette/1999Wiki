import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CharacterDetailViewModel, CharacterMediaViewModel } from './characterDetailViewModel'
import { WikiCharacterDetailPage } from './WikiCharacterDetailPage'

const publicMedia = (id: string, role: string, url = `https://cdn.test/${id}.webp`): CharacterMediaViewModel => ({
  id,
  url,
  title: id,
  mime: role === 'voice' ? 'audio/mpeg' : 'image/webp',
  role,
  sectionKey: role,
  displayOrder: 1,
  width: 480,
  height: 900,
  variant: '',
})

function detailView(): CharacterDetailViewModel {
  const skillOne = publicMedia('skill-1', 'skill')
  const skillTwo = publicMedia('skill-2', 'skill')
  const ultimate = publicMedia('ultimate', 'skill')
  return {
    identity: {
      pageId: 'char:3003',
      entityId: '3003',
      name: '槲寄生',
      exonym: 'Druvis III',
      aliases: ['槲寄生', 'Druvis III'],
      category: '角色',
      route: '/wiki/character/3003',
      sourceTitle: 'Data:Char/3003.json',
      sourcePageid: 3003,
    },
    summary: '神秘学家艺术品，展出于20世纪初叶。',
    quote: '漫游于林间的术杖制造师，橡树与月亮的友人。',
    location: 'Washington / Europe',
    archiveMetadata: {
      activeEra: '20th Century Early',
      birthday: 'Oct 23 (Autumn)',
    },
    udimoMedia: publicMedia('udimo', 'udimo', 'https://cdn.test/udimo.png'),
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
      { key: 'birthday', label: '生日', value: '2024-10-23' },
      { key: 'position', label: '定位标签', value: '输出\n控制\n辅助' },
      { key: 'udimo', label: 'Udimo', value: '猫类' },
    ],
    portraitStates: [
      {
        id: 'initial',
        label: '初始',
        variant: 'initial',
        description: '初始衣着',
        live2dMedia: publicMedia('initial-live2d', 'stage_live2d'),
        portraitMedia: publicMedia('initial-portrait', 'stage_portrait'),
        backdrop: publicMedia('backdrop-initial', 'skin_background'),
      },
      {
        id: 'insight',
        label: '洞悉',
        variant: 'insight',
        description: '洞悉本色',
        live2dMedia: publicMedia('insight-live2d', 'stage_live2d'),
        portraitMedia: publicMedia('insight-portrait', 'stage_portrait'),
        backdrop: publicMedia('backdrop-insight', 'skin_background'),
      },
    ],
    live2dAvailable: false,
    skills: [
      { id: 'skill-1', name: '风入林', kind: 'skill', description: '单体攻击', levels: [{ level: '1', effect: '风在驱逐林中异客。' }], image: skillOne },
      { id: 'skill-2', name: '露渐白', kind: 'skill', description: '群体攻击', levels: [{ level: '1', effect: '白露与湿苔根植于此。' }], image: skillTwo },
      { id: 'ultimate', name: '林间，静默将至', kind: 'ultimate', description: '至终的仪式', levels: [], image: ultimate },
    ],
    inheritance: {
      title: '木秀于林',
      description: '',
      levels: [
        { level: '洞悉一', effect: '造成的伤害提升20%' },
        { level: '洞悉二', effect: '进入战斗时，造成伤害提升8%' },
        { level: '洞悉三', effect: '进入生生不息状态' },
      ],
    },
    portray: {
      title: '',
      description: '弯月与橡树教会了她如何倾听森林。',
      levels: Array.from({ length: 5 }, (_, index) => ({ level: `LV.${index + 1}`, effect: `塑造效果 ${index + 1}` })),
    },
    voices: [{
      id: 'voice-1',
      title: '初遇',
      languages: [
        { code: 'zh-CN', label: '中文', text: '我是槲寄生，很高兴认识你。', audio: publicMedia('voice-zh', 'voice', 'https://cdn.test/voice-zh.mp3') },
        { code: 'en', label: 'English', text: 'I am Druvis III.', audio: publicMedia('voice-en', 'voice', 'https://cdn.test/voice-en.mp3') },
      ],
    }],
    cultureEntries: Array.from({ length: 3 }, (_, index) => ({
      id: `culture-${index + 1}`,
      ordinal: index + 1,
      title: `文化档案 ${index + 1}`,
      titleEn: `Culture ${index + 1}`,
      tags: [],
      paragraphs: [`文化段落 ${index + 1}`],
    })),
    collectionGroups: [
      {
        id: 'group-1',
        name: '熟识橡树之人',
        nameEn: 'The Druid',
        items: Array.from({ length: 3 }, (_, index) => ({
          id: `collection-${index + 1}`,
          ordinal: index + 1,
          name: `藏品 ${index + 1}`,
          nameEn: `Item ${index + 1}`,
          value: '无估值',
          description: '藏品说明',
          image: publicMedia(`collection-${index + 1}`, 'collection_item'),
        })),
      },
      {
        id: 'group-2',
        name: '闹蛾儿',
        nameEn: "Lady With Nao'E",
        items: Array.from({ length: 3 }, (_, index) => ({
          id: `collection-${index + 4}`,
          ordinal: index + 4,
          name: `藏品 ${index + 4}`,
          nameEn: `Item ${index + 4}`,
          value: '20 纯雨滴',
          description: '藏品说明',
          image: publicMedia(`collection-${index + 4}`, 'collection_item'),
        })),
      },
    ],
    technicalDossier: {
      contentVersion: 2,
      projectionVersion: 1,
      sourceTitle: 'Data:Char/3003.json',
      sourcePageid: 3003,
      route: '/wiki/character/3003',
    },
  }
}

function setMobile(matches: boolean) {
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })))
}

describe('WikiCharacterDetailPage', () => {
  beforeEach(() => {
    setMobile(false)
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('mounts only the desktop dossier tree and keeps portrait states mutually exclusive', () => {
    const onBack = vi.fn()
    render(<WikiCharacterDetailPage viewModel={detailView()} onBack={onBack} />)

    expect(screen.getByTestId('desktop-character-dossier')).toBeInTheDocument()
    expect(screen.queryByTestId('mobile-character-dossier')).not.toBeInTheDocument()
    expect(screen.getByTestId('profile-skill-rail')).toHaveAttribute('data-scroll-owner', 'profile-skill-rail')
    expect(screen.getByTestId('inheritance-voice-rail')).toBeInTheDocument()
    expect(screen.getAllByTestId('character-skill-card')).toHaveLength(3)
    expect(screen.getAllByTestId('character-collection-item')).toHaveLength(6)
    expect(screen.getAllByTestId('character-voice-scroll')).toHaveLength(1)
    expect(screen.getByText('UDIMO')).toBeInTheDocument()
    expect(screen.getByTestId('character-identity-portrait')).toHaveAttribute('src', 'https://cdn.test/initial-portrait.webp')
    expect(screen.getByTestId('character-portrait-udimo-image')).toHaveAttribute('src', 'https://cdn.test/udimo.png')
    expect(screen.getByText('Medium:')).toBeInTheDocument()
    expect(screen.getByText('树木 (Trees)')).toBeInTheDocument()
    expect(screen.getByText('Damage Type:')).toBeInTheDocument()
    expect(screen.getByText('精神创伤 (Mental)')).toBeInTheDocument()
    expect(screen.getByText('Birthday:')).toBeInTheDocument()
    expect(screen.getByText('10-23 (Autumn)')).toBeInTheDocument()
    expect(screen.getByText('Tags:')).toBeInTheDocument()
    expect(screen.getByText('输出 / 控制 / 辅助')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'DEPLOY UNIT' })).toHaveAttribute('href', '#combat')
    expect(document.querySelector('#combat')).toBeInTheDocument()

    const portraits = screen.getAllByTestId('character-portrait-image')
    const stage = screen.getByTestId('character-portrait-stage')
    expect(stage).toHaveStyle({ backgroundImage: 'url("https://cdn.test/backdrop-initial.webp")' })
    expect(portraits[0]).toHaveAttribute('aria-hidden', 'false')
    expect(portraits[0]).toHaveAttribute('src', 'https://cdn.test/initial-live2d.webp')
    expect(portraits[0]).toHaveAttribute('data-portrait-mode', 'live2d')
    expect(portraits[1]).toHaveAttribute('aria-hidden', 'true')
    const insight = screen.getByRole('button', { name: '切换到洞悉' })
    expect(insight).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(insight)
    expect(insight).toHaveAttribute('aria-pressed', 'true')
    expect(stage).toHaveStyle({ backgroundImage: 'url("https://cdn.test/backdrop-insight.webp")' })
    expect(portraits[0]).toHaveAttribute('aria-hidden', 'true')
    expect(portraits[1]).toHaveAttribute('aria-hidden', 'false')
    expect(portraits[1]).toHaveAttribute('src', 'https://cdn.test/insight-live2d.webp')

    fireEvent.click(screen.getByRole('button', { name: '返回角色索引' }))
    expect(onBack).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('searchbox', { name: '搜索页面' })).not.toBeInTheDocument()
  })

  it('mounts only the mobile dossier tree in the approved continuous module order', () => {
    setMobile(true)
    const onBack = vi.fn()
    render(<WikiCharacterDetailPage viewModel={detailView()} onBack={onBack} />)

    const mobile = screen.getByTestId('mobile-character-dossier')
    expect(screen.queryByTestId('desktop-character-dossier')).not.toBeInTheDocument()
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
    expect(screen.getAllByTestId('character-voice-scroll')).toHaveLength(1)
    expect(mobile.querySelectorAll('.character-detail__nested-scroll')).toHaveLength(1)
    expect(screen.getByTestId('character-udimo-media')).toHaveAttribute('src', 'https://cdn.test/udimo.png')
    expect(screen.getByTestId('character-udimo-archive')).toHaveTextContent('20th Century Early')
    expect(screen.getByTestId('character-udimo-archive')).toHaveTextContent('Oct 23 (Autumn)')

    const navigation = screen.getByRole('navigation', { name: '移动档案导航' })
    expect(within(navigation).getByRole('button', { name: 'DOSSIER' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(within(navigation).getByRole('button', { name: 'ARCHIVE' }))
    expect(onBack).toHaveBeenCalledTimes(1)
    fireEvent.click(within(navigation).getByRole('button', { name: 'COMBAT' }))
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
  })

  it('toggles stage mode independently of skin selection and keeps the chosen mode across skins', () => {
    const onBack = vi.fn()
    render(<WikiCharacterDetailPage viewModel={detailView()} onBack={onBack} />)

    const portraits = screen.getAllByTestId('character-portrait-image')
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'false')
    expect(portraits[0]).toHaveAttribute('src', 'https://cdn.test/initial-live2d.webp')

    fireEvent.click(screen.getByRole('button', { name: '切换到立绘' }))
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'true')
    expect(portraits[0]).toHaveAttribute('src', 'https://cdn.test/initial-portrait.webp')
    expect(portraits[1]).toHaveAttribute('src', 'https://cdn.test/insight-portrait.webp')

    fireEvent.click(screen.getByRole('button', { name: '切换到洞悉' }))
    expect(portraits[1]).toHaveAttribute('aria-hidden', 'false')
    expect(portraits[1]).toHaveAttribute('src', 'https://cdn.test/insight-portrait.webp')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('falls back to portrait when a skin lacks live2d and restores live2d preference when available', () => {
    const view = detailView()
    view.portraitStates = [
      { ...view.portraitStates[0], live2dMedia: null },
      view.portraitStates[1],
    ]
    const onBack = vi.fn()
    render(<WikiCharacterDetailPage viewModel={view} onBack={onBack} />)

    const portraits = screen.getAllByTestId('character-portrait-image')
    expect(portraits[0]).toHaveAttribute('src', 'https://cdn.test/initial-portrait.webp')
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '切换到洞悉' }))
    expect(portraits[1]).toHaveAttribute('src', 'https://cdn.test/insight-live2d.webp')
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(screen.getByRole('button', { name: '切换到立绘' }))
    expect(portraits[1]).toHaveAttribute('src', 'https://cdn.test/insight-portrait.webp')
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '切换到初始' }))
    expect(portraits[0]).toHaveAttribute('src', 'https://cdn.test/initial-portrait.webp')
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('falls back to live2d when a skin lacks portrait and restores portrait when available', () => {
    const view = detailView()
    view.portraitStates = [
      { ...view.portraitStates[0], portraitMedia: null },
      view.portraitStates[1],
    ]
    const onBack = vi.fn()
    render(<WikiCharacterDetailPage viewModel={view} onBack={onBack} />)

    const portraits = screen.getAllByTestId('character-portrait-image')
    expect(portraits[0]).toHaveAttribute('src', 'https://cdn.test/initial-live2d.webp')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '切换到洞悉' }))
    expect(portraits[1]).toHaveAttribute('src', 'https://cdn.test/insight-live2d.webp')
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '切换到立绘' }))
    expect(portraits[1]).toHaveAttribute('src', 'https://cdn.test/insight-portrait.webp')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '切换到初始' }))
    expect(portraits[0]).toHaveAttribute('src', 'https://cdn.test/initial-live2d.webp')
    expect(screen.getByRole('button', { name: '切换到立绘' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '切换到立绘' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '切换到Live2D' })).toHaveAttribute('aria-pressed', 'true')
  })
})
