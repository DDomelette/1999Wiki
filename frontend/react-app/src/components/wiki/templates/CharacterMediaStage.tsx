import { useEffect, useMemo, useState } from 'react'
import { AudioLines, Box } from 'lucide-react'
import { WikiHeroStage } from '../WikiHeroStage'
import type { WikiMediaViewModel, WikiPortraitSlots } from '../wikiViewModel'
import './CharacterMediaStage.css'

interface CharacterMediaStageProps {
  title: string
  portraitSlots: WikiPortraitSlots
  portraits: readonly WikiMediaViewModel[]
  voices: readonly WikiMediaViewModel[]
}

interface PortraitOption {
  label: string
  media: WikiMediaViewModel
}

export function CharacterMediaStage({ title, portraitSlots, portraits, voices }: CharacterMediaStageProps) {
  const options = useMemo(
    () => buildPortraitOptions(portraitSlots, portraits),
    [portraitSlots, portraits],
  )
  const optionKey = options.map((option) => option.media.id).join('|')
  const [activeIndex, setActiveIndex] = useState(0)
  const [voiceOpen, setVoiceOpen] = useState(false)

  useEffect(() => {
    setActiveIndex(0)
    setVoiceOpen(false)
  }, [optionKey])

  return (
    <section className="character-media" data-testid="character-media-stage">
      <div className="character-media__controls" aria-label="角色媒体切换">
        {options.map((option, index) => (
          <button
            key={option.media.id}
            type="button"
            aria-pressed={activeIndex === index}
            onClick={() => setActiveIndex(index)}
          >
            {option.label}
          </button>
        ))}
        <button
          type="button"
          aria-label="Live2D（未就绪）"
          aria-disabled="true"
          disabled
          className="character-media__live2d"
        >
          <Box aria-hidden="true" />
          <span>Live2D</span>
        </button>
        {voices.length > 0 ? (
          <button
            type="button"
            aria-expanded={voiceOpen}
            onClick={() => setVoiceOpen((current) => !current)}
          >
            <AudioLines aria-hidden="true" />
            <span>语音</span>
          </button>
        ) : null}
      </div>

      <p className="character-media__live2d-status">播放器未就绪</p>

      <WikiHeroStage
        title={title}
        candidates={options.map((option) => option.media)}
        emptyLabel="暂无立绘"
        activeIndex={activeIndex}
        onActiveIndexChange={setActiveIndex}
      />

      {voiceOpen ? (
        <div className="character-media__voices" data-testid="voice-list">
          {voices.map((voice) => (
            <a key={voice.id} href={voice.url}>
              <AudioLines aria-hidden="true" />
              <span>{voice.title || '语音'}</span>
            </a>
          ))}
        </div>
      ) : null}
    </section>
  )
}

function buildPortraitOptions(
  portraitSlots: WikiPortraitSlots,
  portraits: readonly WikiMediaViewModel[],
): PortraitOption[] {
  const options: PortraitOption[] = []
  const seen = new Set<string>()
  const push = (label: string, media: WikiMediaViewModel | null) => {
    if (!media || seen.has(media.id)) return
    seen.add(media.id)
    options.push({ label, media })
  }

  push('初始', portraitSlots.initial)
  push('洞悉', portraitSlots.insight)

  const remaining = [...portraitSlots.extras, ...portraits].filter((media) => !seen.has(media.id))
  remaining.forEach((media, index) => push(`立绘 ${index + 1}`, media))
  return options
}
