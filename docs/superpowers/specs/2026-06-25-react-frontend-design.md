# OUTDATED - React + Vite 前端设计 · 1999Search RAG

> OUTDATED: Superseded by the July 3 Huiji crawler data and parent-child hybrid RAG specs. Keep this file for historical reference only.

> CURRENT STATUS 2026-06-29: Historical design note only. Current startup source of truth is project-root `start.ps1` / `start.bat`. React Vite must be started with `--host 127.0.0.1 --port 5173 --strictPort`; do not allow auto-fallback to 5174.

> **状态**:设计已与用户逐节确认,待用户最终审阅后转入 writing-plans。
> **日期**:2026-06-25
> **作者**:brainstorming 会话

## 0. 背景与目标

1999Search RAG 项目已完成 FastAPI 后端 + 三套前端(HTML+JS / Streamlit / Gradio)+ 一键启动脚本。现新增第四套前端:基于 **React 18 + Vite 5 + TypeScript** 的沉浸式滚动叙事网站,复用现有后端 RAG 能力并新增 SSE 流式问答端点。

**核心体验**:首页(视频背景)→ 滚动进入资料页(6 板块全屏切换 + 进场动画)→ 继续下滑进入问答系统(流式逐字 + 消息弹出动画)。整体复古暖色调,神秘学 + 英伦风,字体取自 Obsidian vault 的"字体大全-1999"风格(用免费 web 字体替代)。

## 1. 已确认的关键决策

| 项 | 决策 | 理由 |
|----|------|------|
| 流式实现 | 后端新增 SSE `/ask/stream` | 真流式,首字延迟=首 token 时间,体验最佳 |
| 字体 | 霞鹜文楷 LXGW WenKai(正文)+ Oswald(DIN 替代,数字/英文标题) | 免费 web 字体,复古手写感接近 HYWenHei,不打包 35MB 版权字体 |
| 板块内容来源 | 复用 RAG 6 大类(人物/心相/剧情/世界/阵营/日历) | 与问答系统共用同一知识库,数据一致 |
| 视频背景 | 先占位 + 预留 `public/videos/pv.mp4` 槽位 | B站防盗链无法 iframe 局部模糊,用户后续手动放 mp4 |
| 风格参考 | PKMer + AnuPpuccin + Blue Topaz 三者揉合 | 复古暖色 + 卡片花边 + 神秘学元素 |
| 主题 | 三套(深色复古暖 `dark-warm` / 浅色羊皮纸 `parchment` / 神秘紫夜间 `mystic-purple`) | 控制栏循环切换,localStorage 持久化 |
| 引用网站 | 重返未来1999 官网(后续可加) | 控制栏外链板块 |
| 板块切换机制 | 全屏 CSS scroll-snap(`y mandatory`)| "滚轮下滑切换板块"体验最直接 |
| 下载选项 | 单一按钮(点击不跳转,toast 提示"链接待补") | YAGNI,后续拿链接再实现 |
| 问答默认 category | 顶部下拉,默认"全部"(null)| 用户可随时切到具体类 |
| 技术栈 | React 18 + Vite 5 + TypeScript + Framer Motion + Zustand + CSS scroll-snap | 方案 A:动画声明式、滚动原生流畅、状态管理轻量 |

## 2. 整体架构

### 2.1 目录结构

