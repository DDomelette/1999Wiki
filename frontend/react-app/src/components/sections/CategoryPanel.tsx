import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import type { CategoryMeta } from '../../types'
import { useCategoryData } from '../../hooks/useCategoryData'
import { ScrollableDescription } from '../ScrollableDescription'
import { getCategoryCoverSrc } from '../../media/assets'
import { TiltedImageCard } from '../ui/TiltedImageCard'
import './DataSection.css'

const panelVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.3 } },
}
const titleVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.8, ease: 'easeOut' as const } },
}
const imageVariants = {
  hidden: { opacity: 0, scale: 1.1, y: 40, filter: 'blur(8px)' },
  visible: {
    opacity: 1, scale: 1, y: 0, filter: 'blur(0px)',
    transition: { duration: 1.2, ease: 'easeOut' as const },
  },
}

export function CategoryPanel({ meta }: { meta: CategoryMeta }) {
  const [inView, setInView] = useState(false)
  const { loading } = useCategoryData(inView ? meta.key : null)
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && entry.intersectionRatio > 0.5) setInView(true)
      },
      { threshold: 0.5 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const description = meta.description
  const coverUrl = getCategoryCoverSrc(meta.key)

  return (
    <section
      ref={ref}
      data-snap-section={`data:${meta.key}`}
      className="snap-section category-panel"
      data-category={meta.key}
    >
      {/* 板块标识竖条 */}
      <div className="category-panel__bar" />

      <motion.div
        data-testid="category-panel-layout"
        className="category-panel__layout"
        variants={panelVariants}
        initial="hidden"
        animate={inView ? 'visible' : 'hidden'}
      >
        {/* 左:文字 */}
        <div className="category-panel__copy">
          <motion.h2 className="category-panel__title" variants={titleVariants}>
            {meta.title}
          </motion.h2>
          <motion.p className="category-panel__meta" variants={titleVariants}>
            {meta.subtitle} · {meta.doc_count} 篇
          </motion.p>
          <ScrollableDescription text={description} start={inView} />
          {loading && <p className="category-panel__loading">加载中...</p>}
        </div>

        {/* 右:封面图 */}
        <motion.div className="category-panel__media" variants={imageVariants}>
          <TiltedImageCard
            className="category-panel__card"
            src={coverUrl}
            alt={meta.title}
            hoverScale={1.15}
            containerStyle={{
              width: 'var(--category-cover-width)',
              height: 'var(--category-cover-height)',
              minWidth: 'var(--category-cover-min-width)',
            }}
            onImageError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = 'none'
            }}
          />
        </motion.div>
      </motion.div>
      {(meta.key === '剧情' || meta.title === '剧情' || meta.key.toLowerCase() === 'story') && (
        <a
          href="/wiki"
          aria-label="进入WIKI"
          className="category-panel__wiki-link"
        >
          <span className="category-panel__wiki-link-label">进入WIKI</span>
          <span aria-hidden="true" className="category-panel__wiki-link-arrow">→</span>
        </a>
      )}
    </section>
  )
}
