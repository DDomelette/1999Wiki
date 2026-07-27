import { describe, expect, it } from 'vitest'
import type { WikiContentBlock, WikiMediaLink, WikiPageDetail } from '../../types/wiki'
import { buildCharacterDetailViewModel } from './characterDetailViewModel'
import { buildWikiPageViewModel } from './wikiViewModel'

const media = (overrides: Partial<WikiMediaLink> & Pick<WikiMediaLink, 'mediaId' | 'url'>): WikiMediaLink => ({
  assetId: overrides.mediaId,
  assetType: 'image',
  mime: 'image/webp',
  role: 'image',
  title: overrides.mediaId,
  ...overrides,
})

const block = (value: WikiContentBlock): WikiContentBlock => value

function character3003(): WikiPageDetail {
  const skillOne = 'media:sha1:c88f1562599e666f5b57a29e8fab51a8377de7cf'
  const skillTwo = 'media:sha1:f9afdf11b70bbee05b9c292f848724e9df852c9d'
  const ultimate = 'media:sha1:df152eba1b5ad70e8f5625feffd6daf18222c7df'
  const collectionMedia = Array.from({ length: 6 }, (_, index) => `collection-${index + 1}`)

  return {
    pageId: 'char:3003',
    pageType: 'character',
    title: '槲寄生',
    subtitle: 'Data:Char/3003.json',
    category: '角色',
    route: '/wiki/character/3003',
    summary: '神秘学家艺术品，展出于20世纪初叶。',
    sourcePageid: 3003,
    sourceTitle: 'Data:Char/3003.json',
    content: {
      contentVersion: 2,
      crawlerProjectionVersion: 1,
      profile: {
        Name: '槲寄生',
        exonym: 'Druvis III',
        aliases: ['槲寄生', 'Druvis III', '德鲁伊'],
        人物合辑: '神秘学家｜Arcanists',
        介质: '树木',
        星级: '✦✦✦✦✦✦',
        属性: '木｜Plant',
        角色灵感: '林间的渴慕[木] 术杖制作',
        伤害类型: '精神创伤',
        传承: '木秀于林',
        造像: '弯月与橡树教会了她如何倾听森林中所发生的一切。',
        银行彩色相片: '漫游于林间的术杖制造师，橡树与月亮的友人。',
        Udimo: '猫类',
        定位标签: ['输出', '控制', '辅助'],
        香调: ['木质调', '雪松', '晚香玉', '琥珀'],
        初始衣着: '酒会从来都是不适合她的。',
        洞悉本色: '她回到橡木树梢，像是回到母亲的怀抱。',
        生日: '2024-10-23',
      },
      blocks: [
        block({
          id: 'profile-facts',
          type: 'facts',
          section: 'profile',
          mediaIds: [],
          items: [
            { label: '稀有度', value: '5' },
            { label: '职业', value: '3' },
            { label: '伤害类型', value: '2' },
          ],
        }),
        block({
          id: 'dossier',
          type: 'paragraph',
          section: 'dossier',
          mediaIds: [],
          text: '神秘学家艺术品，展出于20世纪初叶，参展时长20年。原参展地点为美利坚合众国华盛顿州，后保藏于欧洲。',
        }),
        block({ id: 'skill-1-title', type: 'heading', section: 'skill', mediaIds: [skillOne], text: '风入林' }),
        block({
          id: 'skill-1-levels',
          type: 'table',
          section: 'skill',
          mediaIds: [skillOne],
          rows: [['星级', '效果'], ['1', '风在驱逐林中异客。'], ['2', '风在驱逐林中异客。有时，也会挽留。'], ['3', '风在驱逐林中异客。偶尔，挽留得更久。']],
        }),
        block({ id: 'skill-2-title', type: 'heading', section: 'skill', mediaIds: [skillTwo], text: '露渐白' }),
        block({
          id: 'skill-2-levels',
          type: 'table',
          section: 'skill',
          mediaIds: [skillTwo],
          rows: [['星级', '效果'], ['1', '白露与湿苔根植于此。'], ['2', '他们不应伤害你。'], ['3', '他们不应在林中伤害你。']],
        }),
        block({
          id: 'ultimate',
          type: 'paragraph',
          section: 'skill',
          mediaIds: [ultimate],
          text: '林间，静默将至\n至终的仪式: 林地茂盛之中环伺滋长。',
        }),
        block({ id: 'inheritance-title', type: 'heading', section: 'inheritance', mediaIds: [], text: '木秀于林' }),
        block({
          id: 'inheritance-levels',
          type: 'table',
          section: 'inheritance',
          mediaIds: [],
          rows: [['洞悉等级', '效果'], ['洞悉一', '造成的伤害提升20%'], ['洞悉二', '进入战斗时，造成伤害提升8%'], ['洞悉三', '木灵感角色进入生生不息状态']],
        }),
        block({
          id: 'portray-intro',
          type: 'paragraph',
          section: 'portray',
          mediaIds: [],
          text: '弯月与橡树教会了她如何倾听森林中所发生的一切。',
        }),
        block({
          id: 'portray-levels',
          type: 'table',
          section: 'portray',
          mediaIds: [],
          rows: [['塑造等级', '塑造效果'], ['LV.1', '风入林获得提升'], ['LV.2', '至终仪式获得提升'], ['LV.3', '露渐白获得提升'], ['LV.4', '至终仪式再次提升'], ['LV.5', '穿透率提升至40%']],
        }),
        block({
          id: 'voice-first',
          type: 'voice_reference',
          section: 'voice',
          mediaIds: ['voice-en-01', 'voice-zh-01'],
          title: '初遇',
          text: '初遇\n中文: 我是槲寄生，很高兴认识你。\nEN: I am Druvis III. It is my pleasure to meet you.',
        }),
        block({
          id: 'voice-first-duplicate',
          type: 'voice_reference',
          section: 'voice',
          mediaIds: ['voice-en-01', 'voice-zh-01'],
          title: '初遇',
          text: '初遇\n中文: 我是槲寄生，很高兴认识你。\nEN: I am Druvis III. It is my pleasure to meet you.',
        }),
        block({
          id: 'voice-weather',
          type: 'voice_reference',
          section: 'voice',
          mediaIds: ['voice-zh-02'],
          title: '箱中气候',
          text: '箱中气候\n中文: 水从泥土里去往天上，又从天上坠落地面。',
        }),
        ...[
          ['1900橡木铃', 'Lugus Samildánach', '20 纯雨滴', '熟识橡树之人', 'The Druid'],
          ['术杖“他方世界”', 'Otherworld', '无估值', '熟识橡树之人', 'The Druid'],
          ['一束槲寄生', 'Mistletoe', '无估值', '熟识橡树之人', 'The Druid'],
          ['捻金雪柳闹蛾冠', "Nao'E Willow Tiara", '400 利齿子儿', '闹蛾儿', "Lady With Nao'E"],
          ['璎珞腰饰', 'Yingluo Waist Jewelry', '85 利齿子儿', '闹蛾儿', "Lady With Nao'E"],
          ['青白银绣披帛', 'Silver Embroidery Pibo', '34 利齿子儿', '闹蛾儿', "Lady With Nao'E"],
        ].map(([name, nameEn, value, group, groupEn], index) => block({
          id: `collection-${index + 1}`,
          type: 'structured',
          section: 'collection',
          mediaIds: [],
          kind: 'collection_item',
          ordinal: index + 1,
          name,
          nameEn,
          value,
          group,
          groupEn,
          description: `藏品 ${index + 1} 的真实说明。`,
        })),
        ...[
          ['咆哮的1920年代', 'Roaring Twenties'],
          ['喀斯卡特的秋天', 'Autumn in Cascade'],
          ['她的世界 有另一种哲学', ''],
        ].map(([title, titleEn], index) => block({
          id: `culture-${index + 1}`,
          type: 'structured',
          section: 'culture_dossier',
          mediaIds: [],
          kind: 'culture_entry',
          ordinal: index + 1,
          title,
          titleEn,
          tags: index === 2 ? ['UTTU×槲寄生'] : [],
          paragraphs: [`文化档案 ${index + 1} 第一段。`, `文化档案 ${index + 1} 第二段。`],
        })),
      ],
    },
    mediaLinks: [
      media({ mediaId: 'portrait-a', assetType: 'portrait', role: 'portrait', sectionKey: 'portrait', displayOrder: 1, url: 'https://cdn.test/portrait-a.webp' }),
      media({ mediaId: 'portrait-b', assetType: 'portrait', role: 'portrait', sectionKey: 'portrait', displayOrder: 2, url: 'https://cdn.test/portrait-b.webp' }),
      media({ mediaId: 'udimo', assetType: 'image', role: 'udimo', sectionKey: 'summary', displayOrder: 1, variant: 'udimo', url: 'https://cdn.test/udimo.png' }),
      media({ mediaId: skillOne, assetType: 'skill', role: 'skill', sectionKey: 'skill', url: 'https://cdn.test/skill-1.webp' }),
      media({ mediaId: skillTwo, assetType: 'skill', role: 'skill', sectionKey: 'skill', url: 'https://cdn.test/skill-2.webp' }),
      media({ mediaId: ultimate, assetType: 'skill', role: 'skill', sectionKey: 'skill', url: 'https://cdn.test/ultimate.webp' }),
      media({ mediaId: 'voice-en-01', assetType: 'voice', role: 'voice', mime: 'audio/mpeg', title: '文件:En play mianvoc hero3003 01.mp3', url: 'https://cdn.test/voice-en-01.mp3' }),
      media({ mediaId: 'voice-zh-01', assetType: 'voice', role: 'voice', mime: 'audio/mpeg', title: '文件:Zh play mianvoc hero3003 01.mp3', url: 'https://cdn.test/voice-zh-01.mp3' }),
      media({ mediaId: 'voice-zh-02', assetType: 'voice', role: 'voice', mime: 'audio/mpeg', title: '文件:Zh play mianvoc hero3003 02.mp3', url: 'https://cdn.test/voice-zh-02.mp3' }),
      ...collectionMedia.map((mediaId, index) => media({
        mediaId,
        assetType: 'image',
        role: 'collection_item',
        sectionKey: 'collection',
        displayOrder: index + 1,
        variant: `collection-${String(index + 1).padStart(2, '0')}`,
        url: `https://cdn.test/collection-${index + 1}.webp`,
      })),
    ],
    relations: [],
    linkSpans: [],
  }
}

