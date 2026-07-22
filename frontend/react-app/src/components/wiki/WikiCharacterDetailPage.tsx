import { useEffect, useState } from 'react'
import type { CharacterDetailViewModel } from './characterDetailViewModel'
import { DesktopCharacterDossier } from './character-detail/DesktopCharacterDossier'
import { MobileCharacterDossier } from './character-detail/MobileCharacterDossier'
import './WikiCharacterDetailPage.css'

export interface WikiCharacterDetailPageProps {
  viewModel: CharacterDetailViewModel
  onBack(): void
}

const MOBILE_QUERY = '(max-width: 760px)'

function currentMobileState(): boolean {
  if (typeof window.matchMedia === 'function') return window.matchMedia(MOBILE_QUERY).matches
  return window.innerWidth <= 760
}

export function WikiCharacterDetailPage({ viewModel, onBack }: WikiCharacterDetailPageProps) {
  const [mobile, setMobile] = useState(currentMobileState)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined
    const media = window.matchMedia(MOBILE_QUERY)
    const update = (event: MediaQueryListEvent | MediaQueryList) => setMobile(event.matches)
    update(media)
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])

  return (
    <section className="wiki-character-detail" data-testid="wiki-character-detail">
      {mobile
        ? <MobileCharacterDossier viewModel={viewModel} onBack={onBack} />
        : <DesktopCharacterDossier viewModel={viewModel} onBack={onBack} />}
    </section>
  )
}
