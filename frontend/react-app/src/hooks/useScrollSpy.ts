import { useEffect } from 'react'
import { useUIStore } from '../store/uiStore'

/** 监听所有 [data-snap-section] 元素可见性,写入 uiStore.currentSection / currentCategory。 */
export function useScrollSpy() {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio > 0.5) {
            const section = entry.target.getAttribute('data-snap-section') || ''
            if (section.startsWith('data:')) {
              useUIStore.getState().setSection('data')
              useUIStore.getState().setCategory(section.split(':')[1])
            } else if (section === 'home' || section === 'data' || section === 'chat') {
              useUIStore.getState().setSection(section)
              if (section !== 'data') useUIStore.getState().setCategory(null)
            }
          }
        }
      },
      { threshold: [0.5, 0.75] },
    )
    const observed = new WeakSet<Element>()
    const observeSections = () => {
      document.querySelectorAll('[data-snap-section]').forEach((section) => {
        if (!observed.has(section)) {
          observer.observe(section)
          observed.add(section)
        }
      })
    }

    observeSections()
    const mutationObserver = new MutationObserver(observeSections)
    mutationObserver.observe(document.body, { childList: true, subtree: true })

    return () => {
      mutationObserver.disconnect()
      observer.disconnect()
    }
  }, [])
}
