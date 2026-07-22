import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.text_cleaner import clean_markdown
from src.huiji_rag.text import clean_huiji_text, compact_lines, short_summary


def test_removes_image_embeds():
    text = "前\n![[立绘 6 02.png]]\n![alt](path/img.png)\n后"
    out = clean_markdown(text)
    assert "![" not in out
    assert "前" in out and "后" in out


def test_unwraps_wikilinks():
    assert clean_markdown("[[维尔汀]]") == "维尔汀"
    assert clean_markdown("[[维尔汀|司辰]]") == "司辰"


def test_strips_callout_marker_keeps_content():
    text = "> [!overview]+ 概述\n> - 时代:: 八十年代\n> - 诞生:: 2月"
    out = clean_markdown(text)
    assert "[!" not in out
    assert "概述" not in out  # 标题行被移除
    assert "八十年代" in out
    assert "2月" in out


def test_removes_footnote_refs_and_defs():
    text = "效果[^1]。\n\n[^1]: 这是脚注内容。"
    out = clean_markdown(text)
    assert "[^1]" not in out
    assert "这是脚注内容" not in out
    assert "效果" in out


def test_strips_html_tags_keeps_text():
    text = '<b><font color="#7B5E91">减益</font></b>效果'
    out = clean_markdown(text)
    assert "<" not in out
    assert "减益" in out
    assert "效果" in out


def test_collapses_blank_lines():
    text = "a\n\n\n\nb"
    out = clean_markdown(text)
    assert "\n\n\n" not in out


def test_clean_huiji_text_removes_html_and_keeps_display_text():
    raw = "<span class='x'>Sonetto</span><br/>Foundation member&nbsp;[[Sonetto]]"
    assert clean_huiji_text(raw) == "Sonetto\nFoundation member Sonetto"


def test_compact_lines_removes_empty_lines_without_merging_bullets():
    raw = "Identity: Foundation member\n\n\n- Skill: Commandment V\n\n"
    assert compact_lines(raw) == "Identity: Foundation member\n- Skill: Commandment V"


def test_short_summary_preserves_sentence_boundary():
    text = "First sentence. Second sentence. Third sentence."
    assert short_summary(text, max_chars=8) == "First sentence."
