import { useState } from 'react'
import { SEL_CHARACTERS, SEL_SYS_INFO, SEL_BOTTOM_NAV } from '../data/selectionData'
import { pickMedia } from '../media/contract'
import { usePageMedia } from '../media/usePageMedia'

function SelHeader() {
  return (
    <header className="bg-surface/80 backdrop-blur-xl absolute top-0 w-full z-50 border-b border-outline-variant shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] flex items-center justify-between px-margin-mobile h-16">
      <button className="text-primary hover:text-primary-container transition-colors active:scale-95 duration-150 p-2">
        <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>terminal</span>
      </button>
      <h1 className="font-headline-md text-headline-sm md:text-headline-md text-primary tracking-widest uppercase truncate font-bold">REVERSE: 1999</h1>
      <button className="text-primary hover:text-primary-container transition-colors active:scale-95 duration-150 p-2">
        <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>sensors</span>
      </button>
    </header>
  )
}

// 单列堆叠 · 第一块：角色索引 —— 独立上下滚动的小窗，点击卡片即选人
// 媒体全部来自契约层：pickMedia({ role:'thumb', sectionKey:'character-index', variant })
function CharacterList({ selected, onSelect, mediaLinks }) {
  return (
    <section className="w-full shrink-0 bg-surface-container-high/90 backdrop-blur-xl border-b border-outline-variant z-10 flex flex-col relative">
      <div className="p-4 border-b border-outline/30 flex justify-between items-center shrink-0">
        <span className="font-data-label text-data-label text-on-surface-variant">Wiki • 30</span>
        <span className="material-symbols-outlined text-outline text-sm">filter_list</span>
      </div>
      {/* 固定高度的独立滚动窗口：内部上下滑动选人，不影响页面全局滚动 */}
      <div className="h-[36vh] shrink-0 overflow-y-auto no-scrollbar p-4 space-y-6 overscroll-contain">
        {SEL_CHARACTERS.map((char) => {
          const thumb = pickMedia(mediaLinks, { role: 'thumb', sectionKey: 'character-index', variant: char.variant })
          return char.name === selected ? (
            <div key={char.name} onClick={() => onSelect(char.name)} className="relative group cursor-pointer">
              <div className="absolute -top-2 -left-2 w-4 h-4 border-t border-l border-primary transition-transform group-hover:scale-110"></div>
              <div className="border border-primary bg-surface-container/50 p-2 shadow-[2px_2px_0px_0px_rgba(237,105,22,0.5)]">
                <div className="aspect-video bg-surface-container-lowest relative overflow-hidden mb-2 border border-outline/20">
                  {thumb && <img className="w-full h-full object-cover opacity-80 mix-blend-screen" src={thumb.url} alt={thumb.alt} />}
                </div>
                <div className="text-center font-data-label text-data-label text-primary tracking-widest">{char.name}</div>
                <div className="text-center font-data-code text-[10px] text-primary/60 tracking-widest mt-1">{char.latin}</div>
              </div>
            </div>
          ) : (
            <div key={char.name} onClick={() => onSelect(char.name)} className="relative group cursor-pointer opacity-60 hover:opacity-100 transition-opacity">
              <div className="border border-outline/30 bg-surface/30 p-2 hover:border-outline-variant hover:bg-surface-container/30 transition-colors">
                <div className="aspect-video bg-surface-container-lowest relative overflow-hidden mb-2 border border-outline/10 grayscale group-hover:grayscale-0 transition-all">
                  {thumb && <img className="w-full h-full object-cover mix-blend-screen" src={thumb.url} alt={thumb.alt} />}
                </div>
                <div className="text-center font-data-label text-data-label text-on-surface-variant tracking-widest">{char.name}</div>
                <div className="text-center font-data-code text-[10px] text-on-surface-variant/50 tracking-widest mt-1">{char.latin}</div>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

// 单列堆叠 · 第二块：立绘预览舞台（区块高度随立绘宽高比自然撑开，不定死高度）
// 立绘按契约取 role:'standee'；后端未下发该角色的立绘行时，前端渲染"未入库"占位，
// 而不是自己拼路径碰运气 —— 前端对存储拓扑一无所知
function StageArea({ selectedChar, mediaLinks }) {
  const standee = pickMedia(mediaLinks, { role: 'standee', sectionKey: 'stage', variant: selectedChar.variant })
  const backdrop = pickMedia(mediaLinks, { role: 'backdrop', sectionKey: 'stage' })
  return (
    <section className="relative shrink-0 w-full bg-surface-container-lowest overflow-hidden border-b border-outline-variant">
      {backdrop && <div className="absolute inset-0 bg-cover bg-center opacity-40 mix-blend-luminosity" style={{ backgroundImage: `url(${backdrop.url})` }}></div>}
      {standee ? (
        <img alt={standee.alt} className="relative z-10 block w-full h-auto drop-shadow-2xl pointer-events-none transition-transform duration-1000 hover:scale-105 origin-bottom" src={standee.url} />
      ) : (
        <div className="relative z-10 w-full aspect-[3/4] flex flex-col items-center justify-center gap-2 border border-dashed border-outline/40 m-4 mx-auto max-w-[70%]">
          <span className="material-symbols-outlined text-outline text-3xl">hide_image</span>
          <span className="font-data-code text-data-code text-on-surface-variant tracking-widest uppercase">FULL-BODY ASSET PENDING</span>
          <span className="font-data-label text-data-label text-on-surface-variant/70 tracking-widest">{selectedChar.name} · 立绘未入库</span>
        </div>
      )}
      <div className="absolute inset-0 scanline opacity-30 z-20 pointer-events-none"></div>
      <div className="absolute top-8 left-8 z-30 font-data-code text-data-code text-primary/70 tracking-widest flex flex-col gap-1">
        {SEL_SYS_INFO.map((line) => (
          <span key={line.text} className={`uppercase ${line.dim ? 'opacity-50' : ''}`}>{line.text}</span>
        ))}
      </div>
    </section>
  )
}

// 单列堆叠 · 第三块：摘要与行动按钮（从舞台浮层改为独立区块，跟随选中的角色）
function SummaryBar({ selectedChar }) {
  return (
    <section className="w-full p-4 pb-6 flex flex-col gap-3 bg-surface/60">
      <div className="font-data-code text-data-code text-on-surface-variant tracking-widest">
        <span className="text-primary">{selectedChar.name}</span> / {selectedChar.latin} · PLANT (木)
      </div>
      <button className="w-full flex items-center justify-center gap-3 bg-surface/70 backdrop-blur-md border border-primary px-6 py-3 shadow-[4px_4px_0px_0px_rgba(237,105,22,0.3)] hover:bg-primary-container hover:text-on-primary-container transition-all active:translate-y-1 group">
        <span className="material-symbols-outlined group-hover:text-on-primary-container text-primary transition-colors">assignment_ind</span>
        <span className="font-label-caps text-label-caps tracking-widest uppercase">查看完整档案</span>
      </button>
    </section>
  )
}

function BottomNav() {
  return (
    <nav className="bg-surface/90 backdrop-blur-md absolute bottom-0 w-full z-50 border-t border-outline-variant flex justify-around items-center h-20 pb-safe px-4">
      {SEL_BOTTOM_NAV.map((item) => {
        if (item.fab) {
          return (
            <button key={item.label} className="flex flex-col items-center justify-center text-outline p-unit hover:bg-surface-container-high transition-all active:translate-y-0.5 duration-75 w-16 relative">
              <div className="absolute -top-4 w-12 h-12 bg-primary flex items-center justify-center rounded-full shadow-[0_0_15px_rgba(255,182,147,0.4)] border-2 border-surface">
                <span className="material-symbols-outlined text-on-primary">{item.icon}</span>
              </div>
              <span className="font-label-caps text-[10px] tracking-wider mt-6 text-primary">{item.label}</span>
            </button>
          )
        }
        return item.active ? (
          <button key={item.label} className="flex flex-col items-center justify-center bg-secondary-container text-on-secondary-container rounded-lg p-unit shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:bg-surface-container-high transition-all active:translate-y-0.5 duration-75 w-16">
            <span className="material-symbols-outlined mb-1 text-on-secondary-container" style={{ fontVariationSettings: "'FILL' 1" }}>{item.icon}</span>
            <span className="font-label-caps text-[10px] tracking-wider text-on-secondary-container">{item.label}</span>
          </button>
        ) : (
          <button key={item.label} className="flex flex-col items-center justify-center text-outline p-unit hover:bg-surface-container-high transition-all active:translate-y-0.5 duration-75 w-16">
            <span className="material-symbols-outlined mb-1">{item.icon}</span>
            <span className="font-label-caps text-[10px] tracking-wider">{item.label}</span>
          </button>
        )
      })}
    </nav>
  )
}

export default function MobileSelectionPage() {
  const [selected, setSelected] = useState('槲寄生')
  const selectedChar = SEL_CHARACTERS.find((c) => c.name === selected) ?? SEL_CHARACTERS[0]
  // 模拟 GET /api/wiki/pages/wiki/selection → mediaLinks[]（已清洗，仅 14 字段 DTO）
  // 同时上报实时注册表，契约检查器（按 M）可逐条核对本页实际用到的媒体
  const mediaLinks = usePageMedia('selection', 'wiki/selection')
  return (
    <div className="theme-peach device-stage">
      <div className="device-frame">
        <div className="device-frame-label">MOBILE · 390×844 · 单列堆叠</div>
        <div className="bg-background text-on-background h-full w-full overflow-hidden flex flex-col font-caslon noise-bg selection:bg-primary-container selection:text-on-primary-container relative">
          <SelHeader />
          {/* 单列堆叠：索引（小窗自滚） → 预览 → 摘要；下半部分上滑为全局滚动 */}
          <main className="flex-1 mt-16 mb-20 overflow-y-auto no-scrollbar flex flex-col relative">
            <CharacterList selected={selected} onSelect={setSelected} mediaLinks={mediaLinks} />
            <StageArea selectedChar={selectedChar} mediaLinks={mediaLinks} />
            <SummaryBar selectedChar={selectedChar} />
          </main>
          <BottomNav />
        </div>
      </div>
    </div>
  )
}
