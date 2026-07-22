import { useEffect, useState } from 'react'
import AdvancedProfilePage from './pages/AdvancedProfilePage'
import ArchivalDossierPage from './pages/ArchivalDossierPage'
import MobileSelectionPage from './pages/MobileSelectionPage'
import ComprehensiveProfilePage from './pages/ComprehensiveProfilePage'
import SiteNav, { PAGES } from './components/SiteNav'
import MediaInspector from './components/MediaInspector'
import { subscribeLiveMedia, getLiveMedia } from './media/liveRegistry'

const PAGE_COMPONENTS = {
  advanced: AdvancedProfilePage,
  dossier: ArchivalDossierPage,
  selection: MobileSelectionPage,
  comprehensive: ComprehensiveProfilePage,
}

export default function App() {
  const [page, setPage] = useState('advanced')
  const [showInspector, setShowInspector] = useState(false)
  const [liveMedia, setLiveMedia] = useState(getLiveMedia())

  // 订阅页面媒体的实时上报（页面挂载时 usePageMedia 会推送）
  useEffect(() => subscribeLiveMedia(() => setLiveMedia({ ...getLiveMedia() })), [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'm' || e.key === 'M' || e.key === 'Escape') {
        setShowInspector((v) => (e.key === 'Escape' ? false : !v))
        return
      }
      const target = PAGES.find((p) => p.key === e.key)
      if (target) setPage(target.id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // 切换页面时回到顶部（长卷页尤其需要）
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [page])

  const PageComponent = PAGE_COMPONENTS[page]

  return (
    <>
      <PageComponent />
      <SiteNav current={page} onNavigate={setPage} />
      {/* 契约检查器开关浮标（演示教具） */}
      {!showInspector && (
        <button
          onClick={() => setShowInspector(true)}
          title="媒体契约检查器（M）"
          className="fixed bottom-24 right-4 z-[80] font-mono text-[10px] tracking-widest uppercase bg-black/70 text-amber-300/90 border border-amber-500/40 rounded px-2 py-1 hover:bg-black/90"
        >
          DTO
        </button>
      )}
      {showInspector && <MediaInspector onClose={() => setShowInspector(false)} currentPage={page} liveMedia={liveMedia} />}
    </>
  )
}
