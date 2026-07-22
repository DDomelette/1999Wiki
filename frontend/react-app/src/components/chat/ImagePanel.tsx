import type { AssetItem, MediaItem } from '../../types'
import { CircularMediaGallery } from './CircularMediaGallery'

export function ImagePanel({ items }: { items: Array<AssetItem | MediaItem> }) {
  if (!items.length) return null
  return <div data-testid="image-panel" data-animation-slot="image-panel" className="native-scrollbar-hidden"><CircularMediaGallery items={items} /></div>
}
