import { createElement, useLayoutEffect, useMemo, useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import './ScrollReveal.css'
import { getMotionPolicy } from '../../../motion/motionPolicy'

export interface ScrollRevealProps {
  text: string
  scrollContainer: HTMLElement | null
  baseRotation: 0
  enabled: boolean
  className?: string
  as?: 'p' | 'h1' | 'h2' | 'h3' | 'div'
  blurStrength?: number
  revealStart?: number
}

export function ScrollReveal({ text, scrollContainer, enabled, className = '', as = 'p', blurStrength = 5, revealStart = 90 }: ScrollRevealProps) {
  const ref = useRef<HTMLElement>(null)
  const words = useMemo(() => text.split(/(\s+)/), [text])

  useLayoutEffect(() => {
    const element = ref.current
    const policy = getMotionPolicy()
    if (!element || !enabled || !policy.enabled) return
    gsap.registerPlugin(ScrollTrigger)
    const ownScroller = scrollContainer ?? nearestScrollContainer(element)
    const targets = element.querySelectorAll<HTMLElement>('[data-reveal-word]')
    const animation = gsap.fromTo(targets, { opacity: 0.15, filter: policy.blur ? `blur(${blurStrength}px)` : 'none' }, {
      opacity: 1,
      filter: 'blur(0px)',
      ease: 'none',
      stagger: 0.035,
      scrollTrigger: {
        trigger: element,
        scroller: ownScroller ?? undefined,
        start: `top ${revealStart}%`,
        end: 'bottom 55%',
        scrub: true,
      },
    })
    return () => {
      animation.scrollTrigger?.kill()
      animation.kill()
    }
  }, [blurStrength, enabled, revealStart, scrollContainer, text])

  return createElement(as, { ref, className: `reactbits-scroll-reveal ${className}`.trim() }, words.map((word, index) => /^\s+$/.test(word) ? word : <span data-reveal-word key={`${word}-${index}`}>{word}</span>))
}

function nearestScrollContainer(element: HTMLElement): HTMLElement | null {
  let current = element.parentElement
  while (current) {
    const overflow = getComputedStyle(current).overflowY
    if (overflow === 'auto' || overflow === 'scroll') return current
    current = current.parentElement
  }
  return null
}
