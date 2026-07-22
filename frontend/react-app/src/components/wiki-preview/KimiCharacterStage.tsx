import { Box, ImageOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { KimiWikiDetailViewModel } from './kimiWikiPreviewViewModel'

export function KimiCharacterStage({
  model,
  mode,
}: {
  model: KimiWikiDetailViewModel
  mode: 'desktop' | 'mobile'
}) {
  const { character } = model
  const firstId = character.portraitStates[0]?.id ?? ''
  const [activeId, setActiveId] = useState(firstId)
  const [failedIds, setFailedIds] = useState<Set<string>>(() => new Set())

  useEffect(() => {
    setActiveId(firstId)
    setFailedIds(new Set())
  }, [character.identity.pageId, firstId])

  const active = character.portraitStates.find((item) => item.id === activeId)
    ?? character.portraitStates[0]
  const activeFailed = active ? failedIds.has(active.id) : false
  const activeBackdrop = active?.backdrop ?? model.backdrop
  const backdropStyle = activeBackdrop
    ? { backgroundImage: `url("${activeBackdrop.url}")` }
    : undefined

  return (
    <section
      className={`kimi-character-stage kimi-character-stage--${mode}`}
      data-testid="kimi-character-stage"
      style={backdropStyle}
    >
      <span className="kimi-character-stage__shade" aria-hidden="true" />
      <span className="kimi-character-stage__ribbon">SOPHISTICATED</span>
      <span className="kimi-character-stage__status" aria-hidden="true">
        SYS.LOC: {character.location || 'UNKNOWN'} / STATUS: ACTIVE
      </span>

      <div className="kimi-character-stage__portraits">
        {character.portraitStates.map((state) => {
          const selected = state.id === active?.id
          const failed = failedIds.has(state.id)
          return (
            <img
              key={state.id}
              src={(state.portraitMedia ?? state.live2dMedia)?.url}
              alt={selected ? `${character.identity.name} - ${state.label}` : ''}
              aria-hidden={selected ? 'false' : 'true'}
              className={`${selected ? 'is-active' : 'is-inactive'}${failed ? ' is-failed' : ''}`}
              data-testid="kimi-character-portrait"
              onError={() => setFailedIds((current) => new Set(current).add(state.id))}
            />
          )
        })}
        {character.portraitStates.length === 0 || activeFailed ? (
          <div
            className="kimi-character-stage__fallback"
            aria-label={activeFailed ? '当前立绘加载失败' : '暂无可用立绘'}
          >
            <ImageOff aria-hidden="true" />
            <span>{activeFailed ? 'PORTRAIT LOAD FAILED' : 'MEDIA UNAVAILABLE'}</span>
          </div>
        ) : null}
      </div>

      <div className="kimi-character-stage__identity">
        <p>SUBJECT_EXONYM</p>
        <strong>{character.identity.exonym || character.identity.name}</strong>
        {character.identity.exonym ? <span>{character.identity.name}</span> : null}
      </div>

      <div className="kimi-character-stage__wardrobe">
        <p>SKIN_SELECT</p>
        <div role="group" aria-label="角色立绘">
          {character.portraitStates.map((state) => (
            <button
              key={state.id}
              type="button"
              aria-label={`切换到${state.label}`}
              aria-pressed={state.id === active?.id}
              onClick={() => setActiveId(state.id)}
            >
              {state.variant === 'initial' ? 'INIT' : state.variant === 'insight' ? 'INSIGHT' : state.label}
            </button>
          ))}
        </div>
        <span>{active?.variant === 'insight' ? 'INSIGHT_V2' : 'INIT_V1'}</span>
        {!character.live2dAvailable ? (
          <button type="button" disabled aria-label="Live2D 播放器未就绪">
            <Box aria-hidden="true" /> LIVE2D OFFLINE
          </button>
        ) : null}
      </div>

      {active?.description ? (
        <p className="kimi-character-stage__caption">{active.description}</p>
      ) : null}
    </section>
  )
}
