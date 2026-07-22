import { useChatStore } from '../../store/chatStore'

const OPTIONS: { value: string | null; label: string }[] = [
  { value: null, label: '全部' },
  { value: '人物', label: '人物' },
  { value: '心相', label: '心相' },
  { value: '剧情', label: '剧情' },
  { value: '世界', label: '世界' },
  { value: '阵营', label: '阵营' },
  { value: '日历', label: '日历' },
]

export function CategorySelect() {
  const category = useChatStore((s) => s.category)
  const setCategory = useChatStore((s) => s.setCategory)
  return (
    <select
      value={category ?? ''}
      onChange={(e) => setCategory(e.target.value || null)}
      style={{
        padding: '6px 12px',
        background: 'var(--bg-elevated)',
        color: 'var(--text-primary)',
        border: '1px solid var(--border-card)',
        borderRadius: 4,
        fontFamily: 'var(--font-body)',
        fontSize: '0.95rem',
        cursor: 'pointer',
      }}
    >
      {OPTIONS.map((o) => (
        <option key={o.label} value={o.value ?? ''}>{o.label}</option>
      ))}
    </select>
  )
}
