import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Theme } from '../types'

export const THEME_ORDER: readonly Theme[] = ['storm-dark', 'manuscript-gold', 'cold-archive']

const LEGACY_THEMES: Record<string, Theme> = {
  'dark-warm': 'storm-dark',
  parchment: 'manuscript-gold',
  'mystic-purple': 'cold-archive',
}

export function migrateTheme(value: unknown): Theme {
  if (typeof value !== 'string') return 'storm-dark'
  if ((THEME_ORDER as readonly string[]).includes(value)) return value as Theme
  return LEGACY_THEMES[value] ?? 'storm-dark'
}

interface ThemeState {
  theme: Theme
  cycle: () => void
  set: (theme: Theme) => void
}

function applyTheme(value: unknown) {
  document.documentElement.setAttribute('data-theme', migrateTheme(value))
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'storm-dark',
      cycle: () => {
        const current = migrateTheme(get().theme)
        const next = THEME_ORDER[(THEME_ORDER.indexOf(current) + 1) % THEME_ORDER.length]
        set({ theme: next })
        applyTheme(next)
      },
      set: (theme) => {
        const next = migrateTheme(theme)
        set({ theme: next })
        applyTheme(next)
      },
    }),
    {
      name: 'r1999-theme',
      version: 2,
      migrate: (persisted) => {
        const state = (persisted ?? {}) as Partial<ThemeState>
        return { ...state, theme: migrateTheme(state.theme) } as ThemeState
      },
      onRehydrateStorage: () => (state) => applyTheme(state?.theme),
    },
  ),
)
