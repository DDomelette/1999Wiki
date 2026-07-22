import { Box, Image as ImageIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { CharacterDetailViewModel, CharacterPortraitStateViewModel } from '../characterDetailViewModel'

export interface CharacterPortraitStageProps {
  viewModel: CharacterDetailViewModel
  mode: 'desktop' | 'mobile'
}

type PortraitMode = 'live2d' | 'portrait'

function resolveEffectiveMode(state: CharacterPortraitStateViewModel | undefined, preference: PortraitMode): PortraitMode {
  if (!state) return preference
  if (preference === 'live2d' && state.live2dMedia) return 'live2d'
  if (preference === 'portrait' && state.portraitMedia) return 'portrait'
  if (state.live2dMedia) return 'live2d'
  if (state.portraitMedia) return 'portrait'
  return preference
}

function resolveModeMedia(state: CharacterPortraitStateViewModel, mode: PortraitMode) {
  if (mode === 'live2d') return state.live2dMedia ?? state.portraitMedia
  return state.portraitMedia ?? state.live2dMedia
}

export function CharacterPortraitStage({ viewModel, mode }: CharacterPortraitStageProps) {
  const firstState = viewModel.portraitStates[0]?.id ?? ''
  const [activeId, setActiveId] = useState(firstState)
  const [portraitMode, setPortraitMode] = useState<PortraitMode>('live2d')

  useEffect(() => {
    setActiveId(firstState)
  }, [firstState, viewModel.identity.pageId])

  const active = viewModel.portraitStates.find((item) => item.id === activeId)
    ?? viewModel.portraitStates[0]
  const effectiveMode = resolveEffectiveMode(active, portraitMode)
  const activeMedia = active ? resolveModeMedia(active, effectiveMode) : null
  const udimo = viewModel.profileRows.find((item) => item.key.toLowerCase() === 'udimo')
  const backdropStyle = active?.backdrop
    ? { backgroundImage: `url("${active.backdrop.url}")` }
    : undefined

  return (
    <section
      className={`character-portrait-stage character-portrait-stage--${mode}`}
      data-testid="character-portrait-stage"
      style={backdropStyle}
    >
      <span className="character-portrait-stage__watermark" aria-hidden="true">
        {viewModel.identity.exonym || viewModel.identity.name}
      </span>
      <span className="character-portrait-stage__ribbon">SOPHISTICATED</span>
      <div className="character-portrait-stage__images">
        {viewModel.portraitStates.map((state) => {
          const selected = state.id === active?.id
          const media = resolveModeMedia(state, effectiveMode)
          return (
            <img
              key={state.id}
              src={media?.url}
              alt={selected ? `${viewModel.identity.name} - ${state.label}` : ''}
              aria-hidden={selected ? 'false' : 'true'}
              data-testid="character-portrait-image"
              data-portrait-mode={effectiveMode}
              className={selected ? 'is-active' : 'is-inactive'}
            />
          )
        })}
        {(!activeMedia || viewModel.portraitStates.length === 0) ? (
          <div className="character-portrait-stage__fallback" aria-label="暂无可用立绘">
            <ImageIcon aria-hidden="true" />
          </div>
        ) : null}
      </div>
      <div className="character-portrait-stage__identity">
        <p>SUBJECT_EXONYM</p>
        <strong>{viewModel.identity.exonym || viewModel.identity.name}</strong>
        {viewModel.identity.exonym ? <span>{viewModel.identity.name}</span> : null}
      </div>
      <div className="character-portrait-stage__wardrobe" aria-label="立绘切换">
        <p>MODE_SELECT</p>
        <div role="group" aria-label="舞台模式">
          <button
            type="button"
            aria-label="切换到Live2D"
            aria-pressed={effectiveMode === 'live2d'}
            disabled={!active?.live2dMedia}
            onClick={() => setPortraitMode('live2d')}
          >
            LIVE2D
          </button>
          <button
            type="button"
            aria-label="切换到立绘"
            aria-pressed={effectiveMode === 'portrait'}
            disabled={!active?.portraitMedia}
            onClick={() => setPortraitMode('portrait')}
          >
            立绘
          </button>
        </div>
        <p>SKIN_SELECT</p>
        <div role="group" aria-label="角色立绘">
          {viewModel.portraitStates.map((state) => (
            <button
              key={state.id}
              type="button"
              aria-label={`切换到${state.label}`}
              aria-pressed={state.id === active?.id}
              onClick={() => setActiveId(state.id)}
            >
              {state.label}
            </button>
          ))}
        </div>
        <span>{active?.variant === 'insight' ? 'INSIGHT_V2' : active?.variant === 'initial' ? 'INIT_V1' : active?.label}</span>
        {!viewModel.live2dAvailable ? (
          <span className="character-portrait-stage__live2d-unavailable" title="Live2D 播放器未就绪">
            <Box aria-hidden="true" /> LIVE2D OFFLINE
          </span>
        ) : null}
      </div>
      {mode === 'desktop' && udimo ? (
        <aside className="character-portrait-stage__udimo">
          {viewModel.udimoMedia ? (
            <img
              src={viewModel.udimoMedia.url}
              alt=""
              data-testid="character-portrait-udimo-image"
            />
          ) : null}
          <div>
            <span>UDIMO</span>
            <strong>{udimo.value}</strong>
          </div>
        </aside>
      ) : null}
      {mode === 'desktop' ? <a className="character-portrait-stage__deploy" href="#combat">DEPLOY UNIT</a> : null}
      {active?.description ? <p className="character-portrait-stage__caption">{active.description}</p> : null}
    </section>
  )
}