```
1999Search/
├── backend/
│   ├── main.py              # 修改:新增 /ask/stream /categories /category/{key}/docs 路由 + CORS 加 5173
│   ├── sse.py               # 新增:SSE 事件编码 + rag_stream_generator
│   ├── schemas.py           # 修改:新增 CategoryMeta / CategoryDoc / StreamEvent 模型
│   └── categories_meta.py   # 新增:6 板块元数据(标题/简介/cover_prompt)静态定义
├── src/rag/chain.py         # 修改:新增 _stream_llm 方法(DeepSeek .stream() 封装)
├── frontend/
│   └── react-app/           # 新增
│       ├── public/
│       │   ├── fonts/       # 霞鹜文楷 woff2(本地兜底)+ Oswald woff2
│       │   └── videos/      # pv.mp4 占位(README 说明用户后续放真视频)
│       ├── src/
│       │   ├── api/         # sse.ts(fetch+ReadableStream) / http.ts(/health /ask /categories /category/{key}/docs)
│       │   ├── components/
│       │   │   ├── Sidebar.tsx        # 左侧控制栏(覆盖式,按钮唤出/缩回)
│       │   │   ├── TopNav.tsx         # 顶端浮现导航栏
│       │   │   ├── sections/
│       │   │   │   ├── HomeSection.tsx        # 首页(视频+下载)
│       │   │   │   ├── DataSection.tsx        # 资料页容器(scroll-snap 父,嵌 6 CategoryPanel)
│       │   │   │   ├── CategoryPanel.tsx      # 单板块(进场动画)
│       │   │   │   └── ChatSection.tsx        # 问答页
│       │   │   ├── chat/
│       │   │   │   ├── MessageBubble.tsx      # 消息(用户弹出+缩放,LLM 流式容器)
│       │   │   │   ├── StreamingText.tsx      # 流式逐字 reveal
│       │   │   │   └── ChatInput.tsx          # 输入框
│       │   │   └── ui/               # ThemeToggle / CategorySelect / LinkList / SectionDivider
│       │   ├── store/        # themeStore.ts / uiStore.ts / chatStore.ts
│       │   ├── styles/       # themes.css(3 套主题 CSS 变量) / global.css / decorative.css(花边/纹理)
│       │   ├── hooks/        # useScrollSpy / useTopNavTrigger / useCategoryData / useReducedMotion 兜底
│       │   ├── types/        # 共享 TS 类型(SourceItem / Message / CategoryMeta / Doc)
│       │   ├── App.tsx       # 根:scroll-snap 容器 + 3 大区 + 全局 hook
│       │   └── main.tsx
│       ├── index.html        # 字体 preconnect + link
│       ├── vite.config.ts    # proxy /api → 127.0.0.1:8000,port 5173
│       ├── tsconfig.json
│       └── package.json
├── start.ps1 / start.bat     # 修改:增加延迟启动 Vite dev(端口 5173)段
└── README.md                 # 修改:三前端地址表加 React 行,环境准备加 node/npm
```

### 2.2 三段式滚动结构

```
App.tsx (overflow-y: scroll; scroll-snap-type: y mandatory; scroll-behavior: smooth)
├─ HomeSection   (h:100vh; scroll-snap-align: start; data-snap-section="home")
├─ DataSection   (h:100vh; scroll-snap-align: start; data-snap-section="data")
│   └─ 内嵌 6× CategoryPanel (各 h:100vh, 独立 scroll-snap, data-snap-section="data:{key}")
└─ ChatSection   (min-h:100vh; scroll-snap-align: start; data-snap-section="chat")
```

外层 snap 到 3 大 Section;DataSection 内层再 snap 6 板块。第 6 板块末尾再下滑 → 外层 snap 到 ChatSection。

### 2.3 启动集成

start.ps1 / start.bat 增加"延迟启动 Vite dev server"段(端口 5173),与其他前端并列。先检测 `frontend/react-app/node_modules` 是否存在,不存在则提示 `npm install`。三前端地址表增加 React 行。

## 3. 页面布局与动画

### 3.1 首页 HomeSection

**布局**:
- 背景层:`<video>` autoplay muted loop,poster 兜底
- 视频外围渐变模糊:两层 video 播放同一文件,清晰层在上用径向 mask 镂空中心圆,模糊层(`filter: blur(24px) brightness(0.6); transform: scale(1.1)`)在下铺满全屏
- 内容层(z=10):主标题"重返未来:1999"(LXGW WenKai 700)、副标题"REVERSE: 1999"(Oswald 700)、版本号"3.8 版本 · 世纪末尺度"(Oswald 500 金色)
- 底部:滚轮提示(上下浮动 loop 动画)
- 中下:单一"立即下载"按钮,hover 金光描边,点击 toast"下载链接待补"

**视频 mask CSS**:
```css
.video-bg {
  position: absolute; inset: 0; object-fit: cover;
  -webkit-mask: radial-gradient(ellipse 50% 50% at center, #000 30%, transparent 75%);
}
.video-blur-layer {
  position: absolute; inset: 0; object-fit: cover;
  filter: blur(24px) brightness(0.6);
  transform: scale(1.1);
}
```

**标题进场动画**(Framer Motion,页面挂载触发):
- 主标题:opacity 0→1, translateY 20px→0, duration 0.8s, ease easeOut
- 副标题:延迟 0.3s 同款
- 版本号:延迟 0.6s 同款

**占位视频兜底**:无 pv.mp4 时用 CSS 渐变动画(深褐→金紫径向渐变 + 缓慢旋转)作背景,保持视觉不空。

