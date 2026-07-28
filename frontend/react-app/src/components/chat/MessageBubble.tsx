import { motion } from 'framer-motion'
import type { AssetItem, MediaItem, Message, StreamPhase } from '../../types'
import { MarkdownContent } from './MarkdownContent'
import { MessageAssets } from './MessageAssets'
import { MessageActions } from './MessageActions'
import { useChatStore } from '../../store/chatStore'

const STREAM_PHASE_LABELS: Partial<Record<StreamPhase, string>> = {
  understanding: '正在理解问题…',
  retrieving: '正在检索资料…',
  generating: '正在生成回答…',
  validating: '正在校验引用…',
  cancelled: '已停止生成',
  failed: '回答生成失败',
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  const phaseLabel = message.phase ? STREAM_PHASE_LABELS[message.phase] : undefined
  const statusText = phaseLabel ?? message.status
  const runAction = useChatStore((s) => s.runAction)
  const messages = useChatStore((s) => s.messages)
  const send = useChatStore((s) => s.send)
  const mediaPanels = !isUser ? (message.mediaPanels ?? []) : []
  const hasStructuredVoice = mediaPanels.some((panel) => panel.type === 'voice')
  const compatibilityAttachments: Array<AssetItem | MediaItem> = !isUser
    ? ((message.media?.length ? message.media : message.assets) || [])
    : []
  const attachments = hasStructuredVoice
    ? compatibilityAttachments.filter((item) => {
        const role = ('asset_type' in item ? item.asset_type : item.role) || ''
        const mime = 'mime' in item ? item.mime || '' : ''
        return !(mime.startsWith('audio/') || role === 'voice' || role === 'audio')
      })
    : compatibilityAttachments
  const hasMessageMedia = attachments.length > 0 || mediaPanels.length > 0
  const messageIndex = messages.findIndex((item) => item.id === message.id)
  const precedingQuestion = messageIndex > 0
    ? messages.slice(0, messageIndex).reverse().find((item) => item.role === 'user')?.content
    : undefined
  const reloadVoiceFirstPage = precedingQuestion
    ? () => {
        if (!useChatStore.getState().sending) void send(precedingQuestion)
      }
    : undefined
  return (
    <motion.div
      data-animation-slot="message-shell"
      initial={isUser ? { scale: 1.3, opacity: 0 } : { opacity: 0 }}
      animate={isUser ? { scale: 1, opacity: 1 } : { opacity: 1 }}
      transition={isUser ? { type: 'spring', stiffness: 300, damping: 20 } : { duration: 0.3 }}
      className={`message-bubble message-bubble--${isUser ? 'user' : 'assistant'}`}
    >
      {isUser ? (
        message.content
      ) : (
        <>
          {statusText && (
            <motion.div
              role="status"
              aria-live="polite"
              data-stream-phase={phaseLabel ? message.phase : undefined}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="message-bubble__stream-status"
            >
              {statusText}
            </motion.div>
          )}
          {!message.streaming && message.planningWarning && (
            <div
              data-animation-slot="message-planning"
              style={{
                marginBottom: 6,
                color: 'var(--accent-gold)',
                fontSize: '0.8rem',
              }}
            >
              {message.planningWarning}
            </div>
          )}
          <div data-message-content="true" data-animation-slot="message-body">
            <MarkdownContent text={message.content} streaming={!!message.streaming} />
          </div>
          {message.correctionNotice && (
            <div
              data-correction-notice="true"
              className="message-bubble__correction-notice"
            >
              已完成引用校验并修正
            </div>
          )}
          {message.partialError && (
            <div
              data-partial-error="true"
              className="message-bubble__partial-error"
            >
              回答未完成，未经过引用校验
            </div>
          )}
          {!message.streaming && hasMessageMedia && (
            <div data-message-media="true" data-animation-slot="message-media">
              <MessageAssets
                assets={attachments}
                mediaPanels={mediaPanels}
                onReloadVoiceFirstPage={reloadVoiceFirstPage}
              />
            </div>
          )}
        </>
      )}
      {!isUser && message.sources && message.sources.length > 0 && !message.streaming && (
        <motion.div
          data-animation-slot="message-sources"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          style={{
            marginTop: 8, paddingTop: 8,
            borderTop: '1px solid var(--border-subtle)',
            fontSize: '0.875rem',
            color: 'var(--text-secondary)',
          }}
        >
          <span style={{ color: 'var(--accent-gold)' }}>来源:</span>{' '}
          {message.sources.map((s, i) => (
            <span key={i}>
              {s.citation_id ? `[${s.citation_id}] ` : ''}{s.name}
              {i < message.sources!.length - 1 ? ' · ' : ''}
            </span>
          ))}
        </motion.div>
      )}
      {!isUser && !message.streaming && message.omittedActions?.length ? (
        <MessageActions actions={message.omittedActions} variant="omitted" onAction={runAction} />
      ) : null}
      {!isUser && !message.streaming && message.failureActions?.length ? (
        <MessageActions actions={message.failureActions} variant="rescue" onAction={runAction} />
      ) : null}
    </motion.div>
  )
}
