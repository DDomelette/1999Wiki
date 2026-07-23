import { useState } from 'react'
import './SuggestedQuestions.css'

export const SUGGESTED_QUESTION_POOL = [
  '介绍一下十四行诗',
  '介绍一下槲寄生',
  '介绍一下苏芙比',
  '介绍一下未锈铠',
  '介绍一下星锑',
  '介绍一下百夫长',
  '介绍一下玛蒂尔达',
  '介绍一下牙仙',
  '十四行诗的技能是什么？',
  '槲寄生的技能是什么？',
  '苏芙比的基础资料有哪些？',
  '玛蒂尔达的基础资料有哪些？',
] as const

export function sampleSuggestedQuestions(
  pool: readonly string[],
  count = 4,
  random: () => number = Math.random,
): string[] {
  const candidates = [...new Set(pool)]
  const selected: string[] = []

  while (selected.length < count && candidates.length > 0) {
    const index = Math.floor(random() * candidates.length)
    selected.push(...candidates.splice(index, 1))
  }

  return selected
}

interface SuggestedQuestionsProps {
  disabled: boolean
  onSelect: (question: string) => void
  questions?: readonly string[]
}

export function SuggestedQuestions({
  disabled,
  onSelect,
  questions,
}: SuggestedQuestionsProps) {
  const [suggestions] = useState(() =>
    questions ? [...questions] : sampleSuggestedQuestions(SUGGESTED_QUESTION_POOL),
  )

  return (
    <div className="suggested-questions" role="group" aria-label="推荐问题">
      <span className="suggested-questions__label">试着问问</span>
      <div className="suggested-questions__list">
        {suggestions.map((question) => (
          <button
            className="suggested-questions__item"
            key={question}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(question)}
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  )
}
