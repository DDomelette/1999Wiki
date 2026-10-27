import { useEffect, useRef } from 'react'
import { Trash2 } from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { useChatPageBoundaryNavigation } from '../../hooks/useChatPageBoundaryNavigation'
import { navigateToMainSection } from '../../navigation/mainSectionNavigation'
import { MessageBubble } from '../chat/MessageBubble'
import { ChatInput } from '../chat/ChatInput'
import { AutoHideScrollbar } from '../ui/AutoHideScrollbar'
import { CategorySelect } from '../ui/CategorySelect'
import './ChatSection.css'

const AUTO_SCROLL_THRESHOLD = 96

export function ChatSection() {
  const messages = useChatStore((s) => s.messages)
  const clear = useChatStore((s) => s.clear)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const previousMessageCountRef = useRef(0)
  useChatPageBoundaryNavigation(scrollRef)

  useEffect(() => {
    const addedMessages = messages.slice(previousMessageCountRef.current)
    if (messages.length === 0 || addedMessages.some((message) => message.role === 'user')) {
      stickToBottomRef.current = true
    }
    if (stickToBottomRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
    previousMessageCountRef.current = messages.length
  }, [messages])

  const updateAutoScrollPreference = () => {
    const element = scrollRef.current
    if (!element) return
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight
    stickToBottomRef.current = distanceFromBottom <= AUTO_SCROLL_THRESHOLD
  }

  const handleClear = async () => {
    if (messages.length === 0) return
    if (!window.confirm('确定清空当前对话吗？此操作无法撤销。')) return
    await clear()
  }

  const jumpHome = () => {
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    navigateToMainSection({ kind: 'home' }, { behavior: reducedMotion ? 'auto' : 'smooth', history: 'push' })
  }

  return (
    <section
      data-snap-section="chat"
      className="snap-section chat-section"
    >
      <div className="chat-section__toolbar">
        <div className="chat-section__toolbar-inner">
          <span className="chat-section__toolbar-label">检索范围：</span>
          <CategorySelect />
          <button
            type="button"
            title="清空对话"
            aria-label="清空对话"
            className="chat-section__clear"
            disabled={messages.length === 0}
            onClick={() => void handleClear()}
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
      </div>

      <div className="chat-section__message-shell">
        <div
          ref={scrollRef}
          className="native-scrollbar-hidden chat-section__messages"
          data-page-wheel-lock="true"
          data-testid="chat-message-scroll"
          onScroll={updateAutoScrollPreference}
        >
          {messages.length === 0 && (
            <div className="chat-section__empty">
              <p className="chat-section__empty-kicker">REVERSE: 1999 · ARCANUM ARCHIVE</p>
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
