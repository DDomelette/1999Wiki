import type { ActionItem } from '../../types'

export function MessageActions({
  actions,
  variant,
  onAction,
}: {
  actions: ActionItem[]
  variant: 'omitted' | 'rescue'
  onAction: (action: ActionItem) => void | Promise<void>
}) {
  if (!actions.length) return null
  const actionKind = variant === 'rescue' ? 'recovery' : 'omitted'
  return (
    <div
      data-action-variant={variant}
      data-animation-slot="message-actions"
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 8,
        marginTop: 10,
        paddingTop: 8,
        borderTop: '1px solid var(--border-subtle)',
      }}
    >
      {actions.map((action, index) => (
        <button
          key={`${action.label}-${index}`}
          type="button"
          data-action-kind={actionKind}
          onClick={() => void onAction(action)}
          style={{
            border: '1px solid var(--border-subtle)',
            borderRadius: variant === 'rescue' ? 14 : 6,
            background: variant === 'rescue' ? 'rgba(201, 166, 107, 0.16)' : 'rgba(255, 255, 255, 0.06)',
            color: 'var(--text-primary)',
            padding: variant === 'rescue' ? '5px 12px' : '6px 10px',
            minHeight: variant === 'rescue' ? 30 : 0,
            cursor: 'pointer',
          }}
        >
          {action.label}
        </button>
      ))}
    </div>
  )
}
