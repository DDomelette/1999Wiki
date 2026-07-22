// 槲寄生（Druvis III）档案数据 —— 内容复刻自 Stitch 设计稿
// 媒体一律经由 src/media/contract.js 契约层获取，本文件不持有任何图片路径

export const PROFILE_ROWS = [
  { label: 'Medium:', value: '树木 (Trees)' },
  { label: 'Damage Type:', value: '精神创伤 (Mental)' },
  { label: 'Birthday:', value: '10-23 (Autumn)' },
  { label: 'Tags:', value: '输出 / 控制 / 辅助' },
]

export const PROFILE_QUOTE =
  '漫游于林间的术杖制造师，橡树与月亮的友人，你最沉静的朋友之一。'

export const SKILLS = [
  {
    variant: 'wind',
    name: '风入林 (Wind into Woods)',
    tag: 'ATTACK',
    ultimate: false,
    desc: '单体攻击，造成200%精神创伤，使其陷入[石化]状态。',
  },
  {
    variant: 'dew',
    name: '露渐白 (Early Dew)',
    tag: 'ATTACK',
    ultimate: false,
    desc: '群体攻击，对2名敌方造成120%精神创伤；穿透率提升30%。',
  },
  {
    variant: 'ultimate',
    name: '林间，静默将至',
    tag: 'ULTIMATE',
    ultimate: true,
    desc: '群体攻击，对敌方全体造成400%精神创伤；主目标[石化]1回合。',
  },
]

export const CULTURE_ENTRIES = [
  {
    title: '咆哮的1920年代 | Roaring Twenties',
    body: '20世纪20年代，立体派艺术蓬勃兴起。强调几何特征的风潮不仅影响了克莱斯勒大厦，也改变了女性的时尚风格。全新的剪裁设计，正揭示着一场不协调的碰撞变革——现代化。',
  },
  {
    title: '喀斯卡特的秋天 | Autumn in Cascade',
    body: '她记得喀斯卡特山脉里的每一棵树木。苔藓的形状、生长轮的不规则、蚁窝的规模，每一棵树都是那么的不同。为了倾听它们的诉语，她多次背离母亲的期待，逃过一切没有结尾的宴会，只身闯入森林的长夜。',
  },
]

export const INHERITANCE_LEVELS = [
  {
    level: 'I',
    active: true,
    parts: [
      { text: '当自身处于' },
      { text: '[属性提升]', accent: true },
      { text: ' ' },
      { text: '[状态增益]', accent: true },
      { text: '时，造成的伤害提升' },
      { text: '20%', accent: true, bold: true },
    ],
  },
  {
    level: 'II',
    active: false,
    parts: [
      { text: '进入战斗时，造成伤害提升' },
      { text: '8%', accent: true, bold: true },
    ],
  },
  {
    level: 'III',
    active: false,
    parts: [
      { text: '进入战斗时，己方' },
      { text: '[木]灵感', accent: true },
      { text: '角色进入' },
      { text: '[生生不息]', accent: true, bold: true },
      { text: '状态（最多触发1次）' },
    ],
  },
]

export const SHAPING_LEVELS = [
  { lv: 'LV.1', text: '【风入林】在咒语2/3阶时，造成的精神创伤提升至300/400%' },
  { lv: 'LV.2', text: '【林间，静默将至】造成的精神创伤提升至450%' },
  { lv: 'LV.3', text: '【露渐白】在咒语1/2/3阶时，造成的精神创伤提升至135/200/325%' },
  { lv: 'LV.4', text: '【林间，静默将至】造成的精神创伤提升至500%' },
  { lv: 'LV.5', text: '【露渐白】穿透率提升的效果变为40%' },
]

export const VOICE_RECORDS = [
  {
    title: '初遇 | First Meeting',
    zh: '“我是槲寄生，很高兴认识你。…… 你说看不出我很高兴？呵…… 那么现在呢？”',
    en: "I am Druvis III. It's my pleasure to meet you…. You said I didn't look very pleased? Hah … How about now?",
  },
  {
    title: '箱中气候 | Climate in the Case',
    zh: '“水从泥土里去往天上，又从天上坠落地面。如同我从林中来，又向林中去。”',
    en: 'Water travels from the ground to the sky, and then falls back; just as I, who come from the forest, and now go back.',
  },
  {
    title: '朝晨 | Morning',
    zh: '“太阳升起，野兽们噤声不吠。而后，我听见第一只离林之鸟振翅的声响。”',
    en: "When the sun rose, the beasts kept silence. Then, I heard a bird flapping its wings. It's the first to leave the forest.",
  },
  {
    title: '致未来 | To the Future',
    zh: '“或许，在工业之梦结束的那日。没有人再会伐尽茂密的林海。我期待着那一天。”',
    en: 'Perhaps when the dream of industrial society is realized,no one will ever cut down the dense forest. I am looking forward to that day.',
  },
  {
    title: '孑立 | Standing Alone',
    zh: '“…… 您也在聆听窗外树梢间的风声吗？…”',
    en: 'Are you also listening to the wind dancing on the treetops?',
  },
  {
    title: '问候 | Greetings',
    zh: '“你带来了一缕原野的风。”',
    en: 'You brought me a gentle breeze on the field.',
  },
  {
    title: '入队 | Join Team',
    zh: '“一同去往草木生长之地。”',
    en: "Let's go where trees and grass grow.",
  },
]
