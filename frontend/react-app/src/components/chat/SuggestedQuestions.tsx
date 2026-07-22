export const SUGGESTED_QUESTION_POOL = [
  '十四行诗是怎样的人？',
  '维尔汀经历过哪些重要事件？',
  '介绍一下槲寄生的背景故事',
  '《重返未来：1999》的世界观是怎样的？',
  '“暴雨”是什么，它会带来什么影响？',
  '圣洛夫基金会是怎样的组织？',
  '拉普拉斯科算中心负责什么？',
  '不同阵营之间有什么关系？',
  '心相在故事中代表什么？',
  '箱中日历记录了哪些重要事件？',
  '1999 年发生了什么？',
  '有哪些与新巴别塔有关的剧情？',
] as const

export function sampleSuggestedQuestions(
  pool: readonly string[],
  count = 4,
  random: () => number = Math.random,
): string[] {
  const candidates = [...pool]
  const selected: string[] = []

  while (selected.length < count && candidates.length > 0) {
    const index = Math.floor(random() * candidates.length)
    selected.push(...candidates.splice(index, 1))
  }

  return selected
}
