import type { AssetItem, MediaItem } from '../types'

export function mediaBindingIdentity(item: AssetItem | MediaItem): string {
  if ('media_id' in item) {
    return item.binding_id || item.asset_id || item.media_id
  }
  return item.asset_id
}
