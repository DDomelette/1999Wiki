import { useEffect } from 'react'
import { useUIStore } from '../store/uiStore'

/** 以 .snap-container 为观察根监听吸附叶目标可见性,写入 uiStore.currentSection / currentCategory。 */
export function useScrollSpy() {
  useEffect(() => {
    const root = document.querySelector<HTMLElement>('.snap-container')
    if (!root) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio > 0.5) {
            const section = entry.target.getAttribute('data-snap-section') || ''
            if (section === 'data:loading') {
              useUIStore.getState().setSection('data')
              useUIStore.getState().setCategory(null)
            } else if (section.startsWith('data:')) {
              useUIStore.getState().setSection('data')
              useUIStore.getState().setCategory(section.split(':')[1])
            } else if (section === 'home' || section === 'chat') {
              useUIStore.getState().setSection(section)
              useUIStore.getState().setCategory(null)
            }
          }
        }
      },
      { root, threshold: [0.5, 0.75] },
    )
    const observed = new WeakSet<Element>()
    const observeSections = () => {
      root.querySelectorAll('[data-snap-section]').forEach((section) => {
        if (!observed.has(section)) {
          observer.observe(section)
          observed.add(section)
        }
      })
    }

    observeSections()
    const mutationObserver = new MutationObserver(observeSections)
    mutationObserver.observe(root, { childList: true, subtree: true })

    return () => {
      mutationObserver.disconnect()
      observer.disconnect()
    }
  }, [])
}
