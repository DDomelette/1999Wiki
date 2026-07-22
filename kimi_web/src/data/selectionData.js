// Mobile Selection Profile 页面数据 —— 复刻自 Stitch 设计稿

// 角色静态文案（名字/拉丁名）；媒体一律经由 src/media/contract.js 契约层获取，
// 前端不持有任何图片路径 —— variant 是连接文案与媒体契约的唯一钥匙
export const SEL_CHARACTERS = [
  { name: '槲寄生', latin: 'DRUVIS III', variant: 'druvis' },
  { name: '红弩箭', latin: 'LILYA', variant: 'lilya' },
  { name: '尼克·波顿', latin: 'NICK BOTTOM', variant: 'nick' },
  { name: '星锑', latin: 'REGULUS', variant: 'regulus' },
]

export const SEL_SYS_INFO = [
  { text: 'SYS.LOC: FOREST', dim: false },
  { text: 'CLASS: ARCANIST', dim: true },
  { text: 'STATUS: ACTIVE', dim: true },
]

export const SEL_BOTTOM_NAV = [
  { icon: 'folder_open', label: 'DOSSIER', active: true },
  { icon: 'inventory_2', label: 'ARCHIVE', active: false },
  { icon: 'rocket_launch', label: 'DEPLOY', fab: true },
  { icon: 'history_edu', label: 'LOGS', active: false },
]
