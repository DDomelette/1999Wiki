import { useEffect, useRef } from 'react'
import { Trash2 } from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { MessageBubble } from '../chat/MessageBubble'
import { ChatInput } from '../chat/ChatInput'
import { AutoHideScrollbar } from '../ui/AutoHideScrollbar'
import { CategorySelect } from '../ui/CategorySelect'
import './ChatSection.css'

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
      className="snap-section chat-section"
    >
      <div className="chat-section__toolbar">
        <span className="chat-section__toolbar-label">检索范围:</span>
        <CategorySelect />
        <button
          type="button"
          title="清空对话"
          aria-label="清空对话"
          className="chat-section__clear"
          onClick={() => void clear()}
        >
          <Trash2 aria-hidden="true" size={18} />
        </button>
        <button
          type="button"
          className="chat-section__home"
          onClick={jumpHome}
        >
          返回首页
        </button>
      </div>

      <div className="chat-section__message-shell">
        <div
          ref={scrollRef}
          className="native-scrollbar-hidden chat-section__messages"
          data-page-wheel-lock="true"
          data-testid="chat-message-scroll"
        >
          {messages.length === 0 && (
            <div className="chat-section__empty">
              <p className="chat-section__empty-title">神秘学问答</p>
              <p>问问关于人物、心相、剧情、世界、阵营或日历的任何问题</p>
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
