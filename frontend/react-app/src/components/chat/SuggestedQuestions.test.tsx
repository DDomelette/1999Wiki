import { describe, expect, it } from 'vitest'
import {
  sampleSuggestedQuestions,
  SUGGESTED_QUESTION_POOL,
} from './SuggestedQuestions'

describe('suggested question pool', () => {
  it('keeps a small curated pool covering the supported discovery topics', () => {
    expect(SUGGESTED_QUESTION_POOL).toHaveLength(12)

    const questions = SUGGESTED_QUESTION_POOL.join(' ')
    for (const topic of ['十四行诗', '心相', '剧情', '世界观', '阵营', '日历']) {
      expect(questions).toContain(topic)
    }
  })
})

describe('sampleSuggestedQuestions', () => {
  it('selects at most four unique questions without mutating the pool', () => {
    const pool = ['A', 'B', 'C', 'D', 'E']

    const selected = sampleSuggestedQuestions(pool, 4, () => 0)

    expect(selected).toEqual(['A', 'B', 'C', 'D'])
    expect(new Set(selected).size).toBe(4)
    expect(pool).toEqual(['A', 'B', 'C', 'D', 'E'])
  })

  it('returns every available item when the pool is smaller than the limit', () => {
    expect(sampleSuggestedQuestions(['A', 'B'], 4, () => 0)).toEqual(['A', 'B'])
  })

  it('returns an empty list for an empty pool', () => {
    expect(sampleSuggestedQuestions([])).toEqual([])
  })
})
