import { useState } from 'react'
import {
  COMP_LORE_FIELDS, COMP_SCENTS, COMP_INHERITANCE,
  COMP_SKILLS, COMP_VOICES, COMP_CULTURE, COMP_DIALOGUE, COMP_COLLECTION,
} from '../data/comprehensiveData'
import { pickMedia } from '../media/contract'
import { usePageMedia } from '../media/usePageMedia'

function TopNav() {
  return (
    <nav className="fixed top-0 left-0 w-full z-50 flex justify-between items-center px-4 py-2 h-14 bg-surface-container-lowest border-b border-outline-variant shadow-xl">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-surface-variant border border-outline/40 flex items-center justify-center rounded">
          <span className="material-symbols-outlined text-outline text-xl">menu</span>
        </div>
        <div className="flex flex-col">
          <span className="font-data-mono text-[10px] tracking-[0.2em] font-bold text-on-surface opacity-80 leading-tight">R1999 //</span>
          <span className="font-data-mono text-[10px] tracking-[0.2em] font-bold text-on-surface opacity-80 leading-tight">LONDON_CHRONOGRAPH</span>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="bg-black/60 px-3 py-1 border border-outline-variant/50 rounded-full flex items-center gap-2">
          <div className="w-2 h-2 bg-primary rounded-full animate-pulse shadow-[0_0_8px_rgba(255,182,147,0.6)]"></div>
          <span className="font-data-mono text-[9px] text-primary tracking-wider">LIVE_ARCHIVE</span>
        </div>
      </div>
    </nav>
  )
}

function SectionDivider({ icon, title, align = 'left' }) {
  return (
    <div className={`flex items-center gap-4 mb-4 ${align === 'left' ? 'ml-4' : 'mr-4'}`}>
      {align === 'left' && <div className="h-px bg-outline-variant flex-1"></div>}
      {align === 'right' && <div className="h-px bg-outline-variant w-8"></div>}
      {icon && <span className="material-symbols-outlined text-outline text-sm">{icon}</span>}
      <h3 className="font-data-mono text-[10px] tracking-[0.3em] text-outline uppercase">{title}</h3>
      {align === 'left' && <div className="h-px bg-outline-variant w-8"></div>}
      {align === 'right' && <div className="h-px bg-outline-variant flex-1"></div>}
    </div>
  )
}

