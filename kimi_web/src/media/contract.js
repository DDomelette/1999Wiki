// ============================================================
// 媒体契约层 —— 在前端 demo 内"模拟"后端边界，用于演示解耦规则：
//
//   manifest → 后端构建映射 → MySQL wiki_media_links
//     → GET /api/wiki/pages/{pageId} → mediaLinks[] → React
//
// 对应真实实现：
//   - 读取侧   src/huiji_wiki/repository.py  get_page_detail()
//   - 清洗侧   src/huiji_wiki/models.py      sanitize_media_item()
//   - 公共地址  config/settings.yaml         assets.public_base_url
//
// 约定：object_key 是唯一持久化真相；公共 URL 在"API 返回时"由
// 后端配置运行时生成。前端永远只拿到清洗后的 14 字段 DTO。
// ============================================================

// ------------------------------------------------------------
// 【后端侧配置 · 前端不可见】
// 真实项目里这只存在于 settings.yaml / 部署环境，绝不打包进前端。
// 这里放在前端仓库仅作演示，并用醒目注释标记边界。
// ------------------------------------------------------------
const BACKEND_ONLY = {
  // Docker 网络内部地址（minio 是服务名，浏览器无法解析，绝不下发）
  internalEndpoint: 'minio:9000',
  // 浏览器可访问的公共基址；生产换成 https://assets.example.com 即可，
  // 数据库一行都不用改 —— 因为 URL 是运行时拼出来的
  publicBaseUrl: import.meta.env.VITE_ASSET_BASE_URL || '/assets',
  bucket: 'reverse1999-assets',
  objectPrefix: 'reverse1999',
  // MinIO 凭证、容器名、本地磁盘路径…… 同样止步于此
}

