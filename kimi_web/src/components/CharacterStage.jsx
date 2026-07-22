import { pickMedia } from '../media/contract'

// 立绘舞台：初始/洞悉两张立绘按契约 role:'standee' + variant 取图
export default function CharacterStage({ skin, mediaLinks }) {
  const initial = pickMedia(mediaLinks, { role: 'standee', sectionKey: 'stage', variant: 'initial' })
  const insight = pickMedia(mediaLinks, { role: 'standee', sectionKey: 'stage', variant: 'insight' })
  return (
    <div className="absolute inset-0 flex justify-center items-end pb-0 z-10 pointer-events-none">
      <div className="relative w-full max-w-[1400px] h-full char-img-container flex justify-center items-end">
        {initial && (
          <img
            alt={initial.alt}
            className={`h-[95vh] object-contain object-bottom drop-shadow-[0_0_50px_rgba(0,0,0,0.8)] transition-opacity duration-700 ${skin === 'initial' ? 'opacity-100' : 'opacity-0'}`}
            src={initial.url}
          />
        )}
        {insight && (
          <img
            alt={insight.alt}
            className={`absolute bottom-0 h-[95vh] object-contain object-bottom drop-shadow-[0_0_50px_rgba(0,0,0,0.8)] transition-opacity duration-700 ${skin === 'insight' ? 'opacity-100' : 'opacity-0'}`}
            src={insight.url}
          />
        )}
      </div>
      {/* Giant Vertical Name Overlay */}
      <div className="absolute left-[20%] top-1/4 -translate-y-1/2 vertical-text font-display-lg text-[120px] text-primary/10 select-none tracking-tighter leading-none z-0">
        DRUVIS III
      </div>
    </div>
  )
}
