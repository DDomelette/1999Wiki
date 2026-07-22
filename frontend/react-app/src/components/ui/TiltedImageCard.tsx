import { motion, useMotionValue, useReducedMotion, useSpring } from 'framer-motion'
import type { CSSProperties, ImgHTMLAttributes, PointerEvent } from 'react'
import { useRef } from 'react'

interface TiltedImageCardProps {
  src: string
  alt: string
  className?: string
  containerStyle?: CSSProperties
  imageStyle?: CSSProperties
  /** 悬浮放大倍率，默认 1.35；资料页传更小的值避免超出窗口 */
  hoverScale?: number
  onImageError?: ImgHTMLAttributes<HTMLImageElement>['onError']
}

const spring = {
  damping: 30,
  stiffness: 120,
  mass: 1.4,
}

export function TiltedImageCard({
  src,
  alt,
  className,
  containerStyle,
  imageStyle,
  hoverScale = 1.35,
  onImageError,
}: TiltedImageCardProps) {
  const ref = useRef<HTMLElement>(null)
  const reduceMotion = useReducedMotion()
  const rotateX = useSpring(useMotionValue(0), spring)
  const rotateY = useSpring(useMotionValue(0), spring)
  const scale = useSpring(1, spring)

  const resetMotion = () => {
    rotateX.set(0)
    rotateY.set(0)
    scale.set(1)
  }

  const handlePointerMove = (event: PointerEvent<HTMLElement>) => {
    if (reduceMotion || event.pointerType === 'touch' || !ref.current) return

    const rect = ref.current.getBoundingClientRect()
    const offsetX = event.clientX - rect.left - rect.width / 2
    const offsetY = event.clientY - rect.top - rect.height / 2
    const rotateAmplitude = 16

    rotateX.set((offsetY / (rect.height / 2)) * -rotateAmplitude)
    rotateY.set((offsetX / (rect.width / 2)) * rotateAmplitude)
  }

  const handlePointerEnter = () => {
    if (!reduceMotion) scale.set(hoverScale)
  }

  return (
    <motion.figure
      ref={ref}
      data-testid="tilted-image-card"
      className={className}
      onPointerMove={handlePointerMove}
      onPointerEnter={handlePointerEnter}
      onPointerLeave={resetMotion}
      style={{
        width: 'min(34vw, 420px)',
        height: '70vh',
        maxHeight: 760,
        minWidth: 260,
        perspective: 900,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        isolation: 'isolate',
        margin: 0,
        border: 'none',
        boxShadow: 'none',
        background: 'transparent',
        ...containerStyle,
      }}
    >
      <motion.div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transformStyle: 'preserve-3d',
          rotateX,
          rotateY,
          scale,
          border: 'none',
          boxShadow: 'none',
          background: 'transparent',
        }}
      >
        <img
          src={src}
          alt={alt}
          loading="lazy"
          style={{
            display: 'block',
            maxWidth: '100%',
            maxHeight: '100%',
            width: 'auto',
            height: 'auto',
            objectFit: 'contain',
            border: 'none',
            boxShadow: 'none',
            borderRadius: 0,
            background: 'transparent',
            transform: 'translateZ(24px)',
            willChange: 'transform',
            ...imageStyle,
          }}
          onError={onImageError}
        />
      </motion.div>
    </motion.figure>
  )
}