// ------------------------------------------------------------
// 【后端侧数据 · 模拟 MySQL wiki_media_links 表行】
// 字段与 repository.py:299 的 SELECT 对齐；object_key 为真相，
// 不存绝对 url（这是规则里建议的强化点：URL 运行时生成）。
// ------------------------------------------------------------
const WIKI_MEDIA_LINKS = [
  // —— 移动选人页：角色索引缩略图（点击即选人）——
  { pageId: 'wiki/selection', sectionKey: 'character-index', role: 'thumb', variant: 'druvis', displayOrder: 1, objectKey: 'sel-thumb-druvis.png', mediaId: 'M-DRUVIS-THUMB', assetId: 'A-0101', mime: 'image/png', title: '槲寄生', alt: 'DRUVIS III 索引缩略图', sha1: 'd3mo0001', width: 480, height: 270 },
  { pageId: 'wiki/selection', sectionKey: 'character-index', role: 'thumb', variant: 'lilya', displayOrder: 2, objectKey: 'sel-thumb-rednail.png', mediaId: 'M-LILYA-THUMB', assetId: 'A-0102', mime: 'image/png', title: '红弩箭', alt: 'LILYA 索引缩略图', sha1: 'd3mo0002', width: 480, height: 270 },
  { pageId: 'wiki/selection', sectionKey: 'character-index', role: 'thumb', variant: 'nick', displayOrder: 3, objectKey: 'sel-thumb-nick.png', mediaId: 'M-NICK-THUMB', assetId: 'A-0103', mime: 'image/png', title: '尼克·波顿', alt: 'NICK BOTTOM 索引缩略图', sha1: 'd3mo0003', width: 480, height: 270 },
  { pageId: 'wiki/selection', sectionKey: 'character-index', role: 'thumb', variant: 'regulus', displayOrder: 4, objectKey: 'sel-thumb-regulus.png', mediaId: 'M-REGULUS-THUMB', assetId: 'A-0104', mime: 'image/png', title: '星锑', alt: 'REGULUS 索引缩略图', sha1: 'd3mo0004', width: 480, height: 270 },

  // —— 移动选人页：立绘舞台 ——
  // 注意：只有 druvis 有 standee 行。其余角色"未入库"时后端就是不给行，
  // 前端按缺失渲染占位，而不是自己拼路径碰运气。
  { pageId: 'wiki/selection', sectionKey: 'stage', role: 'standee', variant: 'druvis', displayOrder: 1, objectKey: 'sel-standee.png', mediaId: 'M-DRUVIS-STANDEE', assetId: 'A-0201', mime: 'image/png', title: '槲寄生 全身立绘', alt: 'DRUVIS III 全身立绘', sha1: 'd3mo0011', width: 780, height: 1400 },
  { pageId: 'wiki/selection', sectionKey: 'stage', role: 'backdrop', variant: 'office', displayOrder: 0, objectKey: 'sel-bg-office.png', mediaId: 'M-STAGE-BG-OFFICE', assetId: 'A-0202', mime: 'image/png', title: '舞台背景', alt: '办公室背景', sha1: 'd3mo0012', width: 780, height: 844 },

  // —— 第 1 页 Advanced Profile：立绘舞台 + 技能图标 ——
  { pageId: 'wiki/profile-advanced', sectionKey: 'stage', role: 'standee', variant: 'initial', displayOrder: 1, objectKey: 'standee-initial.png', mediaId: 'M-ADV-STANDEE-INIT', assetId: 'A-0301', mime: 'image/png', title: '槲寄生 初始立绘', alt: 'DRUVIS III 初始立绘', sha1: 'd3mo0101', width: 900, height: 1800 },
  { pageId: 'wiki/profile-advanced', sectionKey: 'stage', role: 'standee', variant: 'insight', displayOrder: 2, objectKey: 'standee-insight.png', mediaId: 'M-ADV-STANDEE-INSIGHT', assetId: 'A-0302', mime: 'image/png', title: '槲寄生 洞悉立绘', alt: 'DRUVIS III 洞悉立绘', sha1: 'd3mo0102', width: 900, height: 1800 },
  { pageId: 'wiki/profile-advanced', sectionKey: 'skills', role: 'skill-icon', variant: 'wind', displayOrder: 1, objectKey: 'skill-wind.png', mediaId: 'M-ADV-SKILL-WIND', assetId: 'A-0303', mime: 'image/png', title: '风入林', alt: '风入林技能图', sha1: 'd3mo0103', width: 320, height: 480 },
  { pageId: 'wiki/profile-advanced', sectionKey: 'skills', role: 'skill-icon', variant: 'dew', displayOrder: 2, objectKey: 'skill-dew.png', mediaId: 'M-ADV-SKILL-DEW', assetId: 'A-0304', mime: 'image/png', title: '露渐白', alt: '露渐白技能图', sha1: 'd3mo0104', width: 320, height: 480 },
  { pageId: 'wiki/profile-advanced', sectionKey: 'skills', role: 'skill-icon', variant: 'ultimate', displayOrder: 3, objectKey: 'skill-ultimate.png', mediaId: 'M-ADV-SKILL-ULT', assetId: 'A-0305', mime: 'image/png', title: '林间，静默将至', alt: '至终的仪式技能图', sha1: 'd3mo0105', width: 320, height: 480 },

  // —— 第 2 页 Archival Dossier：主背景 + 立绘 + 名册缩略图 ——
  { pageId: 'wiki/dossier', sectionKey: 'main', role: 'backdrop', variant: 'archive-hall', displayOrder: 0, objectKey: 'dossier-bg.png', mediaId: 'M-DOS-BG', assetId: 'A-0401', mime: 'image/png', title: '档案馆主背景', alt: '档案馆背景', sha1: 'd3mo0201', width: 1920, height: 1080 },
  { pageId: 'wiki/dossier', sectionKey: 'stage', role: 'portrait', variant: 'druvis', displayOrder: 1, objectKey: 'dossier-portrait.png', mediaId: 'M-DOS-PORTRAIT', assetId: 'A-0402', mime: 'image/png', title: '槲寄生 档案立绘', alt: 'DRUVIS III 档案立绘', sha1: 'd3mo0202', width: 800, height: 1600 },
  { pageId: 'wiki/dossier', sectionKey: 'roster', role: 'thumb', variant: 'druvis', displayOrder: 1, objectKey: 'dossier-roster-druvis.png', mediaId: 'M-DOS-ROSTER-DRUVIS', assetId: 'A-0403', mime: 'image/png', title: '槲寄生', alt: '名册缩略图 槲寄生', sha1: 'd3mo0203', width: 240, height: 360 },
  { pageId: 'wiki/dossier', sectionKey: 'roster', role: 'thumb', variant: 'lilya', displayOrder: 2, objectKey: 'dossier-roster-rednail.png', mediaId: 'M-DOS-ROSTER-LILYA', assetId: 'A-0404', mime: 'image/png', title: '红弩箭', alt: '名册缩略图 红弩箭', sha1: 'd3mo0204', width: 240, height: 360 },
  { pageId: 'wiki/dossier', sectionKey: 'roster', role: 'thumb', variant: 'nick', displayOrder: 3, objectKey: 'dossier-roster-nick.png', mediaId: 'M-DOS-ROSTER-NICK', assetId: 'A-0405', mime: 'image/png', title: '尼克·波顿', alt: '名册缩略图 尼克·波顿', sha1: 'd3mo0205', width: 240, height: 360 },

  // —— 第 4 页 Comprehensive Profile：Hero + 尤提姆插画 + 技能 + 藏品 ——
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'hero', role: 'hero', variant: 'initial', displayOrder: 1, objectKey: 'comp-hero-initial.png', mediaId: 'M-CMP-HERO-INIT', assetId: 'A-0501', mime: 'image/png', title: '槲寄生 初始 Hero', alt: 'DRUVIS III 初始 Hero 图', sha1: 'd3mo0301', width: 1080, height: 1400 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'hero', role: 'hero', variant: 'insight', displayOrder: 2, objectKey: 'comp-hero-insight.png', mediaId: 'M-CMP-HERO-INSIGHT', assetId: 'A-0502', mime: 'image/png', title: '槲寄生 洞悉 Hero', alt: 'DRUVIS III 洞悉 Hero 图', sha1: 'd3mo0302', width: 1080, height: 1400 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'lore', role: 'illustration', variant: 'udimo', displayOrder: 1, objectKey: 'comp-udimo.png', mediaId: 'M-CMP-UDIMO', assetId: 'A-0503', mime: 'image/png', title: '尤提姆 黑猫', alt: '尤提姆插画', sha1: 'd3mo0303', width: 1080, height: 720 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'skills', role: 'skill-icon', variant: 'wind', displayOrder: 1, objectKey: 'skill-wind.png', mediaId: 'M-CMP-SKILL-WIND', assetId: 'A-0303', mime: 'image/png', title: '风入林', alt: '风入林技能图', sha1: 'd3mo0103', width: 320, height: 480 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'skills', role: 'skill-icon', variant: 'dew', displayOrder: 2, objectKey: 'comp-skill-dew.png', mediaId: 'M-CMP-SKILL-DEW', assetId: 'A-0504', mime: 'image/png', title: '露渐白', alt: '露渐白技能图', sha1: 'd3mo0304', width: 640, height: 960 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'skills', role: 'ritual-art', variant: 'ultimate', displayOrder: 3, objectKey: 'comp-ultimate.png', mediaId: 'M-CMP-ULTIMATE', assetId: 'A-0505', mime: 'image/png', title: '林间，静默将至', alt: '至终的仪式演出图', sha1: 'd3mo0305', width: 1080, height: 720 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'collection', role: 'collection-item', variant: 'item-1', displayOrder: 1, objectKey: 'comp-item-1.png', mediaId: 'M-CMP-ITEM-1', assetId: 'A-0506', mime: 'image/png', title: 'Acorn Choker', alt: '藏品 Acorn Choker', sha1: 'd3mo0306', width: 400, height: 400 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'collection', role: 'collection-item', variant: 'item-2', displayOrder: 2, objectKey: 'comp-item-2.png', mediaId: 'M-CMP-ITEM-2', assetId: 'A-0507', mime: 'image/png', title: 'Mistletoe Staff', alt: '藏品 Mistletoe Staff', sha1: 'd3mo0307', width: 400, height: 400 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'collection', role: 'collection-item', variant: 'item-3', displayOrder: 3, objectKey: 'comp-item-3.png', mediaId: 'M-CMP-ITEM-3', assetId: 'A-0508', mime: 'image/png', title: 'Mistletoe Bouquet', alt: '藏品 Mistletoe Bouquet', sha1: 'd3mo0308', width: 400, height: 400 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'collection', role: 'collection-item', variant: 'item-4', displayOrder: 4, objectKey: 'comp-item-4.png', mediaId: 'M-CMP-ITEM-4', assetId: 'A-0509', mime: 'image/png', title: 'Golden Branch', alt: '藏品 Golden Branch', sha1: 'd3mo0309', width: 400, height: 400 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'collection', role: 'collection-item', variant: 'item-5', displayOrder: 5, objectKey: 'comp-item-5.png', mediaId: 'M-CMP-ITEM-5', assetId: 'A-0510', mime: 'image/png', title: 'Pearl Ornament', alt: '藏品 Pearl Ornament', sha1: 'd3mo0310', width: 400, height: 400 },
  { pageId: 'wiki/profile-comprehensive', sectionKey: 'collection', role: 'collection-item', variant: 'item-6', displayOrder: 6, objectKey: 'comp-item-6.png', mediaId: 'M-CMP-ITEM-6', assetId: 'A-0511', mime: 'image/png', title: 'Silk Ribbon', alt: '藏品 Silk Ribbon', sha1: 'd3mo0311', width: 400, height: 400 },
]

