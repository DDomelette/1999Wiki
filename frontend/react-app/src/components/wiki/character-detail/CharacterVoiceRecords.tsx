import { Pause, Play } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { CharacterVoiceViewModel } from '../characterDetailViewModel'

export function CharacterVoiceRecords({ voices }: { voices: CharacterVoiceViewModel[] }) {
  const defaults = useMemo(() => Object.fromEntries(voices.map((voice) => [
    voice.id,
    voice.languages.find((item) => item.code === 'zh-CN')?.code ?? voice.languages[0]?.code ?? '',
  ])), [voices])
  const [languageByVoice, setLanguageByVoice] = useState<Record<string, string>>(defaults)
  const [playing, setPlaying] = useState('')

  if (voices.length === 0) return null
  return (
    <section className="character-voice-records" aria-labelledby="voice-records-title">
      <header>
        <p className="character-detail__eyebrow">VOICE_RECORDS</p>
        <h2 id="voice-records-title">语音档案</h2>
      </header>
      <div
        className="character-voice-records__scroll character-detail__nested-scroll native-scrollbar-hidden"
        data-testid="character-voice-scroll"
        tabIndex={0}
      >
        {voices.map((voice) => {
          const selectedCode = languageByVoice[voice.id] || voice.languages[0]?.code
          const selected = voice.languages.find((item) => item.code === selectedCode) ?? voice.languages[0]
          return (
            <article className="character-voice-record" key={voice.id}>
              <div className="character-voice-record__heading">
                <div>
                  <p>LOG / {voice.title}</p>
                  <h3>{voice.title}</h3>
                </div>
                {selected?.audio ? (
                  <button
                    type="button"
                    aria-label={`${playing === voice.id ? '暂停' : '播放'}${voice.title}`}
                    onClick={() => setPlaying((current) => current === voice.id ? '' : voice.id)}
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
                    onClick={() => setLanguageByVoice((current) => ({ ...current, [voice.id]: language.code }))}
                  >
                    {language.label}
                  </button>
                ))}
              </div>
              {selected ? <p className="character-voice-record__text">{selected.text}</p> : null}
              {selected?.audio ? (
                <audio
                  key={selected.audio.id}
                  src={selected.audio.url}
                  preload="none"
                  controls={playing === voice.id}
                />
              ) : null}
            </article>
          )
        })}
      </div>
    </section>
  )
}
