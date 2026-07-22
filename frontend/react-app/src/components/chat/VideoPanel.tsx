import type { MediaItem } from '../../types'

export function VideoPanel({ items }: { items: MediaItem[] }) {
  if (!items.length) return null
  const [primary, ...rest] = items
  return (
    <div
      data-testid="video-panel"
      data-animation-slot="video-panel"
      style={{ display: 'grid', gap: 8, marginTop: 12 }}
    >
      <video
        src={primary.url}
        title={primary.title || primary.alt || primary.media_id}
        controls
        style={{
          width: '100%',
          maxHeight: 260,
          borderRadius: 8,
          background: '#000',
          border: '1px solid var(--border-subtle)',
        }}
      />
      {rest.length ? (
        <button
          type="button"
          aria-label={`更多视频 ${rest.length}`}
          style={{
            border: '1px solid var(--border-subtle)',
            borderRadius: 6,
            background: 'rgba(255, 255, 255, 0.06)',
            color: 'var(--text-primary)',
            padding: '6px 10px',
            cursor: 'pointer',
          }}
        >
          更多视频 {rest.length}
        </button>
      ) : null}
    </div>
  )
}
