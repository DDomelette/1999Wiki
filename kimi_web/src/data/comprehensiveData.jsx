// Comprehensive Archival Profile（移动端长页）数据 —— 复刻自 Stitch 设计稿
// 媒体一律经由 src/media/contract.js 契约层获取，本文件不持有任何图片路径

export const COMP_LORE_FIELDS = [
  { label: 'Active Era', value: '20th Century Early' },
  { label: 'Birthday', value: 'Oct 23 (Autumn)' },
  { label: 'Medium', value: 'Trees / 树木' },
  { label: 'Udimo', value: 'Black Cat / 猫类' },
]

export const COMP_SCENTS = ['Woody', 'Cedar', 'Amber']

export const COMP_INHERITANCE = [
  {
    lvl: 'I', active: false,
    html: <>当自身处于<span className="text-primary">[属性提升]</span> <span className="text-primary">[状态增益]</span>时，造成的伤害提升<span className="text-primary font-bold">20%</span></>,
  },
  {
    lvl: 'II', active: false,
    html: <>进入战斗时，造成伤害提升<span className="text-primary font-bold">8%</span></>,
  },
  {
    lvl: 'III', active: true,
    html: <>进入战斗时，己方<i className="text-primary">[木]灵感</i>角色进入<span className="text-primary font-bold">[生生不息]</span>状态（最多触发1次）</>,
  },
]

export const COMP_SKILLS = [
  {
    tag: 'SINGLE_ATK', variant: 'wind', name: '风入林', nameEn: 'Wind into Woods',
    desc: <>单体攻击，造成<span className="text-primary">200%</span>精神创伤。高阶状态下使其陷入<span className="text-primary">[石化]</span>状态。</>,
    quote: '风在驱逐林中异客。',
  },
  {
    tag: 'MASS_ATK', variant: 'dew', name: '露渐白', nameEn: 'Early Dew',
    desc: <>群体攻击，对2名敌方造成<span className="text-primary">120%</span>精神创伤；穿透率提升<span className="text-primary">30%</span>。</>,
    quote: '白露与湿苔根植于此。',
  },
]

export const COMP_VOICES = [
  {
    title: '初遇 // First Meeting',
    zh: '我是槲寄生，很高兴认识你。…… 你说看不出我很高兴？呵…… 那么现在呢？',
    en: "I am Druvis III. It's my pleasure to meet you…. You said I didn't look very pleased? Hah … How about now?",
  },
  {
    title: '箱中气候 // Climate in the Case',
    zh: '水从泥土里去往天上，又从天上坠落地面。如同我从林中来，又向林中去。',
    en: 'Water travels from the ground to the sky, and then falls back; just as I, who come from the forest, and now go back.',
  },
  {
    title: '朝晨 // Morning',
    zh: '太阳升起，野兽们噤声不吠。而后，我听见第一只离林之鸟振翅的声响。',
    en: "When the sun rose, the beasts kept silence. Then, I heard a bird flapping its wings. It's the first to leave the forest.",
  },
  {
    title: '孑立 // Standing Alone',
    zh: '…… 您也在聆听窗外树梢间的风声吗？…',
    en: 'Are you also listening to the wind dancing on the treetops?',
  },
]

export const COMP_CULTURE = [
  {
    title: '咆哮的1920年代', titleEn: 'Roaring Twenties', rotate: '-1deg', accent: false,
    paragraphs: [
      '20世纪20年代，立体派艺术蓬勃兴起。强调几何特征的风潮不仅影响了克莱斯勒大厦，也改变了女性的时尚风格。全新的剪裁设计，正揭示着一场不协调的碰撞变革——现代化。在美国，现代科学正在化一切为可能。',
      '蒸汽火车、福特汽车、无线电的使用，将世界推向乐观浪潮的更远处。爵士乐响彻通宵，人们在查尔斯顿舞步中奔赴下一场永不结束的宴会。没有人能拒绝加入这场狂欢，特别是某些艰辛跻身于美国的没落贵族。',
    ],
    quote: '“不要再跟我谈起你的幻觉。”一位母亲将绘着橡树的家谱图轻轻推进壁炉，“从登船的那天起，你已是一位荣耀的美国人。”',
  },
  {
    title: '喀斯卡特的秋天', titleEn: 'Autumn in Cascade', rotate: '1deg', accent: false, indent: true,
    paragraphs: [
      '她记得喀斯卡特山脉里的每一棵树木。苔藓的形状、生长轮的不规则、蚁窝的规模，每一棵树都是那么的不同。为了倾听它们的诉语，她多次背离母亲的期待，逃过一切没有结尾的宴会，只身闯入森林的长夜。',
      '直到1928年的那一天。木材供应崩溃，他猛然陷入一场旷日持久的沉默。大萧条就像一场最时兴的宴会，曾经的新贵无人能够缺席。推平森林、变卖土地似乎成了唯一选择。',
    ],
  },
]

export const COMP_DIALOGUE = [
  { who: '白雪松', text: '你是如何理解“美国梦”的？', self: false },
  { who: '槲寄生', text: '我不理解。', self: true },
  { who: '白雪松', text: '如果用一个词语来形容它呢？', self: false },
  { who: '槲寄生', text: '也是一门生意。', self: true },
  { who: '白雪松', text: '“美国梦”是焰火纷呈。', self: false },
  { who: '槲寄生', text: '“美国梦”是遍地灰烬。', self: true },
]

export const COMP_COLLECTION = [
  { id: 'ITEM_01', name: 'Acorn Choker', meta: 'Value: High', variant: 'item-1' },
  { id: 'ITEM_02', name: 'Mistletoe Staff', meta: 'Source: Forest', variant: 'item-2' },
  { id: 'ITEM_03', name: 'Mistletoe Bouquet', meta: 'Value: Sacred', variant: 'item-3' },
  { id: 'ITEM_04', name: 'Golden Branch', meta: 'Value: Rare', variant: 'item-4' },
  { id: 'ITEM_05', name: 'Pearl Ornament', meta: 'Source: Legacy', variant: 'item-5' },
  { id: 'ITEM_06', name: 'Silk Ribbon', meta: 'Value: Sentimental', variant: 'item-6' },
]
