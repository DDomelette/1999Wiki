"""Source-neutral Markdown normalization for display snippets."""
from __future__ import annotations

import re


def clean_markdown(text: str) -> str:
    if not text:
        return ""

    # 1. 图片嵌入: ![[x.png]] 和 ![alt](url)
    text = re.sub(r"!\[\[[^\]]*\]\]", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)

    # 2. wikilink: [[a|b]] -> b ; [[a]] -> a
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)

    # 3. callout 标记行: > [!type]+/- 标题  (整行删除, 保留其后以 > 开头的内容行)
    text = re.sub(r"^>\s*\[![^\]]*\][+-]?.*$", "", text, flags=re.MULTILINE)
    # 去掉引用块行首的 "> " (保留内容)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

    # 4. 脚注定义块: 单独一行的 [^id]: xxx (必须先于引用标记处理, 否则 [^id] 被删后定义行残缺)
    text = re.sub(r"^\[\^[^\]]+\]:.*$", "", text, flags=re.MULTILINE)
    # 脚注引用标记 [^id]
    text = re.sub(r"\[\^[^\]]+\]", "", text)

    # 5. HTML 标签 (保留标签内文本)
    text = re.sub(r"<[^>]+>", "", text)

    # 6. 折叠 3+ 连续换行为 2 个
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 去除每行尾部空白
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()