### 3.2 资料页 DataSection

**布局**:左侧固定板块导航(当前高亮,点击跳转),右侧内容区(6 CategoryPanel 纵向 snap)。

**单板块进场动画时序**(IntersectionObserver `threshold: 0.5` 触发):
```
t=0ms      标题: opacity 0→1, translateY 20px→0, duration 800ms
t=300ms    主描述: 流式逐字 reveal,每字 18ms(快),整段 1.5-2.5s
t=500ms    图片: opacity 0→1, scale 1.1→1, translateY 40px→0, filter blur(8px)→0, duration 1200ms
t=同上     装饰花边: strokeDashoffset 动画绘制
```

**Framer Motion variants**:
```tsx
const panelVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.3 } }
}
const titleVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.8, ease: "easeOut" } }
}
const imageVariants = {
  hidden: { opacity: 0, scale: 1.1, y: 40, filter: "blur(8px)" },
  visible: { opacity: 1, scale: 1, y: 0, filter: "blur(0px)",
             transition: { duration: 1.2, ease: "easeOut" } }
}
```

**流式逐字主描述**:描述文本来自 `/category/{key}/docs?limit=5` 返回的 5 篇文档 `snippet` 拼接(每段约 200 字,总长约 1000 字),前端拿到完整文本后定时器每 18ms 推一字符到可见队列,每字符包 `<motion.span>` 做 `opacity 0→1 + y 8→0`。18ms/字比聊天 40ms/字快。板块进入视口时才发起该 fetch(IntersectionObserver 触发),避免 6 板块同时拉取。

### 3.3 问答页 ChatSection

**布局**:
- 顶部:category 下拉(神秘学风,默认"全部")
- 消息区(可滚动):用户消息右对齐,LLM 消息左对齐
- 底部:输入框 + 发送按钮

**用户消息发送动画**(用 Framer Motion `layoutId` 共享布局):
- 输入框内文字包一层 `<motion.span layoutId="last-input">`,发送时该 span 内容移到消息列表末位 `<motion.div layoutId="last-input">`
- Framer Motion 自动计算两位置差,做 `scale 1.3→1 + y 位移`过渡,spring `stiffness: 300, damping: 20`
- 输入框文字发送后清空,消息列表项接管 layoutId

**LLM 流式字符动画**:
- SSE 每 token 到达 → 拆字符 → 每字符 `<motion.span variants={{ hidden:{opacity:0, scale:0.5}, visible:{opacity:1, scale:1, transition:{duration:0.2}} }}>` 塞入消息 div
- `AnimatePresence` + key=charIndex 保证只对新字符动画
- 光标 `▌` 流式期间闪烁,流结束淡出
- 回答结束后来源条淡入

### 3.4 控制栏 Sidebar(覆盖式)

**触发**:左上角 ☰ 按钮 click → 滑入;再次 click 或点遮罩 → 滑出。

**内容**:
- 关闭按钮 ×
- 主题切换 ◐(三套循环)
- 引用网站:重返未来1999 官网(外链新标签)
- 板块速达(二级菜单):人物/心相/剧情/世界/阵营/日历(点击跳对应板块)

**动画**:`motion.aside` `initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }}`,transition `type: "spring", stiffness: 260, damping: 30`。遮罩 `motion.div` opacity 0→0.5。

### 3.5 顶端导航栏 TopNav

**触发**:鼠标贴顶端(`mousemove y < 8px`)或滚到顶(`scrollY < 50`)→ 滑入;否则滑出。

**内容**:[☰] [首页] [资料] [问答](锚点跳转对应 Section)。

**z-index 层级**(满足"重叠时控制栏在导航下方,导航在主页面下方"):
- Sidebar: 100
- TopNav: 90
- Section 内容: 1
- 视频背景: 0

## 4. 配色与字体系统

### 4.1 三套主题(CSS 变量,`data-theme` 属性切换)

