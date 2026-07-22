import { useEffect, useState } from 'react'
import { KimiDesktopCharacterDossier } from './KimiDesktopCharacterDossier'
import { KimiMobileCharacterDossier } from './KimiMobileCharacterDossier'
import type { KimiWikiDetailViewModel } from './kimiWikiPreviewViewModel'
import '../wiki/WikiCharacterDetailPage.css'
import './KimiWikiPreview.css'

const MOBILE_QUERY = '(max-width: 760px)'

function currentMobileState(): boolean {
  if (typeof window.matchMedia === 'function') return window.matchMedia(MOBILE_QUERY).matches
  return window.innerWidth <= 760
}

export function KimiWikiCharacterDetailPage({
  model,
  onBack,
}: {
  model: KimiWikiDetailViewModel
  onBack(): void
}) {
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
    <section className="kimi-wiki-detail" data-testid="kimi-wiki-character-detail">
      {mobile
        ? <KimiMobileCharacterDossier model={model} onBack={onBack} />
        : <KimiDesktopCharacterDossier model={model} onBack={onBack} />}
    </section>
  )
}
