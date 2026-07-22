import type { CategoryMeta } from '../types'

/** 资料页只保留这三个板块；世界 / 阵营 / 日历不再展示。 */
export const VISIBLE_CATEGORY_KEYS: readonly string[] = ['人物', '心相', '剧情']

export function filterVisibleCategories(categories: CategoryMeta[]): CategoryMeta[] {
  return categories.filter((item) => VISIBLE_CATEGORY_KEYS.includes(item.key) || VISIBLE_CATEGORY_KEYS.includes(item.title))
}

export const FALLBACK_CATEGORIES: CategoryMeta[] = [
  {
    key: '\u4eba\u7269',
    title: '\u4eba\u7269',
    subtitle: 'Characters',
    description: '\u91cd\u8fd4\u672a\u6765:1999 \u4e2d\u7684\u89d2\u8272\u6863\u6848\uff0c\u542b UTTU \u4eba\u7269\u3001\u795e\u79d8\u5b66\u5bb6\u3001\u7ef4\u62c9\u7b49\u9635\u8425\u7684\u82f1\u4f26\u89d2\u8272\u3002',
    doc_count: 0,
    cover_prompt: '',
  },
  {
    key: '\u5fc3\u76f8',
    title: '\u5fc3\u76f8',
    subtitle: 'Psychube',
    description: '\u89d2\u8272\u7684\u7cbe\u795e\u5177\u8c61\u5b66\u5668\uff0c\u8d4b\u4e88\u80fd\u529b\u4e0e\u6545\u4e8b\uff0c\u627f\u8f7d\u795e\u79d8\u5b66\u5bb6\u7684\u8bb0\u5fc6\u3002',
    doc_count: 0,
    cover_prompt: '',
  },
  {
    key: '\u5267\u60c5',
    title: '\u5267\u60c5',
    subtitle: 'Story',
    description: '\u4e3b\u7ebf\u4e0e\u652f\u7ebf\u5267\u60c5\uff0c\u8de8\u8d8a\u4e0d\u540c\u65f6\u4ee3\u7684\u795e\u79d8\u5b66\u4e8b\u4ef6\u3002',
    doc_count: 0,
    cover_prompt: '',
  },
  {
    key: '\u4e16\u754c',
    title: '\u4e16\u754c',
    subtitle: 'World',
    description: '\u4e16\u754c\u89c2\u8bbe\u5b9a\u3001\u795e\u79d8\u5b66\u3001\u66b4\u96e8\u4e0e\u65f6\u4ee3\u53d8\u8fc1\u7684\u80cc\u666f\u77e5\u8bc6\u3002',
    doc_count: 0,
    cover_prompt: '',
  },
  {
    key: '\u9635\u8425',
    title: '\u9635\u8425',
    subtitle: 'Factions',
    description: '\u5404\u5927\u9635\u8425\u4e0e\u7ec4\u7ec7\uff0c\u4ece\u57fa\u91d1\u4f1a\u5230\u795e\u79d8\u5b66\u5bb6\u65cf\u7fa4\u3002',
    doc_count: 0,
    cover_prompt: '',
  },
  {
    key: '\u65e5\u5386',
    title: '\u65e5\u5386',
    subtitle: 'Calendar',
    description: '\u7bb1\u4e2d\u65e5\u5386\u4e0e\u6bcf\u65e5\u795e\u79d8\u5b66\u89c1\u95fb\uff0c\u8bb0\u5f55\u5404\u5730\u7684\u5947\u95fb\u3002',
    doc_count: 0,
    cover_prompt: '',
  },
]
