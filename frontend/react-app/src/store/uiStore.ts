import { create } from 'zustand'
import type { CategoryMeta } from '../types'

type Section = 'home' | 'data' | 'chat'

interface UIState {
  topNavVisible: boolean
  currentSection: Section
  currentCategory: string | null
  categoriesMeta: CategoryMeta[]
  setTopNav: (v: boolean) => void
  setSection: (s: Section) => void
  setCategory: (c: string | null) => void
  setCategoriesMeta: (m: CategoryMeta[]) => void
}

export const useUIStore = create<UIState>((set) => ({
  topNavVisible: false,
  currentSection: 'home',
  currentCategory: null,
  categoriesMeta: [],
  setTopNav: (v) => set({ topNavVisible: v }),
  setSection: (s) => set({ currentSection: s }),
  setCategory: (c) => set({ currentCategory: c }),
  setCategoriesMeta: (m) => set({ categoriesMeta: m }),
}))
