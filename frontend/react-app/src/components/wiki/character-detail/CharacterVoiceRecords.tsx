import { ChevronDown, ChevronUp, Pause, Play } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { CharacterVoiceViewModel } from '../characterDetailViewModel'

const VOICE_PAGE_SIZE = 5

export function CharacterVoiceRecords({
  voices,
  initialVisibleCount,
}: {
  voices: CharacterVoiceViewModel[]
  initialVisibleCount?: number
}) {
  const defaults = useMemo(() => Object.fromEntries(voices.map((voice) => [
    voice.id,
    voice.languages.find((item) => item.code === 'zh-CN')?.code ?? voice.languages[0]?.code ?? '',
  ])), [voices])
  const [languageByVoice, setLanguageByVoice] = useState<Record<string, string>>(defaults)
  const [activeVoice, setActiveVoice] = useState('')
  const [playing, setPlaying] = useState('')
  const [visibleCount, setVisibleCount] = useState(initialVisibleCount ?? voices.length)
  const audioRefs = useRef<Record<string, HTMLAudioElement | null>>({})
  const recordRefs = useRef<Record<string, HTMLElement | null>>({})
  const canCollapse = initialVisibleCount !== undefined && voices.length > initialVisibleCount
  const allVisible = visibleCount >= voices.length
  const visibleVoices = voices.slice(0, visibleCount)

  useEffect(() => () => {
    Object.values(audioRefs.current).forEach((audio) => audio?.pause())
  }, [])

  useEffect(() => {
    const record = recordRefs.current[activeVoice]
    if (!activeVoice || !record || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) return
      audioRefs.current[activeVoice]?.pause()
      setActiveVoice((current) => current === activeVoice ? '' : current)
      setPlaying((current) => current === activeVoice ? '' : current)
    })
    observer.observe(record)
    return () => observer.disconnect()
  }, [activeVoice])

  const togglePlayback = (voiceId: string) => {
    const audio = audioRefs.current[voiceId]
    if (!audio) return
    if (playing === voiceId) {
      audio.pause()
      setPlaying('')
      return
    }
    if (activeVoice && activeVoice !== voiceId) audioRefs.current[activeVoice]?.pause()
    audio.currentTime = 0
    setActiveVoice(voiceId)
    setPlaying(voiceId)
    void audio.play().catch(() => {
      setActiveVoice((current) => current === voiceId ? '' : current)
      setPlaying((current) => current === voiceId ? '' : current)
    })
  }

  const selectLanguage = (voiceId: string, code: string) => {
    audioRefs.current[voiceId]?.pause()
    setActiveVoice((current) => current === voiceId ? '' : current)
    setPlaying((current) => current === voiceId ? '' : current)
    setLanguageByVoice((current) => ({ ...current, [voiceId]: code }))
  }

  const toggleVisibleVoices = () => {
    if (allVisible) {
      if (activeVoice) audioRefs.current[activeVoice]?.pause()
      setActiveVoice('')
      setPlaying('')
      setVisibleCount(initialVisibleCount ?? voices.length)
      return
    }
    setVisibleCount((current) => Math.min(current + VOICE_PAGE_SIZE, voices.length))
  }

  if (voices.length === 0) return null
  return (
    <section className="character-voice-records" aria-labelledby="voice-records-title">
      <header>
        <p className="character-detail__eyebrow">VOICE_RECORDS</p>
        <h2 id="voice-records-title">语音档案</h2>
      </header>
      <div
        id="character-voice-list"
        className="character-voice-records__scroll character-detail__nested-scroll native-scrollbar-hidden"
        data-testid="character-voice-scroll"
        tabIndex={0}
      >
        {visibleVoices.map((voice) => {
          const selectedCode = languageByVoice[voice.id] || voice.languages[0]?.code
          const selected = voice.languages.find((item) => item.code === selectedCode) ?? voice.languages[0]
          return (
            <article
              className="character-voice-record"
              key={voice.id}
              ref={(node) => { recordRefs.current[voice.id] = node }}
            >
              <div className="character-voice-record__heading">
                <div>
                  <p>LOG / {voice.title}</p>
                  <h3>{voice.title}</h3>
                </div>
                {selected?.audio ? (
                  <button
                    type="button"
                    aria-label={`${playing === voice.id ? '暂停' : '播放'}${voice.title}`}
                    onClick={() => togglePlayback(voice.id)}
                  >
                    {playing === voice.id ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
                  </button>
                ) : null}
              </div>
              <div className="character-voice-record__languages" role="group" aria-label={`${voice.title}语言`}>
                {voice.languages.map((language) => (
                  <button
                    key={language.code}
                    type="button"
                    aria-pressed={language.code === selected?.code}
                    onClick={() => selectLanguage(voice.id, language.code)}
                  >
                    {language.label}
                  </button>
                ))}
              </div>
              {selected ? <p className="character-voice-record__text">{selected.text}</p> : null}
              {selected?.audio ? (
                <audio
                  key={selected.audio.id}
                  ref={(node) => { audioRefs.current[voice.id] = node }}
                  src={selected.audio.url}
                  preload="none"
                  controls={activeVoice === voice.id}
                  onPlay={() => setPlaying(voice.id)}
                  onPause={() => setPlaying((current) => current === voice.id ? '' : current)}
                  onEnded={() => setPlaying((current) => current === voice.id ? '' : current)}
                  onError={() => {
                    setActiveVoice((current) => current === voice.id ? '' : current)
                    setPlaying((current) => current === voice.id ? '' : current)
                  }}
                />
              ) : null}
            </article>
          )
        })}
      </div>
      {canCollapse ? (
        <button
          type="button"
          className="character-voice-records__toggle"
          aria-expanded={visibleCount > (initialVisibleCount ?? voices.length)}
          aria-controls="character-voice-list"
          onClick={toggleVisibleVoices}
        >
          {allVisible ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
          <span>{allVisible ? '收起语音' : '查看更多'}</span>
        </button>
      ) : null}
    </section>
  )
}