```css
/* 主题1:深色复古暖(默认) */
[data-theme="dark-warm"] {
  --bg-base:        #1a1410;
  --bg-elevated:    #241c16;
  --bg-overlay:     rgba(26, 20, 16, 0.85);
  --text-primary:   #e8d9c0;
  --text-secondary: #b8a888;
  --text-muted:     #7a6a52;
  --accent-gold:    #d4af37;
  --accent-purple:  #7b5ea7;
  --accent-rust:    #a85432;
  --border-subtle:  #3a2e22;
  --border-card:    #4a3a2a;
  --border-glow:    rgba(212, 175, 55, 0.4);
  --shadow-card:    0 4px 20px rgba(0, 0, 0, 0.5), 0 0 1px var(--border-card);
  --shadow-glow:    0 0 20px var(--border-glow);
  --font-body:      'LXGW WenKai', 'Noto Serif SC', serif;
  --font-display:   'Oswald', 'LXGW WenKai', sans-serif;
  --font-mono:      'JetBrains Mono', monospace;
}

/* 主题2:浅色羊皮纸 */
[data-theme="parchment"] {
  --bg-base:        #f4ead5;
  --bg-elevated:    #fbf5e6;
  --bg-overlay:     rgba(244, 234, 213, 0.9);
  --text-primary:   #3a2818;
  --text-secondary: #6b5236;
  --text-muted:     #9a8260;
  --accent-gold:    #b8860b;
  --accent-purple:  #6b4c8a;
  --accent-rust:    #8b3a1f;
  --border-subtle:  #d9c9a8;
  --border-card:    #b8a072;
  --border-glow:    rgba(184, 134, 11, 0.35);
  --shadow-card:    0 2px 12px rgba(120, 80, 40, 0.15), 0 0 1px var(--border-card);
  --shadow-glow:    0 0 16px var(--border-glow);
  --font-body:      'LXGW WenKai', 'Noto Serif SC', serif;
  --font-display:   'Oswald', 'LXGW WenKai', sans-serif;
  --font-mono:      'JetBrains Mono', monospace;
}

/* 主题3:神秘紫夜间 */
[data-theme="mystic-purple"] {
  --bg-base:        #120a1f;
  --bg-elevated:    #1c1230;
  --bg-overlay:     rgba(18, 10, 31, 0.88);
  --text-primary:   #d9c9f0;
  --text-secondary: #a890c8;
  --text-muted:     #6a5488;
  --accent-gold:    #e8c547;
  --accent-purple:  #9d7ec9;
  --accent-rust:    #c4628a;
  --border-subtle:  #2e1f48;
  --border-card:    #3e2a5e;
  --border-glow:    rgba(157, 126, 201, 0.5);
  --shadow-card:    0 4px 24px rgba(0, 0, 0, 0.6), 0 0 1px var(--border-card);
  --shadow-glow:    0 0 24px var(--border-glow);
  --font-body:      'LXGW WenKai', 'Noto Serif SC', serif;
  --font-display:   'Oswald', 'LXGW WenKai', sans-serif;
  --font-mono:      'JetBrains Mono', monospace;
}
```

**切换机制**:Zustand `themeStore` 持久化到 `localStorage`,初值 `dark-warm`。`<html data-theme="...">` 上设属性。切换按钮 ◐ 在三套间循环 `dark-warm → parchment → mystic-purple → dark-warm`。

### 4.2 字体加载

**霞鹜文楷 LXGW WenKai**(正文):
- 来源:`https://cdn.jsdelivr.net/npm/lxgw-wenkai-webfont@1.7.0/style.css`
- 字重:Regular + Bold
- 本地兜底:下载 woff2 放 `public/fonts/`,CDN 失败时 fallback

**Oswald**(数字/英文标题,DIN 替代):
- 来源:Google Fonts `Oswald`
- 字重:500 / 700
- 用途:版本号、英文标题、数字数据

