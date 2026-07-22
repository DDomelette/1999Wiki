import { pickMedia } from '../media/contract'

function UdimoChip({ mediaLinks }) {
  // UDIMO 小图复用舞台"初始立绘"同一份对象（灰度裁剪显示）
  const thumb = pickMedia(mediaLinks, { role: 'standee', sectionKey: 'stage', variant: 'initial' })
  return (
    <div className="glass-panel-light p-2 flex items-center gap-3 absolute -top-16 -left-32 rotate-6 shadow-hard w-48 pointer-events-auto">
      <div className="w-10 h-10 bg-black overflow-hidden border border-outline/20">
        {thumb && <img alt={thumb.alt} className="w-full h-full object-cover grayscale brightness-50 contrast-150" src={thumb.url} />}
      </div>
      <div>
        <div className="font-data-mono text-[9px] text-primary">UDIMO</div>
        <div className="font-body-md text-[10px] text-on-surface">猫类 (Cat)</div>
      </div>
    </div>
  )
}

function SkinButton({ active, onClick, children }) {
  const activeCls = 'bg-primary text-surface border-primary shadow-hard'
  const idleCls = 'text-outline hover:text-primary border-outline/30 hover:border-primary/50'
  return (
    <button
      className={`relative px-6 py-2 font-data-mono text-xs tracking-widest transition-all border group ${active ? activeCls : idleCls}`}
      onClick={onClick}
    >
      {children}
      <span className={`absolute -bottom-1 left-0 w-full h-1 bg-primary ${active ? 'animate-pulse' : 'opacity-0'}`}></span>
    </button>
  )
}

export default function BottomControls({ skin, onSkinChange, mediaLinks }) {
  return (
    <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-30 flex flex-col items-center gap-4">
      <UdimoChip mediaLinks={mediaLinks} />
      {/* Skin Toggle */}
      <div className="glass-panel p-4 flex flex-col gap-3 pointer-events-auto shadow-hard border-primary/40">
        <div className="flex items-center gap-2 border-b border-outline/30 pb-2 mb-1">
          <span className="material-symbols-outlined text-sm text-primary">apparel</span>
          <span className="font-data-mono text-[10px] tracking-widest text-primary uppercase">WARDROBE / 衣着分卷</span>
        </div>
        <div className="flex gap-2">
          <SkinButton active={skin === 'initial'} onClick={() => onSkinChange('initial')}>INITIAL</SkinButton>
          <SkinButton active={skin === 'insight'} onClick={() => onSkinChange('insight')}>INSIGHT</SkinButton>
        </div>
      </div>
      <button className="font-data-mono text-xs tracking-[0.2em] text-primary hover:text-white border border-primary/50 hover:bg-primary px-8 py-2 transition-all bg-surface/80 backdrop-blur pointer-events-auto flex items-center gap-2">
        <span className="material-symbols-outlined text-sm">bolt</span>
        DEPLOY UNIT
      </button>
    </div>
  )
}
