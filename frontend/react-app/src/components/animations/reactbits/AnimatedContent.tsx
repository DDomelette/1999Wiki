import { useLayoutEffect, useRef } from 'react'
import type { HTMLAttributes } from 'react'
import gsap from 'gsap'
import { getMotionPolicy } from '../../../motion/motionPolicy'

export interface AnimatedContentProps extends HTMLAttributes<HTMLDivElement> {
  direction?: 'vertical' | 'horizontal'
  distance?: number
  scrollContainer?: Element | null
  once?: boolean
}

export function AnimatedContent({ direction = 'vertical', distance = 40, scrollContainer, once = true, children, ...props }: AnimatedContentProps) {
  const ref = useRef<HTMLDivElement>(null)
  const policy = getMotionPolicy()
  const reduced = !policy.enabled

  useLayoutEffect(() => {
    if (!ref.current || reduced) return
    const context = gsap.context(() => {
      gsap.fromTo(
        ref.current,
        { opacity: 0, x: direction === 'horizontal' ? distance : 0, y: direction === 'vertical' ? distance : 0 },
        { opacity: 1, x: 0, y: 0, duration: 0.55, ease: 'power3.out', clearProps: 'transform', overwrite: 'auto' },
      )
    }, ref)
    return () => context.revert()
  }, [direction, distance, once, reduced, scrollContainer])

  return <div ref={ref} data-motion={reduced ? 'reduced' : 'animated'} {...props}>{children}</div>
}
