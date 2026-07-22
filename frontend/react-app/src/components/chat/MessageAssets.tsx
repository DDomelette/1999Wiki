import type { AssetItem, MediaItem, MediaPanel, VoiceLineGroup, VoicePanelPage } from '../../types'
import { mediaBindingIdentity } from '../../media/identity'
import { ImagePanel } from './ImagePanel'
import { VideoPanel } from './VideoPanel'
import { VoicePanel, useVoicePlaybackCoordinator, voicePanelIdentity } from './VoicePanel'

type DisplayAsset = AssetItem | MediaItem

function assetRole(asset: DisplayAsset): string {
  return ('asset_type' in asset ? asset.asset_type : asset.role) || ''
}

function mediaKind(asset: DisplayAsset): 'image' | 'audio' | 'video' {
  const mime = 'mime' in asset ? asset.mime || '' : ''
  const role = assetRole(asset)
  if (mime.startsWith('audio/') || role === 'voice' || role === 'audio') return 'audio'
  if (mime.startsWith('video/') || role === 'video') return 'video'
  return 'image'
}

function toMediaItem(asset: DisplayAsset): MediaItem {
  if ('media_id' in asset) return asset
  return {
    media_id: asset.asset_id,
    asset_id: asset.asset_id,
    asset_type: asset.role,
    role: asset.role,
    alt: asset.alt,
    title: asset.name,
    url: asset.url,
  }
}

function legacyVoicePage(items: MediaItem[]): VoicePanelPage {
  const grouped = new Map<string, VoiceLineGroup>()
  for (const item of items) {
    const lineId = item.child_id || item.media_id
    const current = grouped.get(lineId)
    if (current) {
      if (!current.variants.some((variant) => mediaBindingIdentity(variant) === mediaBindingIdentity(item))) current.variants.push(item)
    } else {
      grouped.set(lineId, {
        voice_line_id: lineId,
        title: item.title || item.alt || item.media_id,
        variants: [item],
      })
    }
  }
  const lines = [...grouped.values()]
  return {
    type: 'voice',
    grouping: 'voice_line',
    entity_id: 'legacy',
    lines,
    page_size: lines.length,
    total_lines: lines.length,
    has_more: false,
    next_cursor: null,
  }
}

function dedupeMedia(items: MediaItem[]): MediaItem[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    const identity = mediaBindingIdentity(item)
    if (seen.has(identity)) return false
    seen.add(identity)
    return true
  })
}

export function MessageAssets({
  assets,
  mediaPanels = [],
  onReloadVoiceFirstPage,
}: {
  assets: DisplayAsset[]
  mediaPanels?: MediaPanel[]
  onReloadVoiceFirstPage?: () => void
}) {
  const playbackCoordinator = useVoicePlaybackCoordinator()
  const voicePanels = mediaPanels.filter((panel): panel is VoicePanelPage => panel.type === 'voice')
  const panelVideoItems = mediaPanels
    .filter((panel) => panel.type === 'video')
    .flatMap((panel) => panel.items)
  const voiceItems = assets.filter((asset) => mediaKind(asset) === 'audio').map(toMediaItem)
  const flatVideoItems = assets.filter((asset) => mediaKind(asset) === 'video').map(toMediaItem)
  const imageItems = assets.filter((asset) => mediaKind(asset) === 'image')
  const videoItems = dedupeMedia([...panelVideoItems, ...flatVideoItems])
  const legacyVoice = voicePanels.length === 0 && voiceItems.length > 0 ? legacyVoicePage(voiceItems) : null

  if (assets.length === 0 && mediaPanels.length === 0) return null
  return (
    <>
      {voicePanels.map((panel) => (
        <VoicePanel
          key={voicePanelIdentity(panel)}
          page={panel}
          onReloadFirstPage={onReloadVoiceFirstPage}
          playbackCoordinator={playbackCoordinator}
        />
      ))}
      {legacyVoice && <VoicePanel page={legacyVoice} playbackCoordinator={playbackCoordinator} />}
      <VideoPanel items={videoItems} />
      <ImagePanel items={imageItems} />
    </>
  )
}
