import { describe, expect, it } from 'vitest'
import type { WikiContentBlock, WikiPageDetail, WikiPageListItem } from '../../types/wiki'
import {
  buildFallbackBlocks,
  buildWikiIndexItem,
  buildWikiPageViewModel,
  isPublicHttpUrl,
} from './wikiViewModel'

const block = (id: string, section: string): WikiContentBlock => ({
  id,
  type: 'paragraph',
  section,
  mediaIds: [],
  text: id,
})

function detail(): WikiPageDetail {
  return {
    pageId: 'char:3003',
    pageType: 'character',
    title: '槲寄生',
    subtitle: 'Data:Char/3003.json',
    category: '角色',
    route: '/wiki/char/3003',
    summary: '角色摘要。',
    content: {
      body: '备用正文。',
      profile: {
        介质: '树木',
        属性: ['木', '精神'],
        角色灵感: '林间的渴慕',
        伤害类型: '精神创伤',
        传承: '木秀于林',
        定位标签: ['控制', '输出'],
        香调: '木质调',
        初始衣着: '初始衣着描述',
        空字段: '',
      },
      blocks: [
        block('profile', 'profile'),
        block('skill', 'skill'),
        block('ultimate', 'ultimate'),
        block('inheritance', 'inheritance'),
        block('portray', 'portray'),
        block('voice', 'voice'),
        block('dossier', 'dossier'),
        block('culture', 'culture'),
        block('item', 'item'),
        block('unknown', 'timeline'),
      ],
    },
    mediaLinks: [
      { mediaId: 'initial', role: 'initial_portrait', assetType: 'portrait', url: 'https://cdn.test/initial.webp', title: '初始立绘：槲寄生' },
      { mediaId: 'generic-p', role: 'portrait', assetType: 'portrait', url: 'https://cdn.test/l2d_static_300301_p.webp', title: 'L2d static-300301_p.webp' },
      { mediaId: 'numeric', role: 'portrait', assetType: 'portrait', url: 'https://cdn.test/300302.webp', title: '300302.webp' },
      { mediaId: 'insight', role: 'portrait_insight', assetType: 'portrait', url: 'https://cdn.test/insight.webp', title: '洞悉立绘：槲寄生' },
      { mediaId: 'image', role: 'image', assetType: 'image', mime: 'image/webp', url: 'https://cdn.test/archive.webp', title: '档案图' },
      { mediaId: 'voice', role: 'voice', assetType: 'voice', mime: 'audio/mpeg', url: 'https://cdn.test/voice.mp3', title: '语音' },
      { mediaId: 'local', role: 'portrait', assetType: 'portrait', url: 'D:\\vault\\portrait.webp', title: '本地文件' },
    ],
    relations: [{ relation: 'ally' }],
    linkSpans: [{ text: '维尔汀', targetRoute: '/wiki/character/vertin' }],
    sourcePageid: 3003,
    sourceTitle: 'Data:Char/3003.json',
  }
}

