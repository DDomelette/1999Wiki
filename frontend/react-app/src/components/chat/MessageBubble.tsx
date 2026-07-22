import { motion } from 'framer-motion'
import type { AssetItem, MediaItem, Message } from '../../types'
import { MarkdownContent } from './MarkdownContent'
import { MessageAssets } from './MessageAssets'
import { MessageActions } from './MessageActions'
import { useChatStore } from '../../store/chatStore'

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
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
      style={{
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        maxWidth: '70%',
        padding: '12px 16px',
        background: isUser ? 'var(--accent-purple)' : 'var(--bg-elevated)',
        color: isUser ? '#fff' : 'var(--text-primary)',
        borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
        border: isUser ? 'none' : '1px solid var(--border-card)',
        fontFamily: 'var(--font-body)',
        fontSize: '1rem',
        lineHeight: 1.6,
        marginBottom: 12,
        boxShadow: 'var(--shadow-card)',
      }}
    >
      {isUser ? (
        message.content
      ) : (
        <>
          {message.status && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{
                marginBottom: message.content ? 6 : 0,
                color: 'var(--accent-gold)',
                fontSize: '0.875rem',
              }}
            >
              {message.status}
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