**加载策略**(index.html):
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://cdn.jsdelivr.net">
<link href="https://cdn.jsdelivr.net/npm/lxgw-wenkai-webfont@1.7.0/style.css" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap" rel="stylesheet">
```
`font-display: swap` 确保首屏不阻塞,先用 `Noto Serif SC` 系统字体兜底。

### 4.3 字体应用规则

| 元素 | font-family | 字重 / 字号 |
|------|-------------|-------------|
| 主标题"重返未来:1999" | LXGW WenKai | 700 / clamp(2.5rem, 6vw, 4.5rem) |
| 英文标题"REVERSE: 1999" | Oswald | 700 / clamp(1.5rem, 4vw, 3rem),letter-spacing 0.1em |
| 版本号"3.8 版本" | Oswald | 500 / 1.25rem,金色 |
| 板块标题 | LXGW WenKai | 700 / clamp(2rem, 5vw, 3.5rem) |
| 主描述流式文字 | LXGW WenKai | 400 / 1.125rem,line-height 1.9 |
| 聊天消息 | LXGW WenKai | 400 / 1rem |
| 来源标签 | LXGW WenKai | 400 / 0.875rem,`--text-secondary` |
| category 下拉 | LXGW WenKai | 500 / 0.95rem |
| 代码(若有) | JetBrains Mono | 400 / 0.9rem |

### 4.4 神秘学/英伦风装饰元素

1. **PKMer 花边卡片**:卡片四角金色角花(SVG `<path>` strokeDashoffset 绘制动画),`--border-card` 描边,`--shadow-card` 辉光
2. **AnuPpuccin 彩虹标识**:板块标题左侧渐变竖条(gold→purple→rust)作板块标识色
3. **Blue Topaz 网址图标**:引用网站列表每项前加神秘学符号 SVG(六芒星/塔罗/月相)
4. **分割线**:SVG 花边横线(中央菱形 + 两侧藤蔓),非纯 `border-bottom`
5. **纹理叠加**:body 叠低透明度羊皮纸噪声纹理(SVG noise filter,`mix-blend-mode: overlay`)

## 5. 后端 SSE 与数据接口

### 5.1 现有接口(不动)

| 端点 | 方法 | 用途 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/ask` | POST | 一次性问答(其他前端仍用)|

### 5.2 新增 `/ask/stream` — SSE 流式问答

**请求**:`POST /ask/stream`,`Content-Type: application/json`
```json
{ "question": "6的属性", "category": "人物" }
```
`category` 可空(空 = 全库检索)。

**响应**:`Content-Type: text/event-stream`,`Cache-Control: no-cache`,`Connection: keep-alive`,`X-Accel-Buffering: no`

**事件序列**:
```
event: sources
data: {"sources":[{"name":"塞梅尔维斯","category":"人物","source":"...","score":0.63},...]}

event: token
data: {"token":"6"}

event: token
data: {"token":"是"}

event: done
data: {"answer":"6 是一位...完整文本","sources":[...同上]}
```

- `sources`:1 次,检索完成后、LLM 首 token 前发,前端立即渲染来源条
- `token`:N 次,DeepSeek 流式 chunk 拆字符后逐个发
- `done`:1 次,携带完整 answer + sources,前端收尾(光标淡出、来源固化)
- `error`:异常时 `data: {"message":"..."}`

**不用 EventSource**:EventSource 只支持 GET、不能带 POST body。前端用 `fetch` + `ReadableStream` 手动解析 SSE。

### 5.3 新增 `/categories` — 板块元数据

**请求**:`GET /categories`
**响应**:
```json
{
  "categories": [
    {
      "key": "人物",
      "title": "人物",
      "subtitle": "Characters",
      "description": "重返未来:1999 中的角色档案,含 UTTU 人物、神秘学家等",
      "doc_count": 105,
      "cover_prompt": "维多利亚时代英伦人物肖像,神秘学符号点缀,暖色调"
    }
  ]
}
```
`doc_count` 从向量库 `_collection.count(where={"category": key})` 实时取;其余字段从 `backend/categories_meta.py` 静态定义读取。

### 5.4 新增 `/category/{key}/docs` — 板块文档列表

**请求**:`GET /category/人物/docs?limit=50`
**响应**:
```json
{
  "key": "人物",
  "docs": [
    {
      "name": "塞梅尔维斯",
      "source": "100-UTTU人物辑录/.../塞梅尔维斯:Spathodea.md",
      "snippet": "塞梅尔维斯是...(正文前 200 字)"
    }
  ]
}
```
`snippet` 取该文档第一个 chunk 的 page_content 前 200 字。

### 5.5 后端实现要点

**`backend/sse.py`**:
```python
def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

async def rag_stream_generator(chain, question: str, category: str | None) -> AsyncGenerator[str, None]:
    # 1. 检索
    sources = chain._retriever.search(question, category=category)
    source_items = [{"name": s["name"], "category": s["category"],
                     "source": s["source"], "score": s["score"]} for s in sources]
    yield sse_event("sources", {"sources": source_items})

    # 2. api_key 空降级
    if not chain.llm_ready():
        msg = "请在 .env 中配置 DEEPSEEK_API_KEY 后再提问。"
        for ch in msg:
            yield sse_event("token", {"token": ch})
        yield sse_event("done", {"answer": msg, "sources": source_items})
        return

    # 3. DeepSeek 流式
    context = "\n\n".join(s["content"] for s in sources)
    full = []
    for chunk in chain._stream_llm(question, context):
        token = chunk.content
        full.append(token)
        yield sse_event("token", {"token": token})
    yield sse_event("done", {"answer": "".join(full), "sources": source_items})
```