describe('wikiViewModel', () => {
  it('builds a safe index item without inventing a route', () => {
    const page: WikiPageListItem = {
      pageId: 'char:3003',
      pageType: 'character',
      title: '槲寄生',
      subtitle: 'Data:Char/3003.json',
      category: '角色',
      route: '/wiki/character/3003',
      thumbnail: 'file:///portrait.webp',
    }

    expect(buildWikiIndexItem(page)).toEqual({
      pageId: 'char:3003',
      title: '槲寄生',
      meta: '角色 · Data:Char/3003.json',
      thumbnail: '',
      route: '/wiki/character/3003',
    })
  })

  it('rejects audio URLs from the image-only index thumbnail contract', () => {
    const page: WikiPageListItem = {
      pageId: 'char:3004',
      pageType: 'character',
      title: '红弩箭',
      subtitle: 'Data:Char/3004.json',
      category: '角色',
      route: '/wiki/character/3004',
      thumbnail: 'http://127.0.0.1:9002/reverse1999-assets/reverse1999/voice/a.mp3',
    }

    expect(buildWikiIndexItem(page).thumbnail).toBe('')
  })

  it('maps explicit portrait semantics, public media, fields, and sections without mutation', () => {
    const page = detail()
    const before = JSON.stringify(page)

    const view = buildWikiPageViewModel(page)

    expect(view.portraitSlots.initial?.id).toBe('initial')
    expect(view.portraitSlots.insight?.id).toBe('insight')
    expect(view.portraits.find((item) => item.title.includes('_p'))?.variant).toBe('unspecified')
    expect(view.portraits.find((item) => item.title === '300302.webp')?.variant).toBe('unspecified')
    expect(view.primaryMedia?.id).toBe('initial')
    expect(view.live2dAvailable).toBe(false)
    expect(view.voices).toHaveLength(1)
    expect(view.portraits.some((item) => item.id === 'local')).toBe(false)
    expect(view.profileFacts).toEqual([
      { label: '介质', value: '树木' },
      { label: '属性', value: '木\n精神' },
      { label: '角色灵感', value: '林间的渴慕' },
      { label: '伤害类型', value: '精神创伤' },
      { label: '传承', value: '木秀于林' },
      { label: '定位标签', value: '控制\n输出' },
      { label: '香调', value: '木质调' },
      { label: '初始衣着', value: '初始衣着描述' },
    ])
    expect(view.dossier).toContainEqual({ label: 'Aliases', value: '无' })
    expect(view.dossier).toContainEqual({ label: 'Route', value: '/wiki/char/3003', href: '/wiki/char/3003' })
    expect(view.blocks.map((item) => item.id)).toContain('inheritance')
    expect(view.characterSections.skills.map((item) => item.id)).toEqual(['skill', 'ultimate'])
    expect(view.characterSections.inheritance.map((item) => item.id)).toEqual(['inheritance'])
    expect(view.characterSections.portray.map((item) => item.id)).toEqual(['portray'])
    expect(view.characterSections.archive.map((item) => item.id)).toEqual(['dossier', 'culture', 'item'])
    expect(view.characterSections.remainder.map((item) => item.id)).toEqual(['unknown'])
    expect(JSON.stringify(page)).toBe(before)
  })

  it('keeps voice out of the primary image and uses a generic portrait before insight', () => {
    const page = detail()
    page.mediaLinks = page.mediaLinks.filter((item) => item.mediaId !== 'initial')

    const view = buildWikiPageViewModel(page)

    expect(view.primaryMedia?.id).toBe('generic-p')
    expect(view.primaryMedia?.kind).toBe('portrait')
  })

  it('keeps roster avatars out of the character stage while retaining portrait and Live2D stills', () => {
    const page = detail()
    page.mediaLinks = [
      {
        mediaId: 'roster-avatar',
        role: 'roster_avatar',
        assetType: 'portrait',
        variant: 'initial',
        url: 'https://cdn.test/headicon-large.webp',
        title: '角色大头像',
      },
      {
        mediaId: 'live2d-still',
        role: 'portrait',
        assetType: 'portrait',
        url: 'https://cdn.test/l2d-static.webp',
        title: 'L2d static-300701.webp',
      },
      {
        mediaId: 'portrait',
        role: 'portrait',
        assetType: 'portrait',
        url: 'https://cdn.test/portrait.webp',
        title: 'Portrait-300701.webp',
      },
    ]

    const view = buildWikiPageViewModel(page)

    expect(view.portraits.map((item) => item.id)).toEqual(['live2d-still', 'portrait'])
    expect(view.primaryMedia?.id).toBe('live2d-still')
  })

  it('uses v3 binding identity so shared resources remain separate render items', () => {
    const page = detail()
    page.mediaLinks = [
      {
        bindingId: `binding:sha256:${'1'.repeat(64)}`,
        resourceId: `resource:sha256:${'a'.repeat(64)}`,
        mediaId: `media:sha1:${'b'.repeat(40)}`,
        role: 'image',
        assetType: 'image',
        url: 'https://cdn.test/shared.webp',
        title: '共享资源 A',
      },
      {
        bindingId: `binding:sha256:${'2'.repeat(64)}`,
        resourceId: `resource:sha256:${'a'.repeat(64)}`,
        mediaId: `media:sha1:${'b'.repeat(40)}`,
        role: 'image',
        assetType: 'image',
        url: 'https://cdn.test/shared.webp',
        title: '共享资源 B',
      },
    ]

    const view = buildWikiPageViewModel(page)

    expect(view.images.map((item) => item.id)).toEqual([
      `binding:sha256:${'1'.repeat(64)}`,
      `binding:sha256:${'2'.repeat(64)}`,
    ])
  })

  it('deduplicates equivalent content blocks and merges their media references', () => {
    const page = detail()
    page.content.blocks = [
      { id: 'profile-a', type: 'heading', section: 'profile', mediaIds: [], text: '角色资料' },
      { id: 'profile-b', type: 'heading', section: 'profile', mediaIds: [], text: '角色资料' },
      { id: 'voice-a', type: 'voice_reference', section: 'voice', mediaIds: ['zh'], text: '初遇' },
      { id: 'voice-b', type: 'voice_reference', section: 'voice', mediaIds: ['en', 'zh'], text: '初遇' },
    ]

    const view = buildWikiPageViewModel(page)

    expect(view.characterSections.profile).toHaveLength(1)
    expect(view.characterSections.voices).toHaveLength(1)
    expect(view.characterSections.voices[0].mediaIds).toEqual(['zh', 'en'])
  })

  it('builds conservative fallback blocks from headings, fields, paragraphs, and long sentences', () => {
    const long = `${'甲'.repeat(120)}。${'乙'.repeat(120)}！${'丙'.repeat(60)}？`
    const blocks = buildFallbackBlocks(`# 标题\n\n介质：树木\n\n普通段落。\n\n${long}`)

    expect(blocks[0]).toMatchObject({ type: 'heading', text: '标题' })
    expect(blocks[1]).toMatchObject({ type: 'facts', items: [{ label: '介质', value: '树木' }] })
    expect(blocks.some((item) => item.type === 'paragraph' && item.text === '普通段落。')).toBe(true)
    expect(blocks.filter((item) => item.type === 'paragraph' && item.text !== '普通段落。').length).toBeGreaterThan(1)
    expect(blocks.every((item) => !/技能|稀有度|阵营/.test(item.section))).toBe(true)
  })

  it('accepts only public HTTP media URLs', () => {
    expect(isPublicHttpUrl('https://cdn.test/a.webp')).toBe(true)
    expect(isPublicHttpUrl('http://127.0.0.1:9002/a.webp')).toBe(true)
    expect(isPublicHttpUrl('file:///a.webp')).toBe(false)
    expect(isPublicHttpUrl('D:\\a.webp')).toBe(false)
    expect(isPublicHttpUrl(null)).toBe(false)
  })
})
