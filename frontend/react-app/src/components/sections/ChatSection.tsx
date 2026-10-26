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

export function ChatSection() {
  const messages = useChatStore((s) => s.messages)
  const clear = useChatStore((s) => s.clear)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const previousMessageCountRef = useRef(messages.length)
  useChatPageBoundaryNavigation(scrollRef)

  useEffect(() => {
    const previousCount = previousMessageCountRef.current
    const hasNewUserMessage = messages.length > previousCount
      && messages.slice(previousCount).some((message) => message.role === 'user')
    previousMessageCountRef.current = messages.length
    if (hasNewUserMessage) stickToBottomRef.current = true
    if (scrollRef.current && stickToBottomRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const precedingQuestions = new Map<string, string | undefined>()
  let latestQuestion: string | undefined
  for (const message of messages) {
    if (message.role === 'user') latestQuestion = message.content
    else precedingQuestions.set(message.id, latestQuestion)
  }

  const handleMessageScroll = () => {
    const element = scrollRef.current
    if (!element) return
    stickToBottomRef.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80
  }

  const handleClear = () => {
    if (messages.length === 0) return
    if (window.confirm('确定清空当前对话吗？此操作无法撤销。')) void clear()
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
        <span className="chat-section__archive-id" aria-hidden="true">INQUIRY_DESK / 04</span>
        <span className="chat-section__toolbar-label">检索范围:</span>
        <CategorySelect />
        <button
          type="button"
          title="清空对话"
          aria-label="清空对话"
          className="chat-section__clear"
          disabled={messages.length === 0}
          onClick={handleClear}
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
          onScroll={handleMessageScroll}
        >
          {messages.length === 0 && (
            <div className="chat-section__empty">
              <span className="chat-section__empty-index" aria-hidden="true">04</span>
              <p className="chat-section__empty-eyebrow">ARCANUM_INQUIRY / RAG ARCHIVE</p>
              <h2 className="chat-section__empty-title">神秘学问答</h2>
              <p className="chat-section__empty-description">检索人物、心相、剧情与世界档案。每一次提问，都会留下可追溯的资料来源。</p>
              <div className="chat-section__empty-register" role="group" aria-label="可检索档案类别">
                <span>人物</span><span>心相</span><span>剧情</span><span>世界</span><span>阵营</span><span>日历</span>
              </div>
              <p className="chat-section__empty-hint">从下方选择一条档案索引，或输入你的问题。</p>
            </div>
          )}
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              precedingQuestion={message.role === 'assistant' ? precedingQuestions.get(message.id) : undefined}
            />
          ))}
        </div>
        <AutoHideScrollbar targetRef={scrollRef} testId="chat-message-scrollbar" variant="local" />
      </div>

      <ChatInput />
    </section>
  )
}
