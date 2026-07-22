import { motion } from 'framer-motion'
import { useState } from 'react'
import { GLOBAL_BACKGROUND_IMAGE_SRC, HOME_VIDEO_SRC } from '../../media/assets'

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
      className="snap-section"
      style={{ position: 'relative', overflow: 'hidden' }}
    >
      {/* 背景层:视频优先,失败时保留全局图片背景 */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `linear-gradient(rgba(12, 16, 15, 0.28), rgba(12, 16, 15, 0.62)), url(${GLOBAL_BACKGROUND_IMAGE_SRC})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          filter: videoFailed ? 'none' : 'brightness(0.76)',
        }}
      />
      {!videoFailed && (
        <video
          className="video-bg"
          autoPlay
          muted
          loop
          playsInline
          poster={GLOBAL_BACKGROUND_IMAGE_SRC}
          onError={() => setVideoFailed(true)}
          onCanPlay={() => setVideoReady(true)}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            opacity: videoReady ? 1 : 0,
            transition: 'opacity 900ms ease',
          }}
        >
          <source src={HOME_VIDEO_SRC} type="video/mp4" />
        </video>
      )}

      {/* 内容层 */}
      <div
        style={{
          position: 'relative', zIndex: 10,
          height: '100%', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 16,
        }}
      >
        <motion.h1
          custom={0}
          variants={titleVariants}
          initial="hidden"
          animate="visible"
          style={{
            fontFamily: 'var(--font-body)',
            fontWeight: 700,
            fontSize: 'clamp(2.5rem, 6vw, 4.5rem)',
            color: 'var(--text-primary)',
            textShadow: '0 4px 24px rgba(0,0,0,0.6)',
          }}
        >
          重返未来:1999
        </motion.h1>

        <motion.h2
          custom={0.3}
          variants={titleVariants}
          initial="hidden"
          animate="visible"
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: 'clamp(1.5rem, 4vw, 3rem)',
            color: 'var(--accent-gold)',
            letterSpacing: '0.1em',
          }}
        >
          REVERSE: 1999
        </motion.h2>

        <motion.p
          custom={0.6}
          variants={titleVariants}
          initial="hidden"
          animate="visible"
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 500,
            fontSize: '1.25rem',
            color: 'var(--accent-gold)',
            opacity: 0.9,
          }}
        >
          3.8 版本 · 世纪末尺度
        </motion.p>

        {/* 下载按钮 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.9 }}
          style={{ marginTop: 48 }}
        >
          <button
            onClick={() => {
              setShowToast(true)
              setTimeout(() => setShowToast(false), 2500)
            }}
            style={{
              padding: '12px 48px',
              border: '1px solid var(--accent-gold)',
              borderRadius: 4,
              background: 'transparent',
              color: 'var(--accent-gold)',
              fontFamily: 'var(--font-body)',
              fontSize: '1.1rem',
              letterSpacing: '0.1em',
              cursor: 'pointer',
              transition: 'all 0.3s',
            }}
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
              style={{
                marginTop: 12, padding: '8px 16px',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-card)',
                borderRadius: 4,
                color: 'var(--text-secondary)',
                fontSize: '0.9rem',
              }}
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
        style={{
          position: 'absolute', bottom: 32, left: '50%',
          transform: 'translateX(-50%)',
          color: 'var(--text-muted)',
          fontSize: '1.5rem',
        }}
      >
        ↓
      </motion.div>
    </section>
  )
}
