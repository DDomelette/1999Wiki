import { INHERITANCE_LEVELS, SHAPING_LEVELS, VOICE_RECORDS } from '../data/druvis'

function InheritancePanel() {
  return (
    <div className="glass-panel p-5 rotate-1">
      <h3 className="font-headline-md text-lg text-primary border-b border-outline/30 pb-2 mb-3 flex items-center gap-2">
        <span className="material-symbols-outlined text-base">eco</span>
        传承: 木秀于林
      </h3>
      <div className="space-y-4">
        {INHERITANCE_LEVELS.map((item) => (
          <div key={item.level} className={`flex gap-3 ${item.active ? '' : 'opacity-60'}`}>
            <div className={`w-8 h-8 rounded-full bg-surface-container flex items-center justify-center shrink-0 font-data-mono text-xs border ${item.active ? 'border-primary/50 text-primary' : 'border-outline/50'}`}>
              {item.level}
            </div>
            <div className="text-[11px] font-body-md text-on-surface/80 leading-snug pt-1">
              {item.parts.map((p, i) => (
                <span key={i} className={`${p.accent ? 'text-primary' : ''} ${p.bold ? 'font-bold' : ''}`}>{p.text}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ShapingPanel() {
  return (
    <div className="glass-panel p-4 -rotate-1">
      <h3 className="font-headline-md text-lg text-primary border-b border-outline/30 pb-2 mb-3 flex items-center gap-2">
        <span className="material-symbols-outlined text-base">architecture</span>
        塑造
      </h3>
      <div className="space-y-2 h-[100px] overflow-y-auto pr-2 thin-scroll">
        {SHAPING_LEVELS.map((s) => (
          <div key={s.lv} className="text-[10px] font-body-md text-on-surface/80 border-l-2 border-outline/30 pl-2">
            <span className="text-primary font-bold">{s.lv}</span> {s.text}
          </div>
        ))}
      </div>
    </div>
  )
}

function VoiceRecords() {
  return (
    <div className="glass-panel p-5 flex-1 flex flex-col min-h-0 relative">
      <div className="absolute top-4 right-4 text-outline/20">
        <span className="material-symbols-outlined text-4xl">mic_external_on</span>
      </div>
      <h3 className="font-headline-md text-lg text-primary border-b border-outline/30 pb-2 mb-3 shrink-0">VOICE_RECORDS // 语音档案</h3>
      <div className="overflow-y-auto flex-1 pr-2 space-y-4 font-body-md text-xs text-on-surface/80 thin-scroll">
        {VOICE_RECORDS.map((v, i) => (
          <div key={v.title} className={`border-l-2 pl-3 ${i === 0 ? 'border-primary/50' : 'border-outline/30'}`}>
            <div className="flex justify-between items-center mb-1">
              <div className="font-data-mono text-[9px] text-primary uppercase">{v.title}</div>
              <span className={`material-symbols-outlined text-[10px] ${i === 0 ? 'text-primary' : 'text-outline/50'}`}>play_arrow</span>
            </div>
            <p className="mb-1">{v.zh}</p>
            <p className="text-[9px] text-outline/60 italic leading-tight">{v.en}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function RightColumn() {
  return (
    <div className="absolute right-10 top-24 w-[380px] z-20 space-y-6 flex flex-col h-[calc(100vh-140px)]">
      <InheritancePanel />
      <ShapingPanel />
      <VoiceRecords />
    </div>
  )
}
