import { motion } from 'framer-motion'
import { useState } from 'react'
import { GLOBAL_BACKGROUND_IMAGE_SRC, HOME_VIDEO_SRC } from '../../media/assets'
import './HomeSection.css'

const titleVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (delay: number) => ({
    opacity: 1, y: 0,
    transition: { duration: 0.8, ease: 'easeOut' as const, delay },
  }),
}

export function HomeSection() {
  const [showToast, setShowToast] = useState(false)
  const [videoFailed, setVideoFailed] = useState(false)
  const [videoReady, setVideoReady] = useState(false)

  return (
    <section
      data-snap-section="home"
      className="snap-section home-section"
    >
      {/* 背景层:视频优先,失败时保留全局图片背景 */}
      <div
        aria-hidden="true"
        className="home-section__fallback"
        style={{
          backgroundImage: `linear-gradient(rgba(12, 16, 15, 0.28), rgba(12, 16, 15, 0.62)), url(${GLOBAL_BACKGROUND_IMAGE_SRC})`,
          filter: videoFailed ? 'none' : 'brightness(0.76)',
        }}
      />
      {!videoFailed && (
        <video
          className="home-section__video"
          autoPlay
          muted
          loop
          playsInline
          poster={GLOBAL_BACKGROUND_IMAGE_SRC}
          onError={() => setVideoFailed(true)}
          onCanPlay={() => setVideoReady(true)}
          style={{
            opacity: videoReady ? 1 : 0,
            transition: 'opacity 900ms ease',
          }}
        >
          <source src={HOME_VIDEO_SRC} type="video/mp4" />
        </video>
      )}

      {/* 内容层 */}
      <div className="home-section__content">
        <motion.h1
          custom={0}
          variants={titleVariants}
          initial="hidden"
          animate="visible"
          className="home-section__title"
        >
          重返未来:1999
        </motion.h1>

        <motion.h2
          custom={0.3}
          variants={titleVariants}
          initial="hidden"
          animate="visible"
          className="home-section__subtitle"
        >
          REVERSE: 1999
        </motion.h2>

        <motion.p
          custom={0.6}
          variants={titleVariants}
          initial="hidden"
          animate="visible"
          className="home-section__version"
        >
          3.8 版本 · 世纪末尺度
        </motion.p>

        {/* 下载按钮 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.9 }}
          className="home-section__download"
        >
          <button
            onClick={() => {
              setShowToast(true)
              setTimeout(() => setShowToast(false), 2500)
            }}
            className="home-section__cta"
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = '0 0 20px var(--border-glow)'
              e.currentTarget.style.background = 'rgba(212, 175, 55, 0.1)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = 'none'
              e.currentTarget.style.background = 'transparent'
            }}
          >
            立即下载
          </button>
          {showToast && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="home-section__toast"
            >
              下载链接待补
            </motion.div>
          )}
        </motion.div>
      </div>

      {/* 滚轮提示 */}
      <motion.div
        animate={{ y: [0, 8, 0] }}
        transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        className="home-section__scroll-cue"
      >
        ↓
      </motion.div>
    </section>
  )
}
