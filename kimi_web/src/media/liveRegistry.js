// 页面媒体实时注册表（演示教具）
// 页面挂载时通过 usePageMedia 上报自己"实际消费"的 mediaLinks[]，
// 契约检查器订阅此注册表，实时展示当前页的 DTO 全量列表。
// appPage 是站内页面 id（如 'selection'），用于检查器判断报告是否与当前页匹配。

let current = { appPage: null, pageId: null, links: [] }
const listeners = new Set()

export function reportPageMedia(appPage, pageId, links) {
  current = { appPage, pageId, links }
  listeners.forEach((fn) => fn())
}

export function subscribeLiveMedia(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function getLiveMedia() {
  return current
}
