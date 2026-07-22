import { describe, expect, it } from 'vitest'
import type { WikiContentBlock, WikiMediaLink, WikiPageDetail } from '../../types/wiki'
import { buildCharacterDetailViewModel } from './characterDetailViewModel'
import { buildWikiPageViewModel } from './wikiViewModel'

const contentBlock = (value: WikiContentBlock): WikiContentBlock => value

function v3Media(
  token: string,
  role: string,
  title: string,
  displayOrder: number,
  extras: Partial<WikiMediaLink> = {},
): WikiMediaLink {
  return {
    bindingId: `binding:sha256:${displayOrder.toString().padStart(64, '0')}`,
    resourceId: `resource:sha256:${(displayOrder + 100).toString().padStart(64, '0')}`,
    mediaId: `media:sha1:${displayOrder.toString().padStart(40, '0')}`,
    assetType: role === 'voice' ? 'voice' : 'image',
    mime: role === 'voice' ? 'audio/mpeg' : 'image/webp',
    role,
    title,
    sectionKey: role === 'collection_item' ? 'collection' : role === 'udimo' ? 'udimo' : 'profile',
    sourceBindingToken: token,
    displayOrder,
    url: `https://cdn.test/v3-${displayOrder}.${role === 'voice' ? 'mp3' : 'webp'}`,
    ...extras,
  }
}

function v3Character(): WikiPageDetail {
  return {
    pageId: 'char:9001',
    pageType: 'character',
    title: 'Test Character',
    subtitle: 'Data:Char/9001.json',
    category: 'character',
    route: '/wiki/character/9001',
    summary: 'A v3 projection fixture.',
    sourcePageid: 9001,
    sourceTitle: 'Data:Char/9001.json',
    content: {
      contentVersion: 3,
      crawlerProjectionVersion: 3,
      profile: { Name: 'Test Character', exonym: 'Tester' },
      skins: [
        {
          id: '900101',
          name: 'Initial',
          mediaIds: {
            stage_live2d: 'char:9001/crawler:stage_live2d:900101',
            stage_portrait: 'char:9001/crawler:stage_portrait:900101',
          },
        },
        {
          id: '900102',
          name: 'Insight',
          mediaIds: {
            stage_live2d: 'char:9001/crawler:stage_live2d:900102',
            stage_portrait: 'char:9001/crawler:stage_portrait:900102',
            skin_background: 'char:9001/crawler:skin_background:900102',
          },
        },
      ],
      blocks: [
        contentBlock({ id: 'skill-1-title', type: 'heading', section: 'skill', mediaIds: [], text: 'Skill One' }),
        contentBlock({
          id: 'skill-1-table',
          type: 'table',
          section: 'skill',
          mediaIds: [],
          rows: [['Level', 'Effect'], ['1', 'First effect']],
        }),
        contentBlock({
          id: 'ultimate',
          type: 'paragraph',
          section: 'skill',
          mediaIds: [],
          text: 'Ultimate One\nUltimate: Final effect',
        }),
        contentBlock({
          id: 'voice-greeting',
          type: 'voice_reference',
          section: 'voice',
          mediaIds: [],
          title: 'Greeting',
          text: 'Greeting\nEN: Hello from v3.',
        }),
        contentBlock({
          id: 'collection-one',
          type: 'structured',
          section: 'collection',
          mediaIds: ['char:9001/crawler:collection_item:2:900101'],
          kind: 'collection_item',
          ordinal: 1,
          group: 'Collection',
          name: 'Keepsake',
          description: 'A linked item.',
        }),
      ],
    },
    mediaLinks: [
      v3Media('skin:900101:live2d', 'stage_live2d', 'Initial', 1, { skinId: '900101' }),
      v3Media('skin:900101:verticalDrawing', 'stage_portrait', 'Initial', 2, { skinId: '900101' }),
      v3Media('skin:900102:live2d', 'stage_live2d', 'Insight', 3, { skinId: '900102' }),
      v3Media('skin:900102:drawing', 'stage_portrait', 'Insight', 4, { skinId: '900102' }),
      v3Media('skin:900102:live2dbg', 'skin_background', 'Insight backdrop', 5, { skinId: '900102' }),
      v3Media('skill:90010111:90010111', 'skill', 'Skill One', 6, { sectionKey: 'skills' }),
      v3Media('ultimate:90010131:90010131', 'skill', 'Ultimate One', 7, { sectionKey: 'skills' }),
      v3Media('voice:9001:greeting:en', 'voice', 'Greeting', 8, { sectionKey: 'voice', language: 'en' }),
      v3Media('collection:2:900101', 'collection_item', 'Keepsake', 9),
      v3Media('udimo:id-test', 'udimo', 'Udimo', 10),
    ],
    relations: [],
    linkSpans: [],
  }
}

describe('character detail media v3 projection', () => {
  it('resolves binding tokens and semantic media without legacy block media ids', () => {
    const view = buildCharacterDetailViewModel(buildWikiPageViewModel(v3Character()))

    expect(view.portraitStates).toHaveLength(2)
    expect(view.portraitStates[0]).toMatchObject({
      label: 'Initial',
      live2dMedia: { role: 'stage_live2d', skinId: '900101' },
      portraitMedia: { role: 'stage_portrait', skinId: '900101' },
    })
    expect(view.portraitStates[1]).toMatchObject({
      label: 'Insight',
      live2dMedia: { role: 'stage_live2d', skinId: '900102' },
      portraitMedia: { role: 'stage_portrait', skinId: '900102' },
      backdrop: { role: 'skin_background', skinId: '900102' },
    })
    expect(view.skills.map((item) => [item.name, item.kind, item.image?.title])).toEqual([
      ['Skill One', 'skill', 'Skill One'],
      ['Ultimate One', 'ultimate', 'Ultimate One'],
    ])
    expect(view.voices[0].languages[0]).toMatchObject({
      code: 'en',
      audio: { role: 'voice', language: 'en' },
    })
    expect(view.collectionGroups[0].items[0].image).toMatchObject({
      role: 'collection_item',
      sourceBindingToken: 'collection:2:900101',
    })
    expect(view.udimoMedia).toMatchObject({ role: 'udimo', sectionKey: 'udimo' })
  })
})
