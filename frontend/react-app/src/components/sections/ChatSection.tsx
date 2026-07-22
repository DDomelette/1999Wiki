import { useEffect, useRef } from 'react'
import { Trash2 } from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { MessageBubble } from '../chat/MessageBubble'
import { ChatInput } from '../chat/ChatInput'
import { AutoHideScrollbar } from '../ui/AutoHideScrollbar'
import { CategorySelect } from '../ui/CategorySelect'

export function ChatSection() {
  const messages = useChatStore((s) => s.messages)
  const clear = useChatStore((s) => s.clear)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const jumpHome = () => {
    document
      .querySelector('[data-snap-section="home"]')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <section
      data-snap-section="chat"
      className="snap-section"
      style={{
        display: 'flex',
        flexDirection: 'column',
        background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-base) 86%, transparent), color-mix(in srgb, var(--bg-base) 92%, transparent))',
        backdropFilter: 'blur(2px)',
      }}
    >
      <div
        style={{
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>检索范围:</span>
        <CategorySelect />
        <button
          type="button"
          title="清空对话"
          aria-label="清空对话"
          onClick={() => void clear()}
          style={{
            width: 36,
            height: 36,
            flex: '0 0 36px',
            marginLeft: 'auto',
            display: 'grid',
            placeItems: 'center',
            padding: 0,
            border: '1px solid var(--border-card)',
            borderRadius: 4,
            background: 'var(--bg-elevated)',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          <Trash2 aria-hidden="true" size={18} />
        </button>
        <button
          type="button"
          onClick={jumpHome}
          style={{
            padding: '6px 14px',
            border: '1px solid var(--border-card)',
            borderRadius: 4,
            background: 'var(--bg-elevated)',
            color: 'var(--accent-gold)',
            fontFamily: 'var(--font-body)',
            fontSize: '0.9rem',
          }}
        >
          返回首页
        </button>
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          position: 'relative',
        }}
      >
        <div
          ref={scrollRef}
          className="native-scrollbar-hidden"
          data-page-wheel-lock="true"
          data-testid="chat-message-scroll"
          style={{
            height: '100%',
            overflowY: 'auto',
            padding: 24,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {messages.length === 0 && (
            <div
              style={{
                margin: 'auto',
                textAlign: 'center',
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-body)',
              }}
            >
              <p style={{ fontSize: '1.5rem', marginBottom: 8, color: 'var(--accent-gold)' }}>
                神秘学问答
              </p>
              <p style={{ fontSize: '0.95rem' }}>
                问问关于人物、心相、剧情、世界、阵营或日历的任何问题
              </p>
            </div>
          )}
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </div>
        <AutoHideScrollbar targetRef={scrollRef} testId="chat-message-scrollbar" variant="local" />
      </div>

      <ChatInput />
    </section>
  )
}
