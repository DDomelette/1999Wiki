import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import type { CategoryMeta } from '../../types'
import { useCategoryData } from '../../hooks/useCategoryData'
import { ScrollableDescription } from '../ScrollableDescription'
import { getCategoryCoverSrc } from '../../media/assets'
import { TiltedImageCard } from '../ui/TiltedImageCard'

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
      className="snap-section"
      style={{ display: 'flex', alignItems: 'center', padding: '0 8%', position: 'relative' }}
    >
      {/* 板块标识竖条 */}
      <div className="category-bar" style={{ position: 'absolute', left: 0, top: '20%', height: '60%' }} />

      <motion.div
        data-testid="category-panel-layout"
        variants={panelVariants}
        initial="hidden"
        animate={inView ? 'visible' : 'hidden'}
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(320px, 0.72fr) minmax(560px, 1.45fr)',
          gap: 'clamp(40px, 5vw, 104px)',
          width: '100%',
          maxWidth: 1680,
          margin: '0 auto',
        }}
      >
        {/* 左:文字 */}
        <div>
          <motion.h2
            variants={titleVariants}
            style={{
              fontFamily: 'var(--font-body)',
              fontWeight: 700,
              fontSize: 'clamp(2rem, 5vw, 3.5rem)',
              color: 'var(--accent-gold)',
              marginBottom: 8,
            }}
          >
            {meta.title}
          </motion.h2>
          <motion.p
            variants={titleVariants}
            style={{
              fontFamily: 'var(--font-display)',
              color: 'var(--text-muted)',
              letterSpacing: '0.1em',
              marginBottom: 24,
            }}
          >
            {meta.subtitle} · {meta.doc_count} 篇
          </motion.p>
          <ScrollableDescription text={description} start={inView} />
          {loading && <p style={{ color: 'var(--text-muted)', marginTop: 16 }}>加载中...</p>}
        </div>

        {/* 右:封面图 */}
        <motion.div
          variants={imageVariants}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: 0 }}
        >
          <TiltedImageCard
            src={coverUrl}
            alt={meta.title}
            hoverScale={1.15}
            containerStyle={{
              width: 'min(42vw, 680px)',
              height: 'min(64vh, 620px)',
              minWidth: 320,
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
          style={{
            position: 'absolute',
            right: 48,
            bottom: 40,
            color: 'var(--accent-gold)',
            textDecoration: 'none',
            fontFamily: 'var(--font-display)',
            letterSpacing: '0.08em',
            textAlign: 'center',
          }}
        >
          <span style={{ display: 'block', marginBottom: 6 }}>进入WIKI</span>
          <span aria-hidden="true" style={{ fontSize: 32 }}>→</span>
        </a>
      )}
    </section>
  )
}
