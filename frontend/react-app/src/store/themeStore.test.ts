import { beforeEach, describe, expect, it } from 'vitest'
import { migrateTheme, THEME_ORDER, useThemeStore } from './themeStore'

describe('themeStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useThemeStore.getState().set('storm-dark')
  })

  it('migrates legacy and unknown persisted values', () => {
    expect(migrateTheme('dark-warm')).toBe('storm-dark')
    expect(migrateTheme('parchment')).toBe('manuscript-gold')
    expect(migrateTheme('mystic-purple')).toBe('cold-archive')
    expect(migrateTheme('broken')).toBe('storm-dark')
  })

  it('cycles through exactly the three approved themes', () => {
    expect(THEME_ORDER).toEqual(['storm-dark', 'manuscript-gold', 'cold-archive'])
    useThemeStore.getState().cycle()
    expect(useThemeStore.getState().theme).toBe('manuscript-gold')
    useThemeStore.getState().cycle()
    expect(useThemeStore.getState().theme).toBe('cold-archive')
    useThemeStore.getState().cycle()
    expect(useThemeStore.getState().theme).toBe('storm-dark')
    expect(document.documentElement).toHaveAttribute('data-theme', 'storm-dark')
  })
})