function HeroSection({ skin, onSkinChange, mediaLinks }) {
  const heroInitial = pickMedia(mediaLinks, { role: 'hero', sectionKey: 'hero', variant: 'initial' })
  const heroInsight = pickMedia(mediaLinks, { role: 'hero', sectionKey: 'hero', variant: 'insight' })
  return (
    <section className="relative mt-4 mb-12">
      <div className="absolute -left-2 top-10 flex flex-col items-center gap-3 opacity-60 z-20">
        <span className="floating-label font-data-mono text-[9px] tracking-[0.3em] text-outline">ARCANIST_03</span>
        <div className="w-px h-32 bg-outline-variant"></div>
      </div>
      <div className="relative w-full h-[600px] copper-border bg-black hard-shadow overflow-hidden group">
        <div className="absolute top-0 right-0 p-3 z-20 mix-blend-overlay opacity-30">
          <span className="material-symbols-outlined text-6xl">psychology</span>
        </div>
        {heroInitial && <img alt={heroInitial.alt} className={`portrait-transition absolute inset-0 w-full h-full object-cover object-top opacity-80 group-hover:scale-105 transition-transform duration-1000 ${skin === 'initial' ? 'active-portrait' : 'hidden-portrait'}`} src={heroInitial.url} />}
        {heroInsight && <img alt={heroInsight.alt} className={`portrait-transition absolute inset-0 w-full h-full object-cover object-top opacity-80 group-hover:scale-105 transition-transform duration-1000 ${skin === 'insight' ? 'active-portrait' : 'hidden-portrait'}`} src={heroInsight.url} />}
        {/* Mechanical Toggle */}
        <div className="absolute bottom-6 right-6 z-30 flex flex-col items-end gap-2">
          <div className="glass-panel-comp border border-primary/30 p-2 hard-shadow flex flex-col gap-2">
            <div className="flex items-center gap-2 px-1 mb-1">
              <span className="w-1 h-1 bg-primary rounded-full animate-pulse"></span>
              <span className="font-data-mono text-[8px] text-primary tracking-[0.2em] uppercase">Skin_Select</span>
            </div>
            <div className="flex gap-2">
              <button
                className={`tactile-btn px-3 py-1 text-[10px] font-data-mono ${skin === 'initial' ? 'text-primary border-primary/50 bg-primary/10' : 'text-outline opacity-60'}`}
                onClick={() => onSkinChange('initial')}
              >INIT</button>
              <button
                className={`tactile-btn px-3 py-1 text-[10px] font-data-mono ${skin === 'insight' ? 'text-primary border-primary/50 bg-primary/10' : 'text-outline opacity-60'}`}
                onClick={() => onSkinChange('insight')}
              >INSIGHT</button>
            </div>
          </div>
          <div className="bg-surface-container-highest px-2 py-0.5 border border-outline/50 text-[9px] font-data-mono text-outline">
            <span>{skin === 'initial' ? 'INIT_V1' : 'INSIGHT_V2'}</span>
          </div>
        </div>
        {/* Diagonal Tape Label */}
        <div className="absolute top-8 -left-8 bg-primary-container px-12 py-1.5 rotate-[-45deg] text-[10px] font-bold tracking-[0.4em] text-on-primary-container shadow-lg z-30">
          SOPHISTICATED
        </div>
        {/* Info Overlay Card */}
        <div className="absolute bottom-6 left-[-16px] glass-panel-comp p-5 copper-border hard-shadow w-[260px] z-30">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 bg-primary rounded-full"></div>
            <span className="font-data-mono text-[9px] text-primary tracking-widest">SUBJECT_EXONYM</span>
          </div>
          <h1 className="font-display-lg text-5xl text-on-background mb-1">Druvis III</h1>
          <p className="font-headline-md text-xl text-outline mb-4">槲寄生</p>
          <div className="flex gap-2">
            <span className="border border-primary text-primary px-2 py-0.5 text-[9px] font-data-mono font-bold uppercase">PLANT</span>
            <span className="bg-surface-variant text-on-surface-variant px-2 py-0.5 text-[9px] font-data-mono font-bold uppercase">6_STAR</span>
          </div>
        </div>
      </div>
    </section>
  )
}

function StatsGrid() {
  return (
    <section className="grid grid-cols-2 gap-x-4 gap-y-6 relative z-20">
      <div className="glass-panel-comp p-4 copper-border hard-shadow rotate-[-2deg] relative">
        <div className="pin-tape"></div>
        <div className="text-[9px] font-data-mono text-outline mb-1 uppercase tracking-widest">Damage_Type</div>
        <div className="text-3xl font-headline-md text-on-surface mb-1">Mental</div>
        <div className="text-[11px] text-outline font-data-mono">精神创伤</div>
        <span className="material-symbols-outlined absolute bottom-3 right-3 text-3xl opacity-20 text-outline">psychology</span>
      </div>
      <div className="bg-primary-container/20 backdrop-blur-[12px] p-4 border border-primary/50 hard-shadow rotate-[1deg] relative">
        <div className="pin-tape"></div>
        <div className="text-[9px] font-data-mono text-primary mb-1 uppercase tracking-widest">Inspiration</div>
        <div className="text-3xl font-headline-md text-primary mb-1">Plant</div>
        <div className="text-[11px] text-primary/70 font-data-mono">林间的渴慕[木]</div>
        <span className="material-symbols-outlined absolute bottom-3 right-3 text-3xl opacity-20 text-primary">eco</span>
      </div>
      <div className="col-span-2 glass-panel-comp p-4 copper-border hard-shadow flex items-center justify-between mt-2">
        <div className="flex flex-col gap-1">
          <span className="text-[9px] font-data-mono text-outline tracking-widest">LOCATION_TRACE</span>
          <span className="font-data-mono text-sm text-on-surface">Washington / Europe</span>
        </div>
        <div className="w-10 h-10 border border-outline/30 rounded-[0.75rem] flex items-center justify-center bg-surface-variant/50">
          <span className="material-symbols-outlined text-outline">public</span>
        </div>
      </div>
    </section>
  )
}

