import { _demoRawRowsForPage, _demoBackendConfig } from '../media/contract'

// 契约检查器 · 实时模式 —— 可视化"媒体映射由后端掌控"这条边界。
// 数据源：当前页面通过 usePageMedia 实际消费并上报的 mediaLinks[]。
// 左侧：后端 wiki_media_links 原始行（前端不可见）
// 右侧：API 清洗后下发、页面实际使用的 DTO（14 字段）
// 仅作演示教具；按 M / Esc 或点右下角 DTO 浮标开关。

const FORBIDDEN = ['objectKey / object_key', 'internalEndpoint (minio:9000)', 'bucket / objectPrefix', 'MinIO 凭证 · 容器名 · 磁盘路径', '文件名推断规则']

const PAGE_NAMES = {
  advanced: '1 · Advanced Profile',
  dossier: '2 · Archival Dossier',
  selection: '3 · Mobile Selection',
  comprehensive: '4 · Comprehensive Profile',
}

function RowList({ title, tone, rows, emptyText }) {
  return (
    <div className="flex-1 min-w-0 flex flex-col">
      <div className={`font-data-code text-[10px] tracking-widest uppercase mb-1 ${tone}`}>
        {title} <span className="opacity-60">（{rows.length} 行）</span>
      </div>
      <div className="max-h-[38vh] overflow-y-auto border border-white/10 rounded bg-black/60 divide-y divide-white/5">
        {rows.length === 0 && <div className="p-3 font-mono text-[10px] text-white/40">{emptyText}</div>}
        {rows.map((row, i) => (
          <pre key={row.mediaId ?? row.media_id ?? i} className="text-[10px] leading-relaxed font-mono whitespace-pre-wrap break-all p-2">
            {JSON.stringify(row, null, 2)}
          </pre>
        ))}
      </div>
    </div>
  )
}

export default function MediaInspector({ onClose, currentPage, liveMedia }) {
  const backend = _demoBackendConfig()
  const isLive = liveMedia && liveMedia.appPage === currentPage && liveMedia.pageId
  const rawRows = isLive ? _demoRawRowsForPage(liveMedia.pageId) : []
  const dtos = isLive ? liveMedia.links : []

  return (
    <div className="fixed inset-x-0 bottom-0 z-[90] pointer-events-none flex justify-center p-3">
      <div className="pointer-events-auto w-full max-w-4xl bg-[#12100e]/95 backdrop-blur-xl border border-amber-500/40 rounded-lg shadow-2xl p-4 text-amber-100/90">
        <div className="flex items-center justify-between mb-3 gap-3">
          <div className="font-data-code text-[11px] tracking-widest uppercase text-amber-400 truncate">
            MEDIA CONTRACT INSPECTOR · 实时模式 —— 当前页：{PAGE_NAMES[currentPage] ?? currentPage}
          </div>
          <button onClick={onClose} className="shrink-0 text-amber-400/70 hover:text-amber-300 text-xs border border-amber-500/40 rounded px-2 py-0.5">ESC</button>
        </div>

        {isLive ? (
          <div className="flex flex-col md:flex-row gap-3">
            <RowList
              title={`① 后端侧 · wiki_media_links 原始行（前端不可见）· ${liveMedia.pageId}`}
              tone="text-red-400/90"
              rows={rawRows}
              emptyText="该页在后端表中无媒体行"
            />
            <div className="hidden md:flex items-center text-amber-500/60 font-mono text-lg">→</div>
            <RowList
              title="② API 下发 · 本页实际使用的 mediaLinks[] DTO"
              tone="text-emerald-400/90"
              rows={dtos}
              emptyText="清洗后无有效媒体（非公共 URL 会被丢弃）"
            />
          </div>
        ) : (
          <div className="border border-dashed border-amber-500/30 rounded p-4 font-mono text-[11px] text-amber-200/70 leading-relaxed">
            当前页尚未上报媒体数据 —— 正常情况下四个页面均已接入契约层，
            若看到此提示，说明该页的 usePageMedia 上报还未发生（或刚切换页面）。
          </div>
        )}

        <div className="mt-3 border-t border-white/10 pt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="font-data-code text-[10px] tracking-widest uppercase text-red-400/80">止步于后端：</span>
          {FORBIDDEN.map((f) => (
            <span key={f} className="font-mono text-[10px] text-red-300/60 line-through decoration-red-500/60">{f}</span>
          ))}
        </div>
        <div className="mt-1 font-mono text-[10px] text-amber-200/50">
          URL 运行时生成：publicBaseUrl（{backend.publicBaseUrl}）+ objectKey → 换域名/端口只改配置，数据库零改动
        </div>
      </div>
    </div>
  )
}