**`backend/main.py` 新增路由**:
```python
@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    _ensure_loaded()
    chain = _state.get("chain")
    if chain is None:
        return JSONResponse({"answer": "向量库加载失败", "sources": []}, status_code=503)
    gen = rag_stream_generator(chain, req.question, req.category)
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})
```

**`src/rag/chain.py` 新增 `_stream_llm`**:
```python
def _stream_llm(self, question: str, context: str):
    prompt = get_rag_prompt().format_messages(context=context, question=question)
    for chunk in self._llm.stream(prompt):
        yield chunk
```
`ChatOpenAI` 实例本身支持 `.stream()`,无需改 LLM 初始化。

### 5.6 前端 SSE 客户端(`src/api/sse.ts`)

```typescript
export async function streamAsk(
  question: string,
  category: string | null,
  callbacks: {
    onSources: (sources: SourceItem[]) => void
    onToken: (token: string) => void
    onDone: (answer: string, sources: SourceItem[]) => void
    onError: (msg: string) => void
  },
  signal?: AbortSignal
) {
  const res = await fetch('/api/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, category }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const event = block.match(/^event: (.+)$/m)?.[1] ?? 'message'
      const data = JSON.parse(block.match(/^data: (.+)$/m)?.[1] ?? '{}')
      if (event === 'sources') callbacks.onSources(data.sources)
      else if (event === 'token') callbacks.onToken(data.token)
      else if (event === 'done') callbacks.onDone(data.answer, data.sources)
      else if (event === 'error') callbacks.onError(data.message)
    }
  }
}
```

**取消**:用户切换 category 或离开页面时 `AbortController.abort()`。

### 5.7 板块封面图片

`/categories` 返回 `cover_prompt`,封面图片**在开发阶段一次性生成并提交到 `frontend/react-app/public/covers/{key}.png`**(6 张,人工 review 后入库),运行时前端直接用本地静态文件,不每次调生成接口(避免运行时延迟与额度消耗)。

生成时调用:
```
https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt={URL编码的cover_prompt}&image_size=landscape_16_9
```
每板块封面尺寸 `landscape_16_9`,做"从画面浮出"动画载体。prompt 风格统一(维多利亚英伦 + 神秘学 + 暖色调),保证 6 张图视觉一致。生成脚本放 `scripts/generate_covers.py`,手动运行,产物入 git。

### 5.8 CORS 与 Vite 代理

**后端 CORS**:`backend/main.py` 的 `allow_origins` 增加 `http://localhost:5173`、`http://127.0.0.1:5173`。

**Vite 代理**(`vite.config.ts`):
```typescript
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
      rewrite: (p) => p.replace(/^\/api/, ''),
    },
    '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  },
}
```
前端代码所有请求走 `/api/...`,Vite dev 转发到后端 8000。

### 5.9 错误处理

| 场景 | 后端 | 前端 |
|------|------|------|
| api_key 空 | 流式发降级提示文本 + done | 正常渲染逐字动画 |
| 向量库未加载 | 503 JSON | 聊天区显示"向量库加载中..." |
| Ollama 挂了 | 检索抛异常 → SSE error 事件 | 红色提示"检索失败,检查 Ollama" |
| DeepSeek 限流 | LLM 抛异常 → SSE error | 提示"LLM 暂不可用" |
| 网络断开 | — | fetch reject → 提示 + 重试按钮 |

## 6. 组件状态管理与测试

### 6.1 Zustand Store

**`themeStore.ts`**(持久化):
```typescript
type Theme = 'dark-warm' | 'parchment' | 'mystic-purple'
const ORDER: Theme[] = ['dark-warm', 'parchment', 'mystic-purple']
interface ThemeState {
  theme: Theme
  cycle: () => void
  set: (t: Theme) => void
}
```
`cycle` 在 ORDER 中循环,同时 `document.documentElement.setAttribute('data-theme', next)`。`persist` 中间件存 localStorage(key `r1999-theme`),`onRehydrateStorage` 启动时同步 `<html data-theme>`。

