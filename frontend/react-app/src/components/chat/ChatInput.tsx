import { useRef, useState } from 'react'
import { useChatStore } from '../../store/chatStore'
import { SuggestedQuestions } from './SuggestedQuestions'

export function ChatInput() {
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const send = useChatStore((s) => s.send)
  const sending = useChatStore((s) => s.sending)
  const abort = useChatStore((s) => s.abort)
  const routeOptions = useChatStore((s) => s.routeOptions)
  const setRouteOption = useChatStore((s) => s.setRouteOption)
  const [lastError, setLastError] = useState<string | null>(null)
  const [lastQuestion, setLastQuestion] = useState('')

  const selectSuggestedQuestion = (question: string) => {
    setValue(question)
    inputRef.current?.focus()
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const v = value.trim()
    if (!v || sending) return
    setLastQuestion(v)
    setLastError(null)
    setValue('')
    void send(v).then(() => {
      const last = useChatStore.getState().messages.slice(-1)[0]
      if (last?.role !== 'assistant') return
      if (last.phase === 'failed') {
        setLastError(last.partialError ? '回答未完成，未经过引用校验。' : last.content)
      }
      else if (last.content.startsWith('请求失败:') || last.content.startsWith('错误:')) {
        setLastError(last.content)
      }
    })
  }

  const onRetry = () => {
    if (!lastQuestion || sending) return
    setLastError(null)
    useChatStore.setState((s) => ({ messages: s.messages.slice(0, -2) }))
    void send(lastQuestion)
  }

  const modeButton = (key: 'expanded' | 'freeSupplement', label: string) => {
    const active = routeOptions[key]
    return (
      <button
        type="button"
        className="chat-input__mode"
        aria-pressed={active}
        data-active={active || undefined}
        data-action-kind="route-mode"
        disabled={sending}
        onClick={() => setRouteOption(key, !active)}
      >
        {label}
      </button>
    )
  }

  return (
    <div className="chat-input">
      {lastError && (
        <div className="chat-input__error" role="alert">
          <span className="chat-input__error-text">{lastError}</span>
          <button
            type="button"
            className="chat-input__retry"
            onClick={onRetry}
            disabled={sending}
          >
            重试
          </button>
        </div>
      )}
      <form
        onSubmit={onSubmit}
        className="chat-input__form"
      >
        <div className="chat-input__inner">
          <SuggestedQuestions
            disabled={sending}
            onSelect={selectSuggestedQuestion}
          />
          <div className="chat-input__row">
            <input
              ref={inputRef}
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="输入问题..."
              aria-label="输入问题"
              enterKeyHint="send"
              className="chat-input__field"
            />
            <button
              type={sending ? 'button' : 'submit'}
              className={`chat-input__send${sending ? ' chat-input__send--stop' : ''}`}
              disabled={!sending && !value.trim()}
              onClick={sending ? abort : undefined}
            >
              {sending ? '停止' : '发送'}
            </button>
          </div>
          <div className="chat-input__modes" role="group" aria-label="检索选项">
            {modeButton('expanded', '扩大检索')}
            {modeButton('freeSupplement', '自由补充')}
          </div>
        </div>
      </form>
    </div>
  )
}
