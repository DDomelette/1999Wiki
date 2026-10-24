import { beforeEach, describe, expect, it } from 'vitest'
import { migrateTheme, THEME_ORDER, useThemeStore } from './themeStore'

describe('themeStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useThemeStore.getState().set('manuscript-gold')
  })

  it('defaults to the bright manuscript theme and migrates persisted values', () => {
    expect(migrateTheme(undefined)).toBe('manuscript-gold')
    expect(migrateTheme('dark-warm')).toBe('storm-dark')
    expect(migrateTheme('parchment')).toBe('manuscript-gold')
    expect(migrateTheme('mystic-purple')).toBe('cold-archive')
    expect(migrateTheme('broken')).toBe('manuscript-gold')
  })

  it('cycles through exactly the three approved themes', () => {
    expect(THEME_ORDER).toEqual(['storm-dark', 'manuscript-gold', 'cold-archive'])
    useThemeStore.getState().cycle()
    expect(useThemeStore.getState().theme).toBe('cold-archive')
    useThemeStore.getState().cycle()
    expect(useThemeStore.getState().theme).toBe('storm-dark')
    useThemeStore.getState().cycle()
    expect(useThemeStore.getState().theme).toBe('manuscript-gold')
    expect(document.documentElement).toHaveAttribute('data-theme', 'manuscript-gold')
  })
})
