import { Moon, Sun, SunMoon } from 'lucide-react'
import { useThemeStore } from '../../store/themeStore'

const LABELS = {
  'storm-dark': '风暴暗夜',
  'manuscript-gold': '手稿金色',
  'cold-archive': '冷调档案',
} as const

export function ThemeToggle() {
  const theme = useThemeStore((state) => state.theme)
  const cycle = useThemeStore((state) => state.cycle)
  const Icon = theme === 'storm-dark' ? Moon : theme === 'manuscript-gold' ? Sun : SunMoon
  const label = `当前主题：${LABELS[theme]}，点击切换`
  return (
    <button className="theme-toggle" type="button" onClick={cycle} title={label} aria-label={label}>
      <Icon aria-hidden="true" size={19} strokeWidth={1.7} />
    </button>
  )
}
