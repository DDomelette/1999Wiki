import type { CategoryMeta } from '../../types'
import type { WikiCategoryItem } from '../../types/wiki'
import type { CardNavGroup } from '../animations/reactbits/CardNav'
import { navigateToMainSection } from '../../navigation/mainSectionNavigation'
import type { MainRouteTarget } from '../../navigation/mainSectionNavigation'

const mainAction = (target: MainRouteTarget) => () => {
  const behavior: ScrollBehavior =
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      ? 'auto'
      : 'smooth'
  navigateToMainSection(target, { behavior, history: 'push' })
}

export function mainNavigation(categories: CategoryMeta[]): CardNavGroup[] {
  return [
    { label: '页面', links: [{ label: '首页', action: mainAction({ kind: 'home' }) }, { label: '资料', action: mainAction({ kind: 'data' }) }, { label: '问答', action: mainAction({ kind: 'chat' }) }] },
    { label: '资料', links: categories.map((item) => ({ label: `${item.title} ${item.doc_count}`, action: mainAction({ kind: 'data', categoryKey: item.key }) })) },
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
