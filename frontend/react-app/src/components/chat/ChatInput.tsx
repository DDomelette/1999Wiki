import { useState } from 'react'
import { useChatStore } from '../../store/chatStore'

export function ChatInput() {
  const [value, setValue] = useState('')
  const send = useChatStore((s) => s.send)
  const sending = useChatStore((s) => s.sending)
  const routeOptions = useChatStore((s) => s.routeOptions)
  const setRouteOption = useChatStore((s) => s.setRouteOption)
  const [lastError, setLastError] = useState<string | null>(null)
  const [lastQuestion, setLastQuestion] = useState('')

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const v = value.trim()
    if (!v || sending) return
    setLastQuestion(v)
    setLastError(null)
    setValue('')
    send(v).then(() => {
      const last = useChatStore.getState().messages.slice(-1)[0]
      if (last && (last.content.startsWith('请求失败:') || last.content.startsWith('错误:'))) {
        setLastError(last.content)
      }
    })
  }

  const onRetry = () => {
    if (!lastQuestion || sending) return
    setLastError(null)
    useChatStore.setState((s) => ({ messages: s.messages.slice(0, -2) }))
    send(lastQuestion)
  }

  const modeButton = (key: 'expanded' | 'freeSupplement', label: string) => {
    const active = routeOptions[key]
    return (
      <button
        type="button"
        aria-pressed={active}
        data-action-kind="route-mode"
        onClick={() => setRouteOption(key, !active)}
        style={{
          minHeight: 34,
          padding: '6px 14px',
          borderRadius: 16,
          border: `1px solid ${active ? 'var(--accent-gold)' : 'var(--border-card)'}`,
          background: active ? 'rgba(174, 125, 16, 0.92)' : 'rgba(0, 0, 0, 0.12)',
          color: active ? 'var(--bg-base)' : 'var(--text-secondary)',
          fontFamily: 'var(--font-body)',
          fontSize: '0.9rem',
          cursor: 'pointer',
        }}
      >
        {label}
      </button>
    )
  }

  return (
    <div>
      {lastError && (
        <div style={{ padding: '8px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--accent-rust)', color: '#fff' }}>
          <span style={{ fontSize: '0.85rem' }}>{lastError}</span>
          <button
            onClick={onRetry}
            disabled={sending}
            style={{
              padding: '4px 12px',
              background: 'rgba(255,255,255,0.2)',
              color: '#fff',
              border: '1px solid rgba(255,255,255,0.4)',
              borderRadius: 3,
              cursor: sending ? 'not-allowed' : 'pointer',
            }}
          >
            重试
          </button>
        </div>
      )}
      <form
        onSubmit={onSubmit}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          padding: 16,
          background: 'var(--bg-overlay)',
          backdropFilter: 'blur(12px)',
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="输入问题..."
            style={{
              flex: 1, padding: '10px 14px',
              background: 'var(--bg-elevated)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-card)',
              borderRadius: 4,
              fontFamily: 'var(--font-body)',
              fontSize: '1rem',
            }}
          />
          <button
            type="submit"
            disabled={sending || !value.trim()}
            style={{
              padding: '10px 24px',
              background: 'var(--accent-gold)',
              color: 'var(--bg-base)',
              border: 'none',
              borderRadius: 4,
              fontFamily: 'var(--font-body)',
              fontWeight: 500,
              cursor: sending ? 'not-allowed' : 'pointer',
              opacity: sending || !value.trim() ? 0.5 : 1,
            }}
          >
            发送
          </button>
        </div>
        <div className="chat-input-modes" style={{ display: 'flex', gap: 8 }}>
          {modeButton('expanded', '扩大检索')}
          {modeButton('freeSupplement', '自由补充')}
        </div>
      </form>
    </div>
  )
}
