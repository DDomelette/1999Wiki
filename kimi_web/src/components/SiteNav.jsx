import { useState } from 'react'

export const PAGES = [
  { id: 'advanced', title: 'Advanced Profile', subtitle: '桌面 · 双立绘换装', device: 'DESKTOP', key: '1' },
  { id: 'dossier', title: 'Archival Dossier', subtitle: '桌面 · 档案终端', device: 'DESKTOP', key: '2' },
  { id: 'selection', title: 'Mobile Selection', subtitle: '移动端 · 角色选择', device: 'MOBILE', key: '3' },
  { id: 'comprehensive', title: 'Comprehensive Profile', subtitle: '移动端 · 长卷档案', device: 'MOBILE', key: '4' },
]

export default function SiteNav({ current, onNavigate }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="fixed bottom-5 right-5 z-[100] flex flex-col items-end gap-3 font-mono">
      {open && (
        <div className="bg-[#160c07]/95 backdrop-blur-md border border-[#e2610b]/40 shadow-[8px_8px_0px_0px_rgba(0,0,0,0.8)] p-3 w-64">
          <div className="text-[9px] tracking-[0.25em] text-[#a78b7e] border-b border-[#a78b7e]/30 pb-2 mb-2 uppercase">
            Stitch 收藏集 · 复刻导航
          </div>
          {PAGES.map((page) => (
            <button
              key={page.id}
              onClick={() => { onNavigate(page.id); setOpen(false) }}
              className={`w-full text-left px-3 py-2 mb-1 border transition-all group ${current === page.id ? 'border-[#e2610b] bg-[#e2610b]/15 text-[#e2610b]' : 'border-[#a78b7e]/25 text-[#f6ded4]/70 hover:border-[#e2610b]/60 hover:text-[#e2610b]'}`}
            >
              <div className="flex justify-between items-center">
                <span className="text-[11px] font-bold tracking-wider">{page.key}. {page.title}</span>
                <span className={`text-[8px] px-1 border ${page.device === 'MOBILE' ? 'border-[#ffb693]/50 text-[#ffb693]' : 'border-[#a78b7e]/50 text-[#a78b7e]'}`}>{page.device}</span>
              </div>
              <div className="text-[9px] text-[#a78b7e] mt-0.5">{page.subtitle}</div>
            </button>
          ))}
          <div className="text-[8px] text-[#a78b7e]/60 mt-2 tracking-widest">快捷键 1-4 切换界面</div>
        </div>
      )}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-12 h-12 rounded-full bg-[#e2610b] text-[#1c110b] flex items-center justify-center shadow-[0_0_20px_rgba(226,97,11,0.5)] border-2 border-[#1c110b] hover:scale-105 active:scale-95 transition-transform"
        title="切换复刻界面"
      >
        <span className="material-symbols-outlined">{open ? 'close' : 'widgets'}</span>
      </button>
    </div>
  )
}
