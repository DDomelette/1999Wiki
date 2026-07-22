import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import {
  sampleSuggestedQuestions,
  SUGGESTED_QUESTION_POOL,
  SuggestedQuestions,
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

  it('does not return duplicate question text from a duplicated pool', () => {
    expect(sampleSuggestedQuestions(['A', 'A', 'B', 'C'], 4, () => 0)).toEqual([
      'A',
      'B',
      'C',
    ])
  })

  it('returns an empty list for an empty pool', () => {
    expect(sampleSuggestedQuestions([])).toEqual([])
  })
})

describe('SuggestedQuestions', () => {
  it('renders an accessible group and reports the selected question', () => {
    const onSelect = vi.fn()
    render(
      <SuggestedQuestions
        disabled={false}
        questions={['问题一', '问题二', '问题三', '问题四']}
        onSelect={onSelect}
      />,
    )

    const group = screen.getByRole('group', { name: '推荐问题' })
    expect(within(group).getAllByRole('button')).toHaveLength(4)

    fireEvent.click(within(group).getByRole('button', { name: '问题二' }))
    expect(onSelect).toHaveBeenCalledOnce()
    expect(onSelect).toHaveBeenCalledWith('问题二')
  })

  it('uses non-submitting buttons and disables each one when requested', () => {
    render(
      <SuggestedQuestions
        disabled
        questions={['问题一', '问题二']}
        onSelect={vi.fn()}
      />,
    )

    for (const button of screen.getAllByRole('button')) {
      expect(button).toHaveAttribute('type', 'button')
      expect(button).toBeDisabled()
    }
  })

  it('keeps the sampled group stable across rerenders', () => {
    const { rerender } = render(
      <SuggestedQuestions disabled={false} onSelect={vi.fn()} />,
    )
    const group = screen.getByRole('group', { name: '推荐问题' })
    const before = within(group).getAllByRole('button').map((button) => button.textContent)

    rerender(<SuggestedQuestions disabled onSelect={vi.fn()} />)

    const after = within(group).getAllByRole('button').map((button) => button.textContent)
    expect(after).toEqual(before)
  })
})
