import { ROSTER, SIDE_NAV, STATS_BENTO, DOSSIER_DESC, DOSSIER_LORE } from '../data/dossierData'
import { pickMedia } from '../media/contract'
import { usePageMedia } from '../media/usePageMedia'

function DossierHeader() {
  return (
    <header className="fixed top-0 w-full h-16 flex justify-between items-center px-margin-desktop max-w-[1440px] mx-auto z-40 bg-background/80 backdrop-blur-xl border-b border-outline-variant shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] left-1/2 -translate-x-1/2">
      <div className="flex items-center gap-4">
        <span className="material-symbols-outlined text-primary cursor-pointer hover:text-secondary transition-colors">menu</span>
        <span className="font-display-lg text-[24px] uppercase tracking-tighter text-primary">REVERSE: 1999</span>
      </div>
      <div className="flex items-center gap-6">
        <span className="material-symbols-outlined text-on-surface-variant cursor-pointer hover:text-secondary transition-colors">settings</span>
        <span className="material-symbols-outlined text-on-surface-variant cursor-pointer hover:text-secondary transition-colors">terminal</span>
        <span className="material-symbols-outlined text-on-surface-variant cursor-pointer hover:text-secondary transition-colors">timer</span>
      </div>
    </header>
  )
}

function DossierSidebar() {
  return (
    <aside className="fixed left-0 top-16 h-[calc(100vh-64px)] w-64 flex flex-col py-panel-padding gap-gutter bg-surface-container-low/60 backdrop-blur-2xl border-r border-outline-variant z-30 transition-all duration-300 ease-in-out">
      <div className="px-6 mb-4 flex flex-col gap-1">
        <div className="text-primary font-headline-sm text-headline-sm uppercase tracking-wider">STRATEGIST_01</div>
        <div className="text-on-surface-variant font-data-code text-data-code">SESSION_ID: 1999-077</div>
      </div>
      <nav className="flex-1 flex flex-col gap-2 px-2">
        {SIDE_NAV.map((item) => (
          <a key={item.label} href="#" className={`flex items-center gap-4 px-4 py-3 rounded-l transition-colors ${item.active ? 'text-primary font-bold bg-primary-container/20 border-r-2 border-primary' : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-variant/30'}`}>
            <span className="material-symbols-outlined" style={item.active ? { fontVariationSettings: "'FILL' 1" } : undefined}>{item.icon}</span>
            <span className="font-label-caps text-label-caps tracking-widest uppercase">{item.label}</span>
          </a>
        ))}
      </nav>
      <div className="px-4 mt-auto flex flex-col gap-4">
        <div className="flex flex-col gap-2 border-t border-outline-variant pt-4">
          <a className="flex items-center gap-4 px-2 py-2 text-on-surface-variant hover:text-on-surface hover:bg-surface-variant/30 rounded transition-colors" href="#">
            <span className="material-symbols-outlined text-[18px]">history_edu</span>
            <span className="font-label-caps text-label-caps uppercase">Archive</span>
          </a>
          <a className="flex items-center gap-4 px-2 py-2 text-on-surface-variant hover:text-on-surface hover:bg-surface-variant/30 rounded transition-colors" href="#">
            <span className="material-symbols-outlined text-[18px]">database</span>
            <span className="font-label-caps text-label-caps uppercase">Database</span>
          </a>
        </div>
        <button className="w-full py-3 border border-outline text-primary font-label-caps text-label-caps tracking-widest hover:bg-primary-container hover:text-on-primary-container transition-all copper-border">
          DEPLOY UNIT
        </button>
      </div>
    </aside>
  )
}

function RosterList({ mediaLinks }) {
  return (
    <div className="w-32 border-r border-outline-variant glass-panel-dossier h-full overflow-y-auto flex flex-col gap-4 p-4 z-10 shrink-0 dossier-scroll">
      <div className="text-on-surface-variant font-data-code text-data-code mb-2">Wiki • 30</div>
      {ROSTER.map((char) => {
        const thumb = pickMedia(mediaLinks, { role: 'thumb', sectionKey: 'roster', variant: char.variant })
        return char.active ? (
          <div key={char.name} className="relative cursor-pointer border border-primary bg-surface-variant/50 p-2 text-center group">
            <div className="absolute -top-2 -left-2 w-4 h-4 border-t border-l border-primary"></div>
            {thumb && <img className="w-full h-auto object-cover mb-2 opacity-100 mix-blend-luminosity hover:mix-blend-normal transition-all" src={thumb.url} alt={thumb.alt} />}
            <span className="font-label-caps text-label-caps text-primary">{char.name}</span>
          </div>
        ) : (
          <div key={char.name} className="relative cursor-pointer border border-transparent p-2 text-center group opacity-60 hover:opacity-100 transition-opacity">
            {thumb && <img className="w-full h-auto object-cover mb-2 mix-blend-luminosity group-hover:mix-blend-normal transition-all" src={thumb.url} alt={thumb.alt} />}
            <span className="font-label-caps text-label-caps text-on-surface-variant group-hover:text-primary">{char.name}</span>
          </div>
        )
      })}
    </div>
  )
}

