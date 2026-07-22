"""一次性生成 6 板块封面图片到 frontend/react-app/public/covers/。

手动运行:
    conda run -n langchain python scripts/generate_covers.py

依赖:requests(已在 langchain 环境中)
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from backend.categories_meta import CATEGORIES_META

OUT_DIR = ROOT / "frontend" / "react-app" / "public" / "covers"
API_URL = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image"


def generate_one(prompt: str, out_path: Path) -> None:
    params = {
        "prompt": prompt,
        "image_size": "landscape_16_9",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    print(f"[cover] 生成: {out_path.name}  prompt={prompt[:30]}...")
    resp = requests.get(url, timeout=120)
    if resp.status_code != 200:
        print(f"[cover] 错误 {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        return
    out_path.write_bytes(resp.content)
    print(f"[cover] 完成: {out_path}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for meta in CATEGORIES_META:
        out = OUT_DIR / f"{meta['key']}.png"
        if out.exists():
            print(f"[cover] 已存在,跳过: {out.name}")
            continue
        generate_one(meta["cover_prompt"], out)
    print("[cover] 全部完成")


if __name__ == "__main__":
    main()
