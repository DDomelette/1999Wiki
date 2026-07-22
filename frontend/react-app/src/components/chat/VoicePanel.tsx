import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { fetchVoicePage, VoicePageError } from '../../api/media'
import type { MediaItem, VoiceLineGroup, VoicePanelPage } from '../../types'
import { mediaBindingIdentity } from '../../media/identity'
import { AnimatedVoiceList } from './AnimatedVoiceList'
import './VoicePanel.css'

const LANGUAGE_PRIORITY = ['zh', 'zh-hant', 'en', 'jp', 'kr']
const sessionLanguagePreferences = new Map<string, string>()

export function clearVoiceSessionPreferencesForTest() {
  sessionLanguagePreferences.clear()
}

function languageKey(variant: MediaItem): string {
  return variant.language?.trim().toLowerCase() || 'other'
}

function preferredLanguage(line: VoiceLineGroup): string {
  const languages = line.variants.map(languageKey)
  return LANGUAGE_PRIORITY.find((language) => languages.includes(language)) ?? languages[0] ?? 'other'
}

function mergeLines(current: VoiceLineGroup[], incoming: VoiceLineGroup[]): VoiceLineGroup[] {
  const merged = current.map((line) => ({ ...line, variants: [...line.variants] }))
  const lineIndexes = new Map(merged.map((line, index) => [line.voice_line_id, index]))
  const bindingIds = new Set(merged.flatMap((line) => line.variants.map(mediaBindingIdentity)))

  for (const line of incoming) {
    const uniqueVariants = line.variants.filter((variant) => {
      const identity = mediaBindingIdentity(variant)
      if (bindingIds.has(identity)) return false
      bindingIds.add(identity)
      return true
    })
    const existingIndex = lineIndexes.get(line.voice_line_id)
    if (existingIndex !== undefined) {
      merged[existingIndex].variants.push(...uniqueVariants)
    } else if (uniqueVariants.length > 0) {
      lineIndexes.set(line.voice_line_id, merged.length)
      merged.push({ ...line, variants: uniqueVariants })
    }
  }
  return merged
}

export function voicePanelIdentity(page: VoicePanelPage): string {
  const lineIdentity = page.lines
    .map((line) => `${line.voice_line_id}:${line.variants.map(mediaBindingIdentity).join(',')}`)
    .join(';')
  return `${page.entity_id}|${page.total_lines}|${page.next_cursor ?? ''}|${lineIdentity}`
}

type PageError = 'retry' | 'reload-first-page' | null

export interface VoicePlaybackCoordinator {
  activePlaybackId: string | null
  activeProgress: number
  pause: (playbackId: string) => void
  play: (ownerIdentity: string, playbackId: string, url: string) => void
  seek: (playbackId: string, progress: number) => void
  stop: () => void
  stopIfOwned: (ownerIdentity: string) => void
}