**`uiStore.ts`**(不持久化):
```typescript
interface UIState {
  sidebarOpen: boolean
  topNavVisible: boolean
  currentSection: 'home' | 'data' | 'chat'
  currentCategory: string | null
  categoriesMeta: CategoryMeta[]   // 启动时 /categories 拉取缓存
  toggleSidebar: () => void
  setTopNav: (v: boolean) => void
  setSection: (s: UIState['currentSection']) => void
  setCategory: (c: string | null) => void
  setCategoriesMeta: (m: CategoryMeta[]) => void
}
```

**`chatStore.ts`**(不持久化):
```typescript
interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceItem[]
  streaming?: boolean
}
interface ChatState {
  messages: Message[]
  category: string | null
  sending: boolean
  abortController: AbortController | null
  send: (question: string) => Promise<void>
  abort: () => void
  setCategory: (c: string | null) => void
  clear: () => void
}
```
`send` action:推用户消息 → 创建 AbortController → 调 `streamAsk` → onToken 追加内容到末位 assistant 消息 → onDone 设 streaming=false + sources。

### 6.2 关键 Hook

**`useScrollSpy`**:IntersectionObserver 监听所有 `[data-snap-section]`,可见性 > 0.5 时写 `uiStore.currentSection` / `currentCategory`。

**`useTopNavTrigger`**:顶层 `mousemove`(`y < 8px`)+ `scroll`(`scrollY < 50`)→ `setTopNav(true)`,否则 false。

**`useCategoryData(key)`**:`key` 变化时 fetch `/api/category/{key}/docs?limit=50`,meta 取 uiStore 缓存。

### 6.3 组件树

```
<App>
  <ThemeBootstrap />                    // 启动读 localStorage 同步 data-theme
  useScrollSpy()                        // 全局监听
  useTopNavTrigger()                    // 全局监听
  useEffect: 启动 fetch /api/categories → uiStore.setCategoriesMeta

  <Sidebar />                           // 读 uiStore.sidebarOpen, themeStore
  <TopNav />                            // 读 uiStore.topNavVisible, currentSection
  <main scroll-snap>
    <HomeSection data-snap-section="home" />
    <DataSection data-snap-section="data">
      {categories.map(c => (
        <CategoryPanel key={c.key} data-snap-section={`data:${c.key}`} meta={c} />
      ))}
    </DataSection>
    <ChatSection data-snap-section="chat" />   // 读 chatStore
  </main>
</App>
```

**数据流**:Store 单向数据源,组件只读 store + 派发 action。`/categories` 启动时 App 顶层 fetch 一次缓存,6 CategoryPanel 共享。

### 6.4 测试策略

**后端测试**(`tests/test_sse.py`、`tests/test_categories.py`):
```python
# test_sse.py
@pytest.mark.asyncio
async def test_ask_stream_emits_sources_then_tokens_then_done(tmp_path):
    """事件顺序:sources → N×token → done。用 MockChain 避免 real LLM。"""
    # 断言事件序列与 token 拼接

@pytest.mark.asyncio
async def test_ask_stream_api_key_empty_emits_fallback(tmp_path):
    """api_key 空:逐字发降级提示,done 仍带 sources。"""

# test_categories.py
def test_categories_returns_six_categories_with_doc_count(tmp_path):
    """返回 6 类,key/title/subtitle/description/doc_count/cover_prompt 齐全。"""

def test_category_docs_returns_snippets(tmp_path):
    """/category/人物/docs 返回 name/source/snippet,snippet<=200 字。"""
```
`MockChain` 在 `tests/conftest.py`,需实现:
- `llm_ready()` → 返回 `False`(测降级)或 `True`(测正常流式)
- `_retriever.search(question, category)` → 返回固定 `[{name, category, source, score, content}]` 列表
- `_stream_llm(question, context)` → 返回固定 token 列表的生成器(如 `["6", "是", "一位"]`)

`MockVectorstore` 提供 `_collection.count(where=...)` 返回固定数字(如 105),`similarity_search` 返回固定文档列表。

**前端测试**(Vitest + Testing Library):
```typescript
// themeStore.test.ts
it('cycle 顺序 dark-warm → parchment → mystic-purple → dark-warm', () => {})
it('cycle 后 <html data-theme> 同步', () => {})

// chatStore.test.ts
it('send 推用户消息后流式追加 assistant 消息', async () => {
  mockStreamAsk({ sources: [...], tokens: ['6', '是'] })
  await useChatStore.getState().send('6是谁')
  expect(messages[1].content).toBe('6是')
  expect(messages[1].streaming).toBe(false)
})
it('abort 中断流式,streaming 设 false', async () => {})

// sse.test.ts
it('正确解析跨 chunk 拼接的多事件块', async () => {
  const chunks = ['event: sources\ndata: {...}\n\n', 'event: tok', 'en\ndata: {"token":"6"}\n\n']
  mockFetch(chunks)
  // 断言 tokens === ['6']
})
```