function LoreSection({ mediaLinks }) {
  const udimo = pickMedia(mediaLinks, { role: 'illustration', sectionKey: 'lore', variant: 'udimo' })
  return (
    <section className="relative mt-6">
      <SectionDivider icon="history_edu" title="Character_Lore // 概述" />
      <div className="glass-panel-comp p-6 copper-border hard-shadow ml-2 relative">
        <div className="absolute -left-3 top-6 w-6 h-12 bg-surface-variant border border-outline flex items-center justify-center rounded-sm">
          <div className="w-1 h-8 bg-outline/30 rounded-full"></div>
        </div>
        <p className="font-headline-md text-lg text-on-surface-variant leading-relaxed mb-6 italic border-l-2 border-primary pl-4">
          "漫游于林间的术杖制造师，橡树与月亮的友人，你最沉静的朋友之一。"
        </p>
        {udimo && (
          <div className="mb-6 border border-outline/20 bg-black/20 p-2">
            <img alt={udimo.alt} className="w-full h-auto" src={udimo.url} />
          </div>
        )}
        <div className="grid grid-cols-2 gap-y-6 gap-x-4">
          {COMP_LORE_FIELDS.map((f) => (
            <div key={f.label} className="flex flex-col border-b border-outline/20 pb-2">
              <span className="font-data-mono text-[9px] text-outline uppercase mb-1">{f.label}</span>
              <span className="font-body-md text-sm text-on-surface">{f.value}</span>
            </div>
          ))}
        </div>
        <div className="mt-6">
          <h4 className="font-data-mono text-[9px] text-primary mb-3 uppercase tracking-widest">Scent_Notes // 香调</h4>
          <div className="flex flex-wrap gap-2">
            {COMP_SCENTS.map((s) => (
              <span key={s} className="px-3 py-1 bg-surface-container border border-outline/30 text-[11px] font-data-mono text-outline rounded-sm">{s}</span>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function InheritanceSection() {
  return (
    <section className="mt-6">
      <SectionDivider title="Inheritance // 木秀于林" />
      <div className="flex flex-col gap-3 mr-2">
        {COMP_INHERITANCE.map((item) => (
          <div key={item.lvl} className="glass-panel-comp p-4 copper-border flex gap-4 items-start relative group">
            <div className={`w-10 h-10 flex flex-col items-center justify-center shrink-0 border ${item.active ? 'border-primary/50 bg-primary/10' : 'border-outline/50 bg-surface'}`}>
              <span className={`font-data-mono text-[10px] ${item.active ? 'text-primary' : 'text-outline'}`}>LVL</span>
              <span className={`font-headline-md text-lg leading-none ${item.active ? 'text-primary' : ''}`}>{item.lvl}</span>
            </div>
            <p className="font-body-md text-sm text-on-surface-variant leading-relaxed">{item.html}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function SkillsSection({ mediaLinks }) {
  const ultimateArt = pickMedia(mediaLinks, { role: 'ritual-art', sectionKey: 'skills', variant: 'ultimate' })
  return (
    <section className="mt-6 flex flex-col gap-4">
      <SectionDivider title="Arcane_Skills // 神秘术" align="right" />
      {COMP_SKILLS.map((skill, i) => {
        const icon = pickMedia(mediaLinks, { role: 'skill-icon', sectionKey: 'skills', variant: skill.variant })
        return (
          <div key={skill.name} className={`skill-node p-5 copper-border hard-shadow relative ${i === 0 ? 'ml-4' : 'mr-4 mt-2'}`}>
            <div className="absolute top-0 right-0 bg-surface-variant text-[9px] font-data-mono px-2 py-1 border-b border-l border-outline/30 z-10">{skill.tag}</div>
            <div className="flex gap-4 items-start">
              <div className="w-[40%] shrink-0 border border-outline/30 overflow-hidden aspect-[2/3]">
                {icon && <img alt={icon.alt} className="w-full h-full object-cover" src={icon.url} />}
              </div>
              <div className="flex-1">
                <h5 className="font-headline-md text-2xl text-on-surface mb-1">{skill.name}</h5>
                <span className="text-[9px] font-data-mono text-primary tracking-widest uppercase block mb-4">{skill.nameEn}</span>
                <p className="text-sm font-body-md text-on-surface-variant leading-relaxed mb-4">{skill.desc}</p>
                <div className="border-t border-outline/20 pt-3 flex justify-between items-center">
                  <div className="text-[10px] font-data-mono text-outline italic">"{skill.quote}"</div>
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-primary rounded-full"></span>
                    <span className="w-2 h-2 border border-primary rounded-full"></span>
                    <span className="w-2 h-2 border border-primary rounded-full"></span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )
      })}
      {/* Ultimate */}
      <div className="bg-primary-container/10 glass-panel-comp p-6 border border-primary/50 hard-shadow relative overflow-hidden group ml-2 mr-2 mt-8 z-20">
        <div className="absolute -right-8 -bottom-8 opacity-5">
          <span className="material-symbols-outlined text-[180px]">forest</span>
        </div>
        <div className="relative z-10">
          <div className="flex items-center gap-2 mb-3">
            <span className="material-symbols-outlined text-primary text-sm">warning</span>
            <div className="text-primary font-data-mono text-[9px] tracking-[0.2em] uppercase">ULTIMATE_RITUAL // 至终的仪式</div>
          </div>
          <div className="w-full h-auto mb-4 border border-primary/30 overflow-hidden">
            {ultimateArt && <img alt={ultimateArt.alt} className="w-full h-full object-contain" src={ultimateArt.url} />}
          </div>
          <h5 className="font-headline-lg text-3xl text-primary mb-4">林间，静默将至</h5>
          <p className="text-sm font-body-md text-on-surface-variant mb-6 leading-relaxed">
            群体攻击，对敌方全体造成<span className="text-primary font-bold">400%</span>精神创伤；并使主目标陷入<span className="text-primary font-bold">[石化]</span>1回合。
          </p>
          <div className="bg-black/40 border border-primary/30 p-3 flex items-center justify-between">
            <span className="text-[10px] font-data-mono text-primary/80">"林地茂盛之中环伺滋长。"</span>
            <span className="text-[9px] font-data-mono text-primary tracking-widest border border-primary/50 px-2 py-1">RETICENT_WOODS_ARE_WATCHING</span>
          </div>
        </div>
      </div>
    </section>
  )
}

function VoiceSection() {
  return (
    <section className="mt-6 mb-8">
      <SectionDivider icon="graphic_eq" title="Voice_Records // 语音记录" />
      <div className="glass-panel-comp copper-border hard-shadow h-[300px] overflow-y-auto voice-scroll mx-2 p-1">
        {COMP_VOICES.map((v, i) => (
          <div key={v.title} className={`p-4 hover:bg-surface-variant/30 transition-colors ${i < COMP_VOICES.length - 1 ? 'border-b border-outline/20' : ''}`}>
            <div className="flex justify-between items-center mb-2">
              <span className="font-data-mono text-[10px] text-primary">{v.title}</span>
              <span className="material-symbols-outlined text-outline text-sm">play_circle</span>
            </div>
            <p className="font-body-md text-sm text-on-surface-variant mb-2">{v.zh}</p>
            <p className="font-data-mono text-[10px] text-outline/60 leading-relaxed italic">{v.en}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function CultureSection() {
  return (
    <section className="mt-6 mb-8">
      <SectionDivider icon="auto_stories" title="Culture // 文化" />
      <div className="flex flex-col gap-6 mx-2">
        {COMP_CULTURE.map((tab) => (
          <div key={tab.title} className={`glass-panel-comp p-6 copper-border hard-shadow relative ${tab.indent ? 'ml-4' : ''}`} style={{ transform: `rotate(${tab.rotate})` }}>
            <div className="pin-tape"></div>
            <div className="flex justify-between items-start mb-4">
              <h4 className="font-headline-md text-xl text-primary">{tab.title}</h4>
              <span className="font-data-mono text-[9px] text-outline uppercase tracking-widest">{tab.titleEn}</span>
            </div>
            {tab.paragraphs.map((p, i) => (
              <p key={i} className="font-body-md text-sm text-on-surface-variant leading-relaxed mb-4">{p}</p>
            ))}
            {tab.quote && (
              <div className="border-l-2 border-primary pl-4 italic text-outline">{tab.quote}</div>
            )}
          </div>
        ))}
        {/* Philosophy Dialogue */}
        <div className="bg-primary-container/10 glass-panel-comp p-6 border border-primary/50 hard-shadow relative mr-4">
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-primary text-sm">forum</span>
            <h4 className="font-headline-md text-xl text-primary">她的世界 有另一种哲学</h4>
          </div>
          <div className="space-y-3 font-body-md text-sm">
            {COMP_DIALOGUE.map((line, i) => (
              <div key={i} className="flex gap-2">
                <span className={`${line.self ? 'text-primary' : 'text-outline'} shrink-0`}>{line.who}:</span>
                <span className={line.self ? 'text-on-surface font-bold' : 'text-on-surface-variant'}>{line.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function CollectionSection({ mediaLinks }) {
  return (
    <section className="mt-6">
      <SectionDivider title="Collection // 藏品" />
      <div className="flex flex-col gap-4 mx-2">
        {COMP_COLLECTION.map((item) => {
          const icon = pickMedia(mediaLinks, { role: 'collection-item', sectionKey: 'collection', variant: item.variant })
          return (
            <div key={item.id} className="glass-panel-comp p-3 copper-border flex items-center gap-4">
              <div className="w-20 h-20 bg-black/40 border border-outline/20 shrink-0">
                {icon && <img className="w-full h-full object-contain" src={icon.url} alt={icon.alt} />}
              </div>
              <div>
                <div className="text-primary font-data-mono text-[10px] mb-1">{item.id}</div>
                <div className="text-on-surface text-sm font-bold">{item.name}</div>
                <div className="text-outline text-[10px] uppercase tracking-wider mt-1">{item.meta}</div>
              </div>
            </div>
          )
        })}
      </div>
      <footer className="mt-8 pt-4 pb-12 px-2 flex flex-col items-center gap-2 opacity-40">
        <div className="flex gap-2">
          <div className="w-1 h-1 bg-outline rounded-full"></div>
          <div className="w-1 h-1 bg-outline rounded-full"></div>
          <div className="w-1 h-1 bg-outline rounded-full"></div>
        </div>
        <div className="flex justify-between w-full font-data-mono text-[9px] mt-4 border-t border-outline/30 pt-4">
          <span>FILE_REF: ARC_03_DRUVIS</span>
          <span>BUILD_LC_3.2</span>
        </div>
      </footer>
    </section>
  )
}

function BottomTabs() {
  return (
    <div className="fixed bottom-0 left-0 w-full z-50 h-16 bg-surface-container-lowest border-t border-outline-variant flex items-end">
      <button className="flex-1 h-full flex flex-col items-center justify-center gap-1 border-r border-outline-variant/30 bg-primary-container/10 border-t-2 border-t-primary">
        <span className="material-symbols-outlined text-primary text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>dataset</span>
        <span className="font-data-mono text-[9px] font-bold text-primary tracking-widest">DOSSIER</span>
      </button>
      <button className="flex-1 h-14 flex flex-col items-center justify-center gap-1 border-r border-outline-variant/30 hover:bg-surface-variant/50 transition-colors">
        <span className="material-symbols-outlined text-outline text-xl">menu_book</span>
        <span className="font-data-mono text-[9px] font-bold text-outline tracking-widest">ARCHIVE</span>
      </button>
      <button className="flex-1 h-14 flex flex-col items-center justify-center gap-1 border-r border-outline-variant/30 hover:bg-surface-variant/50 transition-colors">
        <span className="material-symbols-outlined text-outline text-xl">psychology</span>
        <span className="font-data-mono text-[9px] font-bold text-outline tracking-widest">COMBAT</span>
      </button>
    </div>
  )
}

export default function ComprehensiveProfilePage() {
  const [skin, setSkin] = useState('initial')
  // GET /api/wiki/pages/wiki/profile-comprehensive → mediaLinks[]（契约检查器按 M 可见）
  const mediaLinks = usePageMedia('comprehensive', 'wiki/profile-comprehensive')

  return (
    <div className="theme-comp archival-bg text-on-background font-body-md min-h-screen overflow-x-hidden selection:bg-primary-container selection:text-on-primary-container">
      <TopNav />
      {/* Decor */}
      <div className="stamp-overlay top-32 -left-20 text-[120px] rotate-[-75deg]">DRUVIS_III</div>
      <div className="stamp-overlay bottom-80 right-[-40px] text-[80px] rotate-[15deg]">CONFIDENTIAL</div>
      <main className="relative z-10 pt-20 pb-32 px-4 flex flex-col gap-8 max-w-lg mx-auto">
        <HeroSection skin={skin} onSkinChange={setSkin} mediaLinks={mediaLinks} />
        <StatsGrid />
        <LoreSection mediaLinks={mediaLinks} />
        <InheritanceSection />
        <SkillsSection mediaLinks={mediaLinks} />
        <VoiceSection />
        <CultureSection />
        <CollectionSection mediaLinks={mediaLinks} />
      </main>
      <BottomTabs />
    </div>
  )
}