export function useVoicePlaybackCoordinator(): VoicePlaybackCoordinator {
  const [activePlaybackId, setActivePlaybackId] = useState<string | null>(null)
  const [activeProgress, setActiveProgress] = useState(0)
  const activePlaybackIdRef = useRef<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const playbackGenerationRef = useRef(0)
  const sourceIdentityRef = useRef<string | null>(null)
  const sourceOwnerRef = useRef<string | null>(null)

  const setActivePlayback = useCallback((playbackId: string | null) => {
    activePlaybackIdRef.current = playbackId
    setActivePlaybackId(playbackId)
    if (playbackId === null) setActiveProgress(0)
  }, [])

  const stopCurrent = useCallback((clearSource: boolean) => {
    playbackGenerationRef.current += 1
    sourceIdentityRef.current = null
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.currentTime = 0
      audio.onended = null
      audio.ontimeupdate = null
      if (clearSource) {
        audio.removeAttribute('src')
        audio.load()
      }
    }
    if (clearSource) sourceOwnerRef.current = null
    setActivePlayback(null)
  }, [setActivePlayback])

  const stop = useCallback(() => {
    stopCurrent(false)
  }, [stopCurrent])

  const stopIfOwned = useCallback((ownerIdentity: string) => {
    if (sourceOwnerRef.current !== ownerIdentity) return
    stopCurrent(true)
  }, [stopCurrent])

  const pause = useCallback((playbackId: string) => {
    if (activePlaybackIdRef.current !== playbackId) return
    playbackGenerationRef.current += 1
    sourceIdentityRef.current = null
    audioRef.current?.pause()
    setActivePlayback(null)
  }, [setActivePlayback])

  const play = useCallback((ownerIdentity: string, playbackId: string, url: string) => {
    const generation = playbackGenerationRef.current + 1
    playbackGenerationRef.current = generation
    const sourceIdentity = `${playbackId}|${url}`
    sourceIdentityRef.current = sourceIdentity
    sourceOwnerRef.current = ownerIdentity
    const current = audioRef.current
    if (current) {
      current.pause()
      current.currentTime = 0
      current.onended = null
      current.ontimeupdate = null
    }
    const audio = current ?? new Audio()
    audioRef.current = audio
    audio.src = url
    const isCurrentPlayback = () =>
      playbackGenerationRef.current === generation && sourceIdentityRef.current === sourceIdentity
    audio.onended = () => {
      if (isCurrentPlayback()) setActivePlayback(null)
    }
    audio.ontimeupdate = () => {
      if (!isCurrentPlayback()) return
      setActiveProgress(Number.isFinite(audio.duration) && audio.duration > 0 ? Math.min(1, audio.currentTime / audio.duration) : 0)
    }
    setActivePlayback(playbackId)
    void audio.play().catch(() => {
      if (isCurrentPlayback()) setActivePlayback(null)
    })
  }, [setActivePlayback])

  const seek = useCallback((playbackId: string, progress: number) => {
    if (activePlaybackIdRef.current !== playbackId) return
    const audio = audioRef.current
    if (!audio || !Number.isFinite(audio.duration) || audio.duration <= 0) return
    const boundedProgress = Math.min(1, Math.max(0, progress))
    audio.currentTime = boundedProgress * audio.duration
    setActiveProgress(boundedProgress)
  }, [])

  useEffect(() => {
    return () => {
      const audio = audioRef.current
      if (!audio) return
      playbackGenerationRef.current += 1
      sourceIdentityRef.current = null
      if (sourceOwnerRef.current !== null) {
        audio.pause()
        audio.currentTime = 0
        audio.onended = null
        audio.ontimeupdate = null
        audio.removeAttribute('src')
        audio.load()
      }
      sourceOwnerRef.current = null
      audioRef.current = null
    }
  }, [])

  return useMemo(
    () => ({ activePlaybackId, activeProgress, pause, play, seek, stop, stopIfOwned }),
    [activePlaybackId, activeProgress, pause, play, seek, stop, stopIfOwned],
  )
}

