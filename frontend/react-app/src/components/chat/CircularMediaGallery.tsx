import type { AssetItem, MediaItem } from '../../types'
import { mediaBindingIdentity } from '../../media/identity'
import { CircularGallery } from '../animations/reactbits/CircularGallery'

type DisplayAsset = AssetItem | MediaItem
const key = (asset: DisplayAsset) => mediaBindingIdentity(asset)
const label = (asset: DisplayAsset) => asset.alt || ('title' in asset ? asset.title ?? '' : '') || '图片'

export function CircularMediaGallery({ items }: { items: DisplayAsset[] }) {
  return <CircularGallery items={items.map((item) => ({ id: key(item), image: item.url, title: label(item), alt: label(item) }))} bend={0} borderRadius={0.1} />
}
