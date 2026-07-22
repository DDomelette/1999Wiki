import { useEffect, useMemo } from 'react'
import { getPageMedia } from './contract'
import { reportPageMedia } from './liveRegistry'

// 页面级媒体钩子：等价于调用 GET /api/wiki/pages/{pageId}，
// 拿到清洗后的 mediaLinks[]；同时上报实时注册表供契约检查器展示。
// appPage：站内页面 id（与 App 的 page state 对齐）
export function usePageMedia(appPage, pageId) {
  const links = useMemo(() => getPageMedia(pageId), [pageId])
  useEffect(() => {
    reportPageMedia(appPage, pageId, links)
  }, [appPage, pageId, links])
  return links
}