export function VoicePanel({
  page,
  onReloadFirstPage,
  playbackCoordinator,
}: {
  page: VoicePanelPage
  onReloadFirstPage?: () => void
  playbackCoordinator?: VoicePlaybackCoordinator
}) {
  const localPlaybackCoordinator = useVoicePlaybackCoordinator()
  const playback = playbackCoordinator ?? localPlaybackCoordinator
  const pageIdentity = voicePanelIdentity(page)
  const previousPageIdentityRef = useRef(pageIdentity)
  const initialLines = useRef(mergeLines([], page.lines)).current
  const [lines, setLines] = useState(initialLines)
  const [languageOverrides, setLanguageOverrides] = useState<Record<string, string>>({})
  const [sessionLanguage, setSessionLanguage] = useState(() => sessionLanguagePreferences.get(page.entity_id) || '')
  const [hasMore, setHasMore] = useState(page.has_more)
  const [nextCursor, setNextCursor] = useState(page.next_cursor)
  const [loading, setLoading] = useState(false)
  const [pageError, setPageError] = useState<PageError>(null)
  const loadingRef = useRef(false)
  const requestControllerRef = useRef<AbortController | null>(null)
  const requestGenerationRef = useRef(0)

  const stopAudio = playback.stop

  useEffect(() => {
    if (previousPageIdentityRef.current === pageIdentity) return
    previousPageIdentityRef.current = pageIdentity
    requestGenerationRef.current += 1
    requestControllerRef.current?.abort()
    requestControllerRef.current = null
    loadingRef.current = false
    const nextLines = mergeLines([], page.lines)
    setLines(nextLines)
    setLanguageOverrides({})
    setSessionLanguage(sessionLanguagePreferences.get(page.entity_id) || '')
    setHasMore(page.has_more)
    setNextCursor(page.next_cursor)
    setLoading(false)
    setPageError(null)
  }, [page, pageIdentity])

  useEffect(() => {
    return () => {
      requestGenerationRef.current += 1
      requestControllerRef.current?.abort()
      playback.stopIfOwned(pageIdentity)
    }
  }, [pageIdentity, playback.stopIfOwned])

  const selectLanguage = (lineId: string, language: string) => {
    stopAudio()
    sessionLanguagePreferences.set(page.entity_id, language)
    setSessionLanguage(language)
    setLanguageOverrides((current) => ({ ...current, [lineId]: language }))
  }

  const togglePlayback = (line: VoiceLineGroup, variant: MediaItem) => {
    const playbackId = `${pageIdentity}|${line.voice_line_id}`
    if (playback.activePlaybackId === playbackId) {
      playback.pause(playbackId)
      return
    }
    playback.play(pageIdentity, playbackId, variant.url)
  }

  const loadNextPage = async () => {
    if (loadingRef.current || !nextCursor) return
    stopAudio()
    loadingRef.current = true
    setLoading(true)
    setPageError(null)
    const controller = new AbortController()
    requestControllerRef.current = controller
    const requestGeneration = requestGenerationRef.current + 1
    requestGenerationRef.current = requestGeneration
    try {
      const nextPage = await fetchVoicePage(nextCursor, controller.signal)
      if (requestGenerationRef.current !== requestGeneration) return
      setLines((current) => {
        return mergeLines(current, nextPage.lines)
      })
      setHasMore(nextPage.has_more)
      setNextCursor(nextPage.next_cursor)
    } catch (error) {
      if (requestGenerationRef.current !== requestGeneration) return
      if (error instanceof VoicePageError && error.reloadFirstPage) {
        setPageError('reload-first-page')
      } else if (!(error instanceof DOMException && error.name === 'AbortError')) {
        setPageError('retry')
      }
    } finally {
      if (requestGenerationRef.current !== requestGeneration) return
      requestControllerRef.current = null
      loadingRef.current = false
      setLoading(false)
    }
  }

  if (lines.length === 0) return null
  return (
    <div
      data-testid="voice-panel"
      data-animation-slot="voice-panel"
      data-page-wheel-lock="true"
      className="voice-panel-scroll"
    >
      <AnimatedVoiceList lines={lines} renderLine={(line) => {
        const variantsByLanguage = new Map<string, MediaItem>()
        for (const variant of line.variants) {
          const language = languageKey(variant)
          if (!variantsByLanguage.has(language)) variantsByLanguage.set(language, variant)
        }
        const override = languageOverrides[line.voice_line_id]
        const selectedLanguage = override && variantsByLanguage.has(override)
          ? override
          : sessionLanguage && variantsByLanguage.has(sessionLanguage) ? sessionLanguage : preferredLanguage(line)
        const selectedVariant = variantsByLanguage.get(selectedLanguage) ?? line.variants[0]
        const isPlaying = playback.activePlaybackId === `${pageIdentity}|${line.voice_line_id}`
        return (
          <div
            data-testid="voice-line"
            data-animation-slot="voice-line"
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr) auto',
              alignItems: 'center',
              gap: 8,
              minHeight: 48,
              border: '1px solid var(--border-subtle)',
              borderRadius: 6,
              background: 'rgba(255, 255, 255, 0.06)',
              color: 'var(--text-primary)',
              padding: '6px 8px',
            }}
          >
            <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{line.title || line.voice_line_id}</span>
            <div
              role="group"
              aria-label={`Languages for ${line.title || line.voice_line_id}`}
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                minWidth: 0,
                maxWidth: '100%',
                border: '1px solid var(--border-subtle)',
                borderRadius: 4,
                overflow: 'hidden',
              }}
            >
              {[...variantsByLanguage.keys()].map((language) => {
                const selected = language === selectedLanguage
                return (
                  <button
                    key={language}
                    type="button"
                    aria-label={`Select ${language} for ${line.title || line.voice_line_id}`}
                    aria-pressed={selected}
                    onClick={() => selectLanguage(line.voice_line_id, language)}
                    style={{
                      minWidth: 30,
                      height: 26,
                      border: 0,
                      borderRight: '1px solid var(--border-subtle)',
                      background: selected ? 'var(--accent-gold)' : 'transparent',
                      color: selected ? 'var(--bg-primary)' : 'var(--text-secondary)',
                      padding: '0 5px',
                      cursor: 'pointer',
                    }}
                  >
                    {language}
                  </button>
                )
              })}
            </div>
            <button
              type="button"
              aria-label={`${isPlaying ? 'Pause' : 'Play'} ${line.title || line.voice_line_id}`}
              onClick={() => togglePlayback(line, selectedVariant)}
              style={{
                width: 30,
                height: 30,
                display: 'grid',
                placeItems: 'center',
                border: '1px solid var(--border-subtle)',
                borderRadius: '50%',
                background: 'transparent',
                color: 'var(--text-primary)',
                padding: 0,
                cursor: 'pointer',
              }}
            >
              <span aria-hidden="true">{isPlaying ? '\u23f8' : '\u25b6'}</span>
            </button>
            {isPlaying && (
              <input
                className="voice-progress-seek"
                type="range"
                min={0}
                max={100}
                step={0.1}
                value={playback.activeProgress * 100}
                aria-label={`Playback progress for ${line.title || line.voice_line_id}`}
                onChange={(event) => playback.seek(
                  `${pageIdentity}|${line.voice_line_id}`,
                  Number(event.currentTarget.value) / 100,
                )}
                style={{ '--voice-progress': `${playback.activeProgress * 100}%` } as CSSProperties}
              />
            )}
          </div>
        )
      }} />
      {pageError === 'retry' && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <span role="alert" style={{ color: 'var(--accent-gold)', fontSize: '0.8rem' }}>
            Unable to load more voice lines.
          </span>
          <button type="button" aria-label="Retry loading voice lines" onClick={() => void loadNextPage()}>
            Retry
          </button>
        </div>
      )}
      {pageError === 'reload-first-page' && (
        <button
          type="button"
          aria-label="Reload voice first page"
          title="Reload voice first page"
          disabled={!onReloadFirstPage}
          onClick={onReloadFirstPage}
          style={{ width: 32, height: 32, justifySelf: 'end', padding: 0, cursor: 'pointer' }}
        >
          <span aria-hidden="true">{'\u21bb'}</span>
        </button>
      )}
      {hasMore && pageError === null && (
        <button
          type="button"
          aria-label="Load more voice lines"
          disabled={loading || !nextCursor}
          onClick={() => void loadNextPage()}
          style={{ minHeight: 32, cursor: loading ? 'wait' : 'pointer' }}
        >
          {loading ? 'Loading...' : 'Load more'}
        </button>
      )}
    </div>
  )
}
