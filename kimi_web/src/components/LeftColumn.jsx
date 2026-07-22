import { PROFILE_ROWS, PROFILE_QUOTE, SKILLS, CULTURE_ENTRIES } from '../data/druvis'
import { pickMedia } from '../media/contract'

function OperativeCard({ mediaLinks }) {
  // 头像复用舞台"初始立绘"同一份对象（裁剪显示），不再单独持有路径
  const avatar = pickMedia(mediaLinks, { role: 'standee', sectionKey: 'stage', variant: 'initial' })
  return (
    <div className="glass-panel p-4 -rotate-1 relative group cursor-pointer border-l-4 border-l-primary mb-6">
      <div className="absolute top-2 right-2 text-[10px] font-data-mono text-outline">INDEX_03</div>
      <div className="flex gap-4 items-center">
        <div className="w-14 h-14 bg-black border border-outline/30 overflow-hidden relative">
          {avatar && <img alt={avatar.alt} className="w-full h-full object-cover scale-150 object-top opacity-80 group-hover:opacity-100 transition-opacity" src={avatar.url} />}
          <div className="absolute inset-0 border border-primary/50 m-1"></div>
        </div>
        <div>
          <h2 className="font-headline-md text-2xl text-primary m-0 leading-none">槲寄生</h2>
          <div className="font-data-mono text-xs text-on-surface uppercase mt-1">Druvis III</div>
          <div className="font-data-mono text-[9px] text-outline mt-1 flex gap-2">
            <span>✦✦✦✦✦✦</span>
            <span>PLANT (木)</span>
          </div>
        </div>
      </div>
    </div>
  )
}

function ProfileStickyNote() {
  return (
    <div className="sticky-note p-5 w-72 rotate-3 ml-4 relative mb-10">
      <div className="tape"></div>
      <div className="absolute -right-4 -top-4 stamp">VERIFIED</div>
      <h3 className="font-headline-md text-lg border-b border-black/20 pb-2 mb-3">PROFILE_DATA</h3>
      <ul className="font-data-mono text-xs space-y-2">
        {PROFILE_ROWS.map((row, i) => (
          <li key={row.label} className={`flex justify-between pb-1 ${i < PROFILE_ROWS.length - 1 ? 'border-b border-black/10' : ''}`}>
            <span className="opacity-60">{row.label}</span> <span>{row.value}</span>
          </li>
        ))}
      </ul>
      <div className="mt-4 p-2 bg-black/5 text-[10px] italic font-body-md border-l-2 border-primary leading-tight">
        "{PROFILE_QUOTE}"
      </div>
    </div>
  )
}

function SkillCard({ skill, mediaLinks }) {
  const icon = pickMedia(mediaLinks, { role: 'skill-icon', sectionKey: 'skills', variant: skill.variant })
  if (skill.ultimate) {
    return (
      <div className="border border-primary/40 p-2 bg-primary/5 hover:bg-primary/10 transition-colors cursor-help group relative overflow-hidden flex gap-3">
        <div className="w-16 h-24 shrink-0 overflow-hidden border border-primary/30 z-10">
          {icon && <img alt={icon.alt} className="w-full h-full object-cover opacity-90 group-hover:opacity-100 transition-opacity" src={icon.url} />}
        </div>
        <div className="flex-1 z-10">
          <div className="absolute right-0 top-0 text-4xl text-primary opacity-10 material-symbols-outlined -rotate-12 transform translate-x-2 -translate-y-2">auto_awesome</div>
          <div className="flex justify-between items-center mb-1">
            <span className="font-headline-md text-sm text-primary">{skill.name}</span>
            <span className="text-[10px] font-data-mono text-primary px-1 border border-primary">ULTIMATE</span>
          </div>
          <p className="text-[9px] font-data-mono text-outline leading-tight">{skill.desc}</p>
        </div>
      </div>
    )
  }
  return (
    <div className="border border-outline/20 p-2 bg-surface/50 hover:border-primary/50 transition-colors cursor-help group flex gap-3">
      <div className="w-16 h-24 shrink-0 overflow-hidden border border-outline/30">
        {icon && <img alt={icon.alt} className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" src={icon.url} />}
      </div>
      <div className="flex-1">
        <div className="flex justify-between items-center mb-1">
          <span className="font-headline-md text-sm text-on-surface group-hover:text-primary transition-colors">{skill.name}</span>
          <span className="text-[10px] font-data-mono text-[#933334] px-1 border border-[#933334]">{skill.tag}</span>
        </div>
        <p className="text-[9px] font-data-mono text-outline leading-tight">{skill.desc}</p>
      </div>
    </div>
  )
}

function TacticalSkills({ mediaLinks }) {
  return (
    <div className="glass-panel p-4 w-80 -rotate-2 mb-8">
      <h3 className="font-data-mono text-xs text-primary mb-3 flex justify-between items-center">
        <span>&gt; TACTICAL_SKILLS</span>
        <span className="material-symbols-outlined text-sm">psychology</span>
      </h3>
      <div className="space-y-3">
        {SKILLS.map((s) => <SkillCard key={s.name} skill={s} mediaLinks={mediaLinks} />)}
      </div>
    </div>
  )
}

function CulturePanel() {
  return (
    <div className="glass-panel p-4 w-80 rotate-1 mb-8">
      <h3 className="font-data-mono text-xs text-primary mb-3 flex justify-between items-center border-b border-outline/30 pb-2">
        <span>&gt; CULTURE // 文化</span>
        <span className="material-symbols-outlined text-sm">history_edu</span>
      </h3>
      <div className="space-y-4 text-[10px] font-body-md text-on-surface/80 leading-relaxed">
        {CULTURE_ENTRIES.map((entry) => (
          <div key={entry.title}>
            <div className="text-primary font-bold mb-1">{entry.title}</div>
            <p>{entry.body}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function LeftColumn({ mediaLinks }) {
  return (
    <div className="absolute left-10 top-24 w-80 z-20 h-[calc(100vh-140px)] overflow-y-auto pr-4 pb-10 thin-scroll">
      <OperativeCard mediaLinks={mediaLinks} />
      <ProfileStickyNote />
      <TacticalSkills mediaLinks={mediaLinks} />
      <CulturePanel />
    </div>
  )
}
