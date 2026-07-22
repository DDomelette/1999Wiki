import { useEffect, useRef, useState } from 'react'
import { useUIStore } from './store/uiStore'
import { useScrollSpy } from './hooks/useScrollSpy'
import { useWheelSnapNavigation } from './hooks/useWheelSnapNavigation'
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
  if (pathname.startsWith('/wiki-preview')) {
    return <WikiShell variant="kimi-preview" />
  }
  if (pathname.startsWith('/wiki')) {
    return <WikiShell variant="current" />
  }

  return <MainApp />
}

function MainApp() {
  const setCategoriesMeta = useUIStore((s) => s.setCategoriesMeta)
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
