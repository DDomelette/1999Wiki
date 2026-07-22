import type { CategoryMeta } from '../../types'
import type { WikiCategoryItem } from '../../types/wiki'
import type { CardNavGroup } from '../animations/reactbits/CardNav'

const jump = (target: string) => () => document.querySelector(`[data-snap-section="${target}"]`)?.scrollIntoView({ behavior: 'smooth' })

export function mainNavigation(categories: CategoryMeta[]): CardNavGroup[] {
  return [
    { label: '页面', links: [{ label: '首页', action: jump('home') }, { label: '资料', action: jump('data') }, { label: '问答', action: jump('chat') }] },
    { label: '资料', links: categories.map((item) => ({ label: `${item.title} ${item.doc_count}`, action: jump(`data:${item.key}`) })) },
    { label: '项目', links: [{ label: '官方网站', href: 'https://re.bluepoch.com/home/' }, { label: '数据状态', href: '/health' }, { label: 'Wiki', href: '/wiki/character' }] },
  ]
}

export function wikiNavigation(categories: WikiCategoryItem[], onSelect?: (key: string) => void, anchors: ReadonlySet<string> = new Set(['content', 'media', 'info'])): CardNavGroup[] {
  const anchor = (key: string) => () => document.getElementById(`wiki-${key}`)?.scrollIntoView({ behavior: 'smooth' })
  return [
    { label: '浏览', links: [{ label: '全部', action: () => onSelect?.('') }, ...categories.map((item) => ({ label: `${item.label} ${item.count}`, action: () => onSelect?.(item.key) }))] },
    { label: '当前页面', links: [{ label: '正文', action: anchor('content'), disabled: !anchors.has('content') }, { label: '媒体', action: anchor('media'), disabled: !anchors.has('media') }, { label: '资料', action: anchor('info'), disabled: !anchors.has('info') }] },
    { label: '项目', links: [{ label: '首页', href: '/' }, { label: '问答', href: '/#chat' }, { label: '官方网站', href: 'https://re.bluepoch.com/home/' }] },
  ]
}
