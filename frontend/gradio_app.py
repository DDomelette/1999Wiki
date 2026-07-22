"""Gradio 前端, 调用 FastAPI 后端。端口 7860。"""
from __future__ import annotations

import sys
from pathlib import Path

import gradio as gr
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.config import get_config

cfg = get_config()
BACKEND = f"http://localhost:{cfg.server.backend_port}"

theme = gr.themes.Base(
    primary_hue="amber",
    secondary_hue="purple",
    neutral_hue="slate",
    font=[
        gr.themes.Font("PingFang SC"),
        gr.themes.Font("Microsoft YaHei"),
        gr.themes.Font("Segoe UI"),
        gr.themes.Font("sans-serif"),
    ],
).set(
    body_background_fill="#14101f",
    body_text_color="#e8e2f5",
    block_background_fill="#1f1830",
    block_border_color="#3a2f55",
    button_primary_background_fill="linear-gradient(135deg,#d4af37,#b8941f)",
    button_primary_text_color="#1a1430",
)


def ask(question: str, category: str, history: list):
    cat = category if category != "全部" else None
    try:
        r = requests.post(f"{BACKEND}/ask",
                          json={"question": question, "category": cat}, timeout=60).json()
        answer = r["answer"]
        if r.get("sources"):
            answer += "\n\n---\n**来源引用:**\n" + "\n".join(
                f"- **{s['name']}** · `{s['category']}` · {s['score']:.3f}" for s in r["sources"]
            )
    except Exception as e:
        answer = f"请求失败: {e}"
    history = history + [(question, answer)]
    return history, history


def health_info():
    try:
        h = requests.get(f"{BACKEND}/health", timeout=3).json()
        return f"● 后端就绪 · 文档块 {h.get('doc_count',0)} · LLM {'就绪' if h.get('llm_ready') else '未配置 key'}"
    except Exception as e:
        return f"● 后端未连接: {e}"


with gr.Blocks(theme=theme, title="1999Search") as demo:
    gr.Markdown("# ✦ 1999Search\nReverse: 1999 知识库 RAG 助手 · Gradio 前端")
    gr.Markdown(health_info())
    with gr.Row():
        category = gr.Dropdown(["全部", "人物", "心相", "剧情", "世界", "阵营", "日历"],
                               value="全部", label="分类筛选")
    chatbot = gr.Chatbot(height=520)
    with gr.Row():
        question = gr.Textbox(placeholder="问问关于角色、心相、剧情的问题…", scale=9, label="问题")
        send = gr.Button("发送", scale=1, variant="primary")
    clear = gr.Button("清空对话")
    send.click(ask, [question, category, chatbot], [chatbot, chatbot]).then(lambda: "", None, question)
    question.submit(ask, [question, category, chatbot], [chatbot, chatbot]).then(lambda: "", None, question)
    clear.click(lambda: None, None, chatbot)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=cfg.server.gradio_port)
