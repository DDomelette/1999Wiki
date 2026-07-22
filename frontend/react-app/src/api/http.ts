import type { CategoryMeta, CategoryDoc } from '../types'

export async function fetchCategories(): Promise<CategoryMeta[]> {
  const res = await fetch('/api/categories')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.categories as CategoryMeta[]
}

export async function fetchCategoryDocs(key: string, limit = 5): Promise<CategoryDoc[]> {
  const res = await fetch(`/api/category/${encodeURIComponent(key)}/docs?limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.docs as CategoryDoc[]
}

export async function fetchHealth(): Promise<{ status: string; doc_count: number; llm_ready: boolean }> {
  const res = await fetch('/health')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