// ------------------------------------------------------------
// 【后端运行时】object_key → 公共 URL
// 换域名/端口/HTTPS 只改 publicBaseUrl，映射表零改动。
// ------------------------------------------------------------
function toPublicUrl(objectKey) {
  return `${BACKEND_ONLY.publicBaseUrl}/${objectKey}`
}

// ------------------------------------------------------------
// 【后端出口清洗】对应 models.py sanitize_media_item()
// 1) 非 http(s)/相对公共路径一律丢弃（挡住 minio:9000 这类内部地址）
// 2) 只放行前端契约的 14 个字段；object_key 等一律不出后端
// ------------------------------------------------------------
export function sanitizeMediaLink(row) {
  const url = toPublicUrl(row.objectKey)
  if (!/^(https?:\/\/|\/)/.test(url)) return null
  return {
    mediaId: row.mediaId,
    assetId: row.assetId,
    assetType: row.role,
    mime: row.mime,
    url,
    title: row.title,
    alt: row.alt,
    role: row.role,
    sectionKey: row.sectionKey,
    displayOrder: row.displayOrder,
    sha1: row.sha1,
    width: row.width,
    height: row.height,
    variant: row.variant,
  }
}

// ------------------------------------------------------------
// 【API】GET /api/wiki/pages/{pageId} → mediaLinks[]
// ------------------------------------------------------------
export function getPageMedia(pageId) {
  return WIKI_MEDIA_LINKS
    .filter((row) => row.pageId === pageId)
    .sort((a, b) => a.displayOrder - b.displayOrder)
    .map(sanitizeMediaLink)
    .filter(Boolean)
}