### 6.5 性能与边界

- **流式动画性能**:每字符一个 `<motion.span>` 产生大量 DOM。限制单条消息最长 2000 字符(超长截断 + 提示),React key 复用已渲染字符避免重排
- **scroll-snap 平滑**:`scroll-behavior: smooth` + `scroll-snap-stop: always` 防止快速滚动跳过板块
- **图片懒加载**:板块封面 `<img loading="lazy">`,IntersectionObserver 触发才加载
- **SSE 内存**:后端 async generator,客户端断开时 Starlette 自动取消迭代
- **动画降级**:`prefers-reduced-motion: reduce` 时禁用所有 Framer Motion 动画(`useReducedMotion()` 判断)

## 7. 启动集成改动

**start.ps1 / start.bat 新增段**(在其他前端启动后):
```powershell
# 检测 node_modules
if (-not (Test-Path "frontend\react-app\node_modules")) {
    Write-Host "[step] 首次启动, 安装 React 前端依赖..." -ForegroundColor Yellow
    Push-Location frontend\react-app
    & npm install
    Pop-Location
}
Write-Host "[step] ${delay}s 后启动 React Vite :5173 ..." -ForegroundColor Yellow
Start-Sleep -Seconds $delay
$jobs += Start-Process -PassThru -WindowStyle Minimized -FilePath "npm.cmd" -ArgumentList "--prefix","frontend\react-app","run","dev","--","--host","127.0.0.1","--port","5173","--strictPort"
```

**npm 路径说明**:`npm` 需在 PATH 中(Node.js 安装时默认加入,全局可用,无 conda activate 那样的非交互 shell 问题)。若用户用 nvm,需确保 nvm 已在当前 shell 激活对应 Node 版本。脚本不主动激活 nvm,由用户环境保证。

**README 更新**:
- 三前端地址表加 `| React+Vite | http://localhost:5173 |`
- 环境准备加 Node.js 18+ / npm 要求
- 手动分步运行加 `cd frontend\react-app && npm install && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`

## 8. 验收标准

1. `start.ps1` 启动后 4 端口可访问(8000/8501/7860/5173)
2. 首页视频占位背景显示,标题渐变浮现
3. 鼠标贴顶端 → TopNav 滑入;移开 → 滑出
4. 点左上角 ☰ → Sidebar 覆盖滑入;点遮罩 → 滑出;Sidebar z-index 高于 TopNav
5. Sidebar 主题切换循环 3 套,localStorage 持久化,刷新后保留
6. 滚动首页 → 资料 → 问答,snap 流畅
7. 6 板块逐个进场,标题(t=0)/描述(t=300ms,18ms/字)/图片(t=500ms)动画时序正确
8. 第 6 板块再下滑 → 问答页
9. 问答页发消息 → 用户消息弹出动画(scale 1.3→1)+ LLM 流式逐字(40ms/字,每字 scale 0.5→1)
10. category 下拉切换后重新提问,过滤生效
11. 中途离开页面 → 流式中断无残留
12. api_key 空 → 流式发降级提示
13. 三套主题切换不破坏布局
14. 后端测试:test_sse / test_categories 全过
15. 前端测试:themeStore / chatStore / sse 全过

## 9. 非目标(YAGNI)

- 用户登录、多用户会话持久化
- 视频真实下载(用户后续手动放 mp4)
- 下载按钮真实跳转(占位 toast)
- 移动端响应式适配(本次桌面优先)
- 生产构建与 FastAPI 托管 dist(本次 dev 模式)
- 英文 i18n
- 其他引用网站(仅官网,后续可加)

## 10. 依赖清单

**前端**(`frontend/react-app/package.json`):
- react@^18.3, react-dom@^18.3
- vite@^5.4, @vitejs/plugin-react@^4.3
- typescript@^5.5
- framer-motion@^11
- zustand@^4.5
- vitest@^2, @testing-library/react@^16, jsdom(测试)

**后端**(无新增,复用现有 starlette/fastapi):
- starlette(已随 fastapi 安装,提供 StreamingResponse)

**系统**:
- Node.js 18+ / npm
