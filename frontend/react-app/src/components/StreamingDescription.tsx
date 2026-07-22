import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

/** 文本逐字 reveal,每字 18ms,每字 opacity 0→1 + y 8→0。 */
export function StreamingDescription({ text, start }: { text: string; start: boolean }) {
  const [visibleCount, setVisibleCount] = useState(0)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (!start || !text) return
    setVisibleCount(0)
    let i = 0
    timerRef.current = window.setInterval(() => {
      i++
      setVisibleCount(i)
      if (i >= text.length) {
        if (timerRef.current) window.clearInterval(timerRef.current)
      }
    }, 18)
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
    }
  }, [start, text])

  const chars = Array.from(text.slice(0, visibleCount))
  return (
    <p
      style={{
        fontFamily: 'var(--font-body)',
        fontSize: '1.125rem',
        lineHeight: 1.9,
        color: 'var(--text-secondary)',
      }}
    >
      {chars.map((ch, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {ch}
        </motion.span>
      ))}
    </p>
  )
}