function PortraitStage({ mediaLinks }) {
  const portrait = pickMedia(mediaLinks, { role: 'portrait', sectionKey: 'stage', variant: 'druvis' })
  return (
    <div className="flex-1 relative overflow-hidden flex items-center justify-center z-0">
      <div className="absolute top-1/4 right-1/4 w-64 h-32 bg-outline/5 -rotate-12 blur-[2px] font-display-lg text-outline-variant/10 pointer-events-none select-none flex items-center justify-center" style={{ letterSpacing: '0.5em' }}>CONFIDENTIAL</div>
      {portrait && <img alt={portrait.alt} className="h-[90%] w-auto object-contain relative z-10 transition-transform duration-700 ease-out hover:scale-105" src={portrait.url} />}
      <div className="absolute top-[20%] left-[20%] font-data-code text-data-code text-primary/70 tracking-widest z-20">SYS.LOC: FOREST</div>
      <div className="absolute bottom-[20%] right-[30%] font-data-code text-data-code text-primary/70 tracking-widest z-20 flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div> ACTIVE
      </div>
      <div className="absolute top-8 left-8 flex items-center gap-4 z-20">
        <span className="font-label-caps text-label-caps text-on-surface-variant">立绘</span>
        <span className="font-label-caps text-label-caps text-on-surface-variant">Live2D</span>
        <span className="font-label-caps text-label-caps text-on-surface-variant">语音</span>
        <div className="ml-12 flex items-center gap-4 bg-surface-container-highest/50 px-4 py-1 border border-outline-variant">
          <span className="material-symbols-outlined text-primary cursor-pointer hover:text-secondary">chevron_left</span>
          <span className="font-data-code text-data-code text-on-surface">1/15</span>
          <span className="material-symbols-outlined text-primary cursor-pointer hover:text-secondary">chevron_right</span>
        </div>
      </div>
    </div>
  )
}

function DataPanel() {
  return (
    <div className="w-[400px] h-full glass-panel-dossier border-l border-outline-variant shrink-0 p-8 flex flex-col gap-8 overflow-y-auto z-10 shadow-[-10px_0_30px_rgba(0,0,0,0.5)] dossier-scroll">
      <div className="border-b border-outline-variant pb-4 relative">
        <div className="absolute -top-4 -right-4 bg-outline-variant px-2 py-1 text-on-surface font-data-code text-[10px] transform rotate-45 shadow-md">ARCHIVE</div>
        <div className="text-on-surface-variant font-label-caps text-label-caps mb-2 tracking-widest">角色资料</div>
        <h1 className="font-headline-md text-[42px] text-primary mb-1">槲寄生</h1>
        <div className="font-data-code text-data-code text-secondary mb-4">Data:Char/3003.json</div>
        <h2 className="font-headline-sm text-headline-sm text-on-surface">Druvis III Character Dossier</h2>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {STATS_BENTO.map((s) => (
          <div key={s.label} className="border border-outline-variant p-3 bg-surface-dim/40 flex justify-between items-center group hover:border-primary transition-colors">
            <span className="font-data-label text-data-label text-on-surface-variant">{s.label}</span>
            <span className="font-data-code text-data-code text-primary group-hover:text-secondary text-lg">{s.value}</span>
          </div>
        ))}
      </div>
      <div className="text-body-md text-on-surface-variant leading-relaxed font-caslon">
        {DOSSIER_DESC}
      </div>
      <div className="text-data-code font-data-code text-outline-variant leading-relaxed border-l-2 border-outline-variant pl-4 opacity-80">
        1900榛木铃<br />
        由Lugus为爱尔兰隐修院附<br />
        属孤儿院定制的1900百年纪念款，隶属Samildánach真理珠宝系列，同时也是她身上唯一的真理珠宝作品。珠宝鉴定证书颁发于1911年10月，在<br />
        一场母爱与女儿举办的生日宴上。
      </div>
      <div className="mt-4 flex flex-col gap-3">
        <h3 className="font-label-caps text-label-caps text-on-surface tracking-widest uppercase mb-2 border-b border-outline pb-1">个人详情</h3>
        <div className="p-6 border border-primary bg-primary-container/10 flex flex-col items-center gap-4 group cursor-pointer hover:bg-primary-container/20 transition-all copper-border">
          <span className="material-symbols-outlined text-primary text-[32px]">person_search</span>
          <div className="text-center">
            <div className="font-headline-sm text-primary uppercase tracking-widest">查看完整档案</div>
            <div className="font-data-code text-data-code text-on-surface-variant mt-1">ACCESS FULL DOSSIER</div>
          </div>
          <button className="mt-2 px-8 py-2 bg-primary text-on-primary font-label-caps text-label-caps tracking-widest hover:bg-secondary transition-colors">INITIALIZE</button>
        </div>
      </div>
    </div>
  )
}

export default function ArchivalDossierPage() {
  // GET /api/wiki/pages/wiki/dossier → mediaLinks[]（契约检查器按 M 可见）
  const mediaLinks = usePageMedia('dossier', 'wiki/dossier')
  const backdrop = pickMedia(mediaLinks, { role: 'backdrop', sectionKey: 'main' })
  return (
    <div className="theme-peach dossier-bg text-on-surface font-caslon h-screen w-screen overflow-hidden flex bg-background selection:bg-primary-container selection:text-on-primary-container relative">
      <div className="absolute inset-0 scanline-peach z-50 mix-blend-overlay"></div>
      <DossierHeader />
      <DossierSidebar />
      <main
        className="ml-64 mt-16 flex-1 h-[calc(100vh-64px)] relative flex bg-cover bg-center"
        style={backdrop ? { backgroundImage: `url(${backdrop.url})` } : undefined}
      >
        <RosterList mediaLinks={mediaLinks} />
        <PortraitStage mediaLinks={mediaLinks} />
        <DataPanel />
      </main>
    </div>
  )
}
