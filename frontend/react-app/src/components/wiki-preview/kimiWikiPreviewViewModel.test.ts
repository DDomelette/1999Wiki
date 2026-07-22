import { describe, expect, it } from 'vitest'
import type { WikiContentBlock, WikiPageDetail, WikiPageListItem } from '../../types/wiki'
import { buildWikiPageViewModel } from '../wiki/wikiViewModel'
import { buildKimiWikiPreviewViewModel, parseSelectionSummary } from './kimiWikiPreviewViewModel'

const block = (value: WikiContentBlock): WikiContentBlock => value

function pages(): WikiPageListItem[] {
  return [
    {
      pageId: 'char:3003',
      pageType: 'character',
      title: '槲寄生',
      subtitle: 'Druvis III',
      category: '角色',
      route: '/wiki/char/3003',
      thumbnail: 'https://media.test/thumb.webp',
      summary: '林间的神秘学家。',
    },
    {
      pageId: 'char:3004',
      pageType: 'character',
      title: '红弩箭',
      subtitle: 'Regulus',
      category: '角色',
      route: '/wiki/char/3004',
      thumbnail: 'file:///D:/private/red.webp',
      summary: '海上的摇滚船长。',
    },
  ]
}

function detail(): WikiPageDetail {
  return {
    ...pages()[0],
    sourcePageid: 3003,
    sourceTitle: 'Data:Char/3003.json',
    content: {
      contentVersion: 2,
      profile: {
        Name: '槲寄生',
        exonym: 'Druvis III',
        初始衣着: '酒会从来都不适合她。',
        洞悉本色: '她回到橡木树梢。',
      },
      blocks: [
        block({
          id: 'inheritance-title',
          type: 'heading',
          section: 'inheritance',
          mediaIds: [],
          text: '木秀于林',
        }),
        block({
          id: 'inheritance-levels',
          type: 'table',
          section: 'inheritance',
          mediaIds: [],
          rows: [['洞悉等级', '效果'], ['洞悉一', '造成伤害提升。']],
        }),
        block({
          id: 'portray-levels',
          type: 'table',
          section: 'portray',
          mediaIds: [],
          rows: [['塑造等级', '效果'], ['LV.1', '风入林获得提升。'], ['LV.5', '穿透率提升。']],
        }),
      ],
    },
    mediaLinks: [
      {
        mediaId: 'portrait-initial',
        assetType: 'portrait',
        role: 'portrait',
        variant: 'initial',
        url: 'https://media.test/initial.webp',
        title: '初始立绘',
        objectKey: 'reverse1999/private/initial.webp',
        local_relpath: 'D:/private/initial.webp',
      },
      {
        mediaId: 'portrait-insight',
        assetType: 'portrait',
        role: 'portrait',
        variant: 'insight',
        url: 'https://media.test/insight.webp',
        title: '洞悉立绘',
      },
      {
        mediaId: 'backdrop-library',
        assetType: 'image',
        role: 'backdrop',
        sectionKey: 'stage',
        url: 'https://media.test/backdrop.webp',
        title: '档案室背景',
        endpoint: 'http://minio:9000',
      },
      {
        mediaId: 'private-file',
        assetType: 'image',
        role: 'backdrop',
        url: 'file:///D:/private/backdrop.webp',
      },
    ],
    relations: [],
    linkSpans: [],
  }
}

describe('kimiWikiPreviewViewModel', () => {
  it('splits personnel summaries into labelled facts and readable paragraphs', () => {
    expect(parseSelectionSummary(
      'Druvis III Character Profile\nRarity: 5\nProfession: 3\nDamage Type: Mental\n\nA mystic artist active for twenty years. Lives in Europe.',
    )).toEqual({
      facts: [
        { label: 'Rarity', value: '5' },
        { label: 'Profession', value: '3' },
        { label: 'Damage Type', value: 'Mental' },
      ],
      paragraphs: [
        'A mystic artist active for twenty years.',
        'Lives in Europe.',
      ],
    })
  })

  it('builds a complete Kimi preview from the public Wiki DTO without leaking storage fields', () => {
    const result = buildKimiWikiPreviewViewModel(
      pages(),
      'char:3003',
      buildWikiPageViewModel(detail()),
    )

    expect(result.entries).toHaveLength(2)
    expect(result.selected).toMatchObject({
      pageId: 'char:3003',
      title: '槲寄生',
      canonicalRoute: '/wiki/char/3003',
      selected: true,
    })
    expect(result.selected?.portrait?.url).toBe('https://media.test/initial.webp')
    expect(result.selected?.backdrop?.url).toBe('https://media.test/backdrop.webp')
    expect(result.detail?.character.inheritance?.title).toBe('木秀于林')
    expect(result.detail?.character.portray?.levels.map((item) => item.level)).toEqual(['LV.1', 'LV.5'])
    expect(JSON.stringify(result)).not.toMatch(/objectKey|local_relpath|file:\/\/|minio:9000|endpoint/i)
  })

  it('rejects non-public media and does not carry a stale character detail across selection changes', () => {
    const invalid = detail()
    invalid.mediaLinks = invalid.mediaLinks.map((item) => ({ ...item, url: '/assets/private.webp' }))

    const invalidMedia = buildKimiWikiPreviewViewModel(
      pages(),
      'char:3003',
      buildWikiPageViewModel(invalid),
    )
    expect(invalidMedia.selected?.portrait).toBeNull()
    expect(invalidMedia.selected?.backdrop).toBeNull()

    const staleDetail = buildKimiWikiPreviewViewModel(
      pages(),
      'char:3004',
      buildWikiPageViewModel(detail()),
    )
    expect(staleDetail.selected?.pageId).toBe('char:3004')
    expect(staleDetail.selected?.portrait).toBeNull()
    expect(staleDetail.detail).toBeNull()
  })
})
