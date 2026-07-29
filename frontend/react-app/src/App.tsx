import { useEffect, useRef, useState } from 'react'
import { useUIStore } from './store/uiStore'
import { useScrollSpy } from './hooks/useScrollSpy'
import { useWheelSnapNavigation } from './hooks/useWheelSnapNavigation'
import { navigateToMainSection, parseMainHash } from './navigation/mainSectionNavigation'
import { fetchCategories } from './api/http'
import { RouteAwareCardNav } from './components/navigation/RouteAwareCardNav'
import { HomeSection } from './components/sections/HomeSection'
import { DataSection } from './components/sections/DataSection'
import { ChatSection } from './components/sections/ChatSection'
import { AutoHideScrollbar } from './components/ui/AutoHideScrollbar'
import { WikiShell } from './components/wiki/WikiShell'
import { FALLBACK_CATEGORIES, filterVisibleCategories } from './data/fallbackCategories'
import { MotionPreview } from './components/dev/MotionPreview'

export default function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname)

  useEffect(() => {
    const handlePopState = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  if (import.meta.env.DEV && pathname === '/__motion-preview') {
    return <MotionPreview />
  }
  if (pathname === '/wiki' || pathname.startsWith('/wiki/')) {
    return <WikiShell />
  }

  return <MainApp />
}

function MainApp() {
  const setCategoriesMeta = useUIStore((s) => s.setCategoriesMeta)
  const categoriesMeta = useUIStore((s) => s.categoriesMeta)
  const snapContainerRef = useRef<HTMLElement>(null)
  useScrollSpy()
  useWheelSnapNavigation()

  useEffect(() => {
    fetchCategories()
      .then((categories) => {
        const visible = filterVisibleCategories(categories)
        setCategoriesMeta(visible.length > 0 ? visible : filterVisibleCategories(FALLBACK_CATEGORIES))
      })
      .catch((e) => {
        console.error('[App] 加载板块元数据失败:', e)
        setCategoriesMeta(filterVisibleCategories(FALLBACK_CATEGORIES))
      })
  }, [setCategoriesMeta])

  // 挂载与 hashchange 时恢复 hash 对应的语义页面;分类异步返回后重试,且不写入历史
  useEffect(() => {
    const restoreMainHash = () => {
      const target = parseMainHash(window.location.hash)
      if (target) navigateToMainSection(target, { behavior: 'auto', history: 'none' })
    }
    restoreMainHash()
    window.addEventListener('hashchange', restoreMainHash)
    return () => window.removeEventListener('hashchange', restoreMainHash)
  }, [categoriesMeta])

  return (
    <>
      <RouteAwareCardNav mode="main" />
      <main ref={snapContainerRef} className="snap-container native-scrollbar-hidden">
        <HomeSection />
        <DataSection />
        <ChatSection />
      </main>
      <AutoHideScrollbar targetRef={snapContainerRef} testId="global-scrollbar" />
    </>
  )
}
