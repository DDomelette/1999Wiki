"""6 板块元数据静态定义(标题/简介/封面 prompt)。doc_count 运行时从向量库取。"""
from __future__ import annotations

CATEGORIES_META: list[dict] = [
    {
        "key": "人物",
        "title": "人物",
        "subtitle": "Characters",
        "description": "重返未来:1999 中的角色档案,含 UTTU 人物、神秘学家、维拉等阵营的英伦角色",
        "cover_prompt": "维多利亚时代英伦人物肖像,神秘学符号点缀,暖色调,复古油画质感",
    },
    {
        "key": "心相",
        "title": "心相",
        "subtitle": "Psychube",
        "description": "角色的精神具象武器,赋予能力与故事,每件心相都承载着神秘学家的记忆",
        "cover_prompt": "神秘学心相武器,发光符文,维多利亚装饰,暖金色调,复古插画",
    },
    {
        "key": "剧情",
        "title": "剧情",
        "subtitle": "Story",
        "description": "重返未来:1999 的主线与支线剧情,跨越不同时代的神秘学事件",
        "cover_prompt": "英伦雾都街景,神秘学事件场景,复古暖色调,油画质感",
    },
    {
        "key": "世界",
        "title": "世界",
        "subtitle": "World",
        "description": "游戏世界观设定,神秘学、暴雨、时代变迁的背景知识",
        "cover_prompt": "世界地图,维多利亚风格,神秘学符号,暖色复古",
    },
    {
        "key": "阵营",
        "title": "阵营",
        "subtitle": "Factions",
        "description": "游戏中的各大阵营组织,从基金会到神秘学家族",
        "cover_prompt": "阵营徽章,维多利亚纹章风格,金紫色,复古",
    },
    {
        "key": "日历",
        "title": "日历",
        "subtitle": "Calendar",
        "description": "箱中日历,每日一段神秘学见闻,记录圣保罗洛夫顿等地的奇闻",
        "cover_prompt": "复古日历,维多利亚装饰,神秘学符号,暖色调",
    },
]
