"""Export the characters used by frontend source and dynamic Wiki content.

Run from a configured project root. The database access is read-only.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pymysql

from config.config import get_config


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "react-app"
CORPUS = FRONTEND / "font-corpus.txt"
SOURCE_SUFFIXES = {".css", ".html", ".ts", ".tsx"}
WIKI_TEXT_QUERIES = (
    "SELECT title, subtitle, category, source_title, content_json FROM wiki_pages",
    "SELECT alias FROM wiki_aliases",
    "SELECT label FROM wiki_categories",
    "SELECT label FROM wiki_relations",
    "SELECT text FROM wiki_link_spans",
    "SELECT title FROM wiki_media_links",
    "SELECT title FROM wiki_media_bindings",
)


def frontend_text() -> str:
    paths = [FRONTEND / "index.html"]
    paths.extend(path for path in (FRONTEND / "src").rglob("*") if path.suffix in SOURCE_SUFFIXES)
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def wiki_text() -> str:
    cfg = get_config().mysql
    chunks: list[str] = []
    with pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        charset=cfg.charset,
        cursorclass=pymysql.cursors.DictCursor,
    ) as conn:
        with conn.cursor() as cur:
            for query in WIKI_TEXT_QUERIES:
                cur.execute(query)
                chunks.extend(
                    json.dumps(row, ensure_ascii=False, default=str)
                    for row in cur.fetchall()
                )
    return "\n".join(chunks)


def main() -> None:
    characters = set(frontend_text() + wiki_text())
    characters = {
        char for char in characters
        if char == " " or (not char.isspace() and not unicodedata.category(char).startswith("C"))
    }
    CORPUS.write_text("".join(sorted(characters)) + "\n", encoding="utf-8")
    print(f"Wrote {len(characters)} characters to {CORPUS}")


if __name__ == "__main__":
    main()
