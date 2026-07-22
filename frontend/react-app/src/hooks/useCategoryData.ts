import { useEffect, useState } from 'react'
import type { CategoryDoc, CategoryMeta } from '../types'
import { fetchCategoryDocs } from '../api/http'
import { useUIStore } from '../store/uiStore'

interface CategoryData {
  docs: CategoryDoc[]
  meta: CategoryMeta | null
  loading: boolean
  error: string | null
}

/** 板块进入视口时加载文档列表,meta 取 uiStore 缓存。 */
export function useCategoryData(key: string | null): CategoryData {
  const [state, setState] = useState<CategoryData>({
    docs: [], meta: null, loading: false, error: null,
  })
  const categoriesMeta = useUIStore((s) => s.categoriesMeta)

  useEffect(() => {
    if (!key) {
      setState({ docs: [], meta: null, loading: false, error: null })
      return
    }
    let cancelled = false
    const meta = categoriesMeta.find((c) => c.key === key) || null
    setState({ docs: [], meta, loading: true, error: null })
    fetchCategoryDocs(key, 5)
      .then((docs) => {
        if (!cancelled) setState({ docs, meta, loading: false, error: null })
      })
      .catch((e) => {
        if (!cancelled) setState({ docs: [], meta, loading: false, error: String(e) })
      })
    return () => { cancelled = true }
  }, [key, categoriesMeta])

  return state
}