describe('characterDetailViewModel', () => {
  it('retains production same-origin portrait media for crawler skins', () => {
    const live2dUrl = '/media/reverse1999-assets/reverse1999/portrait/aa/live2d.webp'
    const portraitUrl = '/media/reverse1999-assets/reverse1999/portrait/bb/portrait.webp'
    const page = character3003()
    page.content.skins = [{
      id: '300301',
      name: 'Initial Archive',
      mediaIds: {
        stage_live2d: 'char:3003/crawler:stage_live2d:300301',
        stage_portrait: 'char:3003/crawler:stage_portrait:300301',
      },
    }]
    page.mediaLinks = [
      media({
        mediaId: 'live2d-resource',
        role: 'stage_live2d',
        skinId: '300301',
        url: live2dUrl,
      }),
      media({
        mediaId: 'portrait-resource',
        role: 'stage_portrait',
        skinId: '300301',
        url: portraitUrl,
      }),
    ]

    const view = buildCharacterDetailViewModel(buildWikiPageViewModel(page))

    expect(view.portraitStates).toHaveLength(1)
    expect(view.portraitStates[0].live2dMedia?.url).toBe(live2dUrl)
    expect(view.portraitStates[0].portraitMedia?.url).toBe(portraitUrl)
  })

  it('maps the real 3003-shaped detail into every approved dossier module without mutation', () => {
    const page = character3003()
    const before = JSON.stringify(page)

    const view = buildCharacterDetailViewModel(buildWikiPageViewModel(page))

    expect(view.identity).toMatchObject({
      entityId: '3003',
      name: '槲寄生',
      exonym: 'Druvis III',
      sourceTitle: 'Data:Char/3003.json',
    })
    expect(view.summaryCards).toEqual([
      { key: 'rarity', label: '稀有度', value: '5' },
      { key: 'profession', label: '职业', value: '3' },
      { key: 'damageType', label: 'DAMAGE_TYPE', value: 'Mental', detail: '精神创伤' },
      { key: 'inspiration', label: 'INSPIRATION', value: 'Plant', detail: '木' },
    ])
    expect(view.location).toBe('美利坚合众国华盛顿州 / 欧洲')
    expect(view.archiveMetadata).toEqual({
      activeEra: '20th Century Early',
      birthday: 'Oct 23 (Autumn)',
    })
    expect(view.udimoMedia?.id).toBe('udimo')
    expect(view.portraitStates.map((item) => [item.label, item.variant])).toEqual([
      ['立绘 1', 'unclassified'],
      ['立绘 2', 'unclassified'],
    ])
    expect(view.skills.map((item) => [item.name, item.kind, item.image?.id])).toEqual([
      ['风入林', 'skill', 'media:sha1:c88f1562599e666f5b57a29e8fab51a8377de7cf'],
      ['露渐白', 'skill', 'media:sha1:f9afdf11b70bbee05b9c292f848724e9df852c9d'],
      ['林间，静默将至', 'ultimate', 'media:sha1:df152eba1b5ad70e8f5625feffd6daf18222c7df'],
    ])
    expect(view.skills[0].levels).toHaveLength(3)
    expect(view.inheritance).toMatchObject({ title: '木秀于林' })
    expect(view.inheritance?.levels).toHaveLength(3)
    expect(view.portray?.levels).toHaveLength(5)
    expect(view.voices.map((item) => item.title)).toEqual(['初遇', '箱中气候'])
    expect(view.voices[0].languages.map((item) => item.code)).toEqual(['zh-CN', 'en'])
    expect(view.cultureEntries).toHaveLength(3)
    expect(view.collectionGroups.map((group) => [group.name, group.items.length])).toEqual([
      ['熟识橡树之人', 3],
      ['闹蛾儿', 3],
    ])
    expect(view.collectionGroups.flatMap((group) => group.items).map((item) => item.image?.id)).toEqual([
      'collection-1', 'collection-2', 'collection-3', 'collection-4', 'collection-5', 'collection-6',
    ])
    expect(view.technicalDossier).toMatchObject({
      contentVersion: 2,
      projectionVersion: 1,
    })
    expect(JSON.stringify(page)).toBe(before)
  })

  it('honours explicit initial and insight variants and omits unavailable optional modules', () => {
    const page = character3003()
    page.mediaLinks = page.mediaLinks.slice(0, 2).map((item, index) => ({
      ...item,
      variant: index === 0 ? 'initial' : 'insight',
    }))
    page.content.blocks = []

    const view = buildCharacterDetailViewModel(buildWikiPageViewModel(page))

    expect(view.portraitStates.map((item) => [item.label, item.variant, item.description])).toEqual([
      ['初始', 'initial', '酒会从来都是不适合她的。'],
      ['洞悉', 'insight', '她回到橡木树梢，像是回到母亲的怀抱。'],
    ])
    expect(view.skills).toEqual([])
    expect(view.inheritance).toBeNull()
    expect(view.portray).toBeNull()
    expect(view.voices).toEqual([])
    expect(view.cultureEntries).toEqual([])
    expect(view.collectionGroups).toEqual([])
    expect(JSON.stringify(view)).not.toContain('undefined')
  })

  it('preserves crawler skin order and keeps live2d and portrait media separate with explicit backdrop', () => {
    const page = character3003()
    page.content.skins = [
      {
        id: '300301',
        name: 'Initial Archive',
        description: 'initial description',
        mediaIds: {
          stage_live2d: 'skin-1-live',
          stage_portrait: 'skin-1-portrait',
        },
      },
      {
        id: '300302',
        name: 'Insight Archive',
        description: 'insight description',
        mediaIds: {
          stage_live2d: 'skin-2-live',
          stage_portrait: 'skin-2-portrait',
          skin_background: 'skin-2-bg',
        },
      },
      {
        id: '300303',
        name: 'Named Skin',
        description: 'named skin description',
        mediaIds: {
          stage_live2d: 'skin-3-live',
          stage_portrait: 'skin-3-portrait',
          skin_background: 'skin-3-bg',
        },
      },
    ]
    page.mediaLinks = [
      ...['1', '2', '3'].flatMap((skin) => [
        media({
          mediaId: `skin-${skin}-live`,
          assetType: 'portrait',
          role: 'stage_live2d',
          sectionKey: 'stage',
          url: `https://cdn.test/skin-${skin}-live.webp`,
        }),
        media({
          mediaId: `skin-${skin}-portrait`,
          assetType: 'portrait',
          role: 'stage_portrait',
          sectionKey: 'stage',
          url: `https://cdn.test/skin-${skin}-portrait.webp`,
        }),
      ]),
      media({ mediaId: 'skin-2-bg', role: 'skin_background', url: 'https://cdn.test/skin-2-bg.webp' }),
      media({ mediaId: 'skin-3-bg', role: 'skin_background', url: 'https://cdn.test/skin-3-bg.webp' }),
    ]

    const view = buildCharacterDetailViewModel(buildWikiPageViewModel(page))

    expect(view.portraitStates.map((item) => [
      item.id,
      item.label,
      item.variant,
      item.live2dMedia?.id ?? '',
      item.portraitMedia?.id ?? '',
      item.backdrop?.id ?? '',
    ])).toEqual([
      ['skin-1-live', 'Initial Archive', 'initial', 'skin-1-live', 'skin-1-portrait', ''],
      ['skin-2-live', 'Insight Archive', 'insight', 'skin-2-live', 'skin-2-portrait', 'skin-2-bg'],
      ['skin-3-live', 'Named Skin', 'unclassified', 'skin-3-live', 'skin-3-portrait', 'skin-3-bg'],
    ])
  })

  it('falls back to portrait id when live2d media id is missing for a skin', () => {
    const page = character3003()
    page.content.skins = [
      {
        id: '300301',
        name: 'Initial Archive',
        mediaIds: {
          stage_live2d: 'missing-live',
          stage_portrait: 'skin-1-portrait',
        },
      },
    ]
    page.mediaLinks = [
      media({ mediaId: 'skin-1-portrait', role: 'stage_portrait', url: 'https://cdn.test/skin-1-portrait.webp' }),
    ]

    const view = buildCharacterDetailViewModel(buildWikiPageViewModel(page))

    expect(view.portraitStates).toHaveLength(1)
    expect(view.portraitStates[0].id).toBe('skin-1-portrait')
    expect(view.portraitStates[0].live2dMedia).toBeNull()
    expect(view.portraitStates[0].portraitMedia?.id).toBe('skin-1-portrait')
  })

  it('ignores headicon and roster_avatar media when building portrait states from legacy portraits', () => {
    const page = character3003()
    page.content.skins = undefined
    page.mediaLinks = [
      media({ mediaId: 'headicon', role: 'headicon', url: 'https://cdn.test/headicon.webp' }),
      media({ mediaId: 'roster_avatar', role: 'roster_avatar', url: 'https://cdn.test/roster_avatar.webp' }),
      media({ mediaId: 'portrait-a', role: 'portrait', url: 'https://cdn.test/portrait-a.webp' }),
    ]

    const view = buildCharacterDetailViewModel(buildWikiPageViewModel(page))

    expect(view.portraitStates.map((item) => item.portraitMedia?.id)).toEqual(['portrait-a'])
    expect(view.portraitStates.every((item) => item.live2dMedia === null)).toBe(true)
  })
})
