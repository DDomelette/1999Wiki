import { useEffect, useMemo, useState } from 'react'
import { TiltedImageCard } from '../ui/TiltedImageCard'
import type { WikiMediaViewModel } from './wikiViewModel'
import './WikiHeroStage.css'

interface WikiHeroStageProps {
  title: string
  candidates: readonly WikiMediaViewModel[]
  emptyLabel: string
  activeIndex?: number
  onActiveIndexChange?(index: number): void
}

export function WikiHeroStage({
  title,
  candidates,
  emptyLabel,
  activeIndex,
  onActiveIndexChange,
}: WikiHeroStageProps) {
  const [internalIndex, setInternalIndex] = useState(activeIndex ?? 0)
  const [failedUrls, setFailedUrls] = useState<Set<string>>(() => new Set())
  const candidateKey = useMemo(() => candidates.map((item) => `${item.id}:${item.url}`).join('|'), [candidates])

  useEffect(() => {
    setFailedUrls(new Set())
    setInternalIndex(activeIndex ?? 0)
  }, [candidateKey])

  const requestedIndex = activeIndex ?? internalIndex
  const resolvedIndex = resolveActiveIndex(candidates, failedUrls, requestedIndex)
  const active = resolvedIndex >= 0 ? candidates[resolvedIndex] : null

  const markFailed = (url: string) => {
    const nextFailed = new Set(failedUrls)
    nextFailed.add(url)
    setFailedUrls(nextFailed)

    const nextIndex = resolveActiveIndex(candidates, nextFailed, requestedIndex)
    if (nextIndex < 0 || nextIndex === requestedIndex) return
    setInternalIndex(nextIndex)
    onActiveIndexChange?.(nextIndex)
  }

  return (
    <figure
      className="wiki-hero-stage"
      data-testid="wiki-hero-stage"
      data-empty={active ? 'false' : 'true'}
      style={{ border: 'none', background: 'transparent' }}
    >
      <figcaption className="sr-only">{title}</figcaption>
      {active ? (
        <TiltedImageCard
          key={active.url}
          src={active.url}
          alt={active.title || title}
          className="wiki-hero-stage__tilted-card"
          containerStyle={{ width: 'min(100%, 44rem)', height: 'min(72dvh, 58rem)', minWidth: 0, maxHeight: 'none' }}
          imageStyle={{ objectFit: 'contain', background: 'transparent' }}
          onImageError={() => markFailed(active.url)}
        />
      ) : (
        <div className="archive-empty wiki-hero-stage__empty" role="status">{emptyLabel}</div>
      )}
    </figure>
  )
}

function resolveActiveIndex(
  candidates: readonly WikiMediaViewModel[],
  failedUrls: ReadonlySet<string>,
  requestedIndex: number,
): number {
  if (candidates[requestedIndex] && !failedUrls.has(candidates[requestedIndex].url)) return requestedIndex

  for (let offset = 1; offset <= candidates.length; offset += 1) {
    const index = (Math.max(requestedIndex, 0) + offset) % candidates.length
    if (!failedUrls.has(candidates[index].url)) return index
  }
  return -1
}