// ------------------------------------------------------------
// 【前端唯一选择器】只按 role + variant + sectionKey (+ displayOrder)
// 决定"放哪、怎么摆" —— 前端对存储拓扑一无所知，也不需要知道。
// ------------------------------------------------------------
export function pickMedia(mediaLinks, { role, variant, sectionKey } = {}) {
  const hit = mediaLinks.find(
    (m) =>
      (role === undefined || m.role === role) &&
      (variant === undefined || m.variant === variant) &&
      (sectionKey === undefined || m.sectionKey === sectionKey),
  )
  return hit ?? null
}

// ------------------------------------------------------------
// 【演示专用】暴露"后端原始行"，供契约检查器对比展示。
// 真实前端代码里不存在这些函数 —— 它们只是这堂课的教具。
// ------------------------------------------------------------
export function _demoRawRow(index = 0) {
  return { ...WIKI_MEDIA_LINKS[index], _backendConfig: { ...BACKEND_ONLY, publicBaseUrl: BACKEND_ONLY.publicBaseUrl } }
}

// 某页面在后端表里的全部原始行（未清洗、含 objectKey）
export function _demoRawRowsForPage(pageId) {
  return WIKI_MEDIA_LINKS
    .filter((row) => row.pageId === pageId)
    .sort((a, b) => a.displayOrder - b.displayOrder)
    .map((row) => ({ ...row }))
}

export function _demoBackendConfig() {
  return { ...BACKEND_ONLY }
}
