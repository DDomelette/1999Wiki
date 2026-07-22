import { useState } from 'react'
import type { WikiCategoryItem } from '../../types/wiki'
import { useUIStore } from '../../store/uiStore'
import { ThemeToggle } from '../ui/ThemeToggle'
import { CardNav } from '../animations/reactbits/CardNav'
import { mainNavigation, wikiNavigation } from './navigationConfig'
import type { RecentWikiPage } from './recentWiki'

export type NavMode = 'main' | 'wiki'
export interface RouteAwareCardNavProps {
  mode: NavMode
  categories?: WikiCategoryItem[]
  activeCategory?: string
  onCategorySelect?: (key: string) => void
  availableAnchors?: ReadonlySet<'content' | 'media' | 'info'>
  pageType?: string
  recentPages?: RecentWikiPage[]
  onBack?: () => void
}

export function RouteAwareCardNav({ mode, categories = [], onCategorySelect, availableAnchors, pageType = '', recentPages = [], onBack }: RouteAwareCardNavProps) {
  const [open, setOpen] = useState(false)
  const mainCategories = useUIStore((state) => state.categoriesMeta)
  const isWiki = mode === 'wiki'
  const baseGroups = isWiki ? wikiNavigation(categories, onCategorySelect, availableAnchors) : mainNavigation(mainCategories)
  const groups = isWiki && pageType
    ? [
        { ...baseGroups[1], links: [...baseGroups[1].links, ...recentPages.map((item) => ({ label: `最近 · ${item.title}`, href: item.route }))] },
        baseGroups[0],
        baseGroups[2],
      ]
    : baseGroups
  return (
    <CardNav
      groups={groups}
      open={open}
      onOpenChange={setOpen}
      visible
      context={pageType || mode}
      className={`card-nav--archive card-nav--${mode}`}
      dataContext={pageType || mode}
      themeControl={<ThemeToggle />}
      primary={<a className="card-nav__primary" href={isWiki ? '/' : '/wiki/character'}>{isWiki ? '首页' : 'WIKI'}</a>}
      backControl={onBack ? (
        <button type="button" className="card-nav__back" aria-label="返回" onClick={onBack}>返回</button>
      ) : undefined}
    />
  )
}
