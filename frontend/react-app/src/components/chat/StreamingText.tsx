import { motion } from 'framer-motion'

/** LLM 回答逐字动画,每字 opacity 0→1 + scale 0.5→1,200ms。 */
export function StreamingText({ text, streaming }: { text: string; streaming: boolean }) {
  const chars = Array.from(text)
  return (
    <span>
      {chars.map((ch, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.2 }}
          style={{ display: 'inline-block' }}
        >
          {ch}
        </motion.span>
      ))}
      {streaming && (
        <motion.span
          animate={{ opacity: [1, 0, 1] }}
          transition={{ duration: 0.8, repeat: Infinity }}
          style={{ display: 'inline-block', marginLeft: 2, color: 'var(--accent-gold)' }}
        >
          ▌
        </motion.span>
      )}
    </span>
  )
}
