"""Streamlit 前端, 调用 FastAPI 后端。端口 8501。"""
from __future__ import annotations

import sys
from pathlib import Path

import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.config import get_config

cfg = get_config()
BACKEND = f"http://localhost:{cfg.server.backend_port}"

st.set_page_config(page_title="1999Search", page_icon="✦", layout="wide")

# 主题色注入
st.markdown("""
<style>
.stApp { background: linear-gradient(160deg, #14101f, #221a35); }
.stApp, .stApp * { color: #e8e2f5; }
[data-testid="stChatMessage"] { border-radius: 14px; border: 1px solid #3a2f55; }
.stButton>button { background: linear-gradient(135deg,#d4af37,#b8941f); color:#1a1430; font-weight:700; }
.stSelectbox label, .stSlider label { color: #d4af37; }
</style>
""", unsafe_allow_html=True)

st.title("✦ 1999Search")
st.caption("Reverse: 1999 知识库 RAG 助手 · Streamlit 前端")

# 侧边栏
with st.sidebar:
    st.header("设置")
    backend_url = st.text_input("后端地址", value=BACKEND)
    category = st.selectbox("分类筛选", ["", "人物", "心相", "剧情", "世界", "阵营", "日历"],
                            format_func=lambda x: "全部" if x == "" else x)
    try:
        h = requests.get(f"{backend_url}/health", timeout=3).json()
        st.success(f"后端就绪 · 文档块 {h.get('doc_count',0)}")
        st.caption(f"LLM: {'已配置' if h.get('llm_ready') else '未配置 key'}")
    except Exception as e:
        st.error(f"后端未连接: {e}")

# 聊天
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("sources"):
            with st.expander(f"来源引用 ({len(m['sources'])})"):
                for s in m["sources"]:
                    st.markdown(f"**{s['name']}** · `{s['category']}` · 相关度 {s['score']:.3f}")

if q := st.chat_input("问问关于角色、心相、剧情的问题…"):
    st.session_state.messages.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        with st.spinner("思考中…"):
            try:
                r = requests.post(f"{backend_url}/ask",
                                  json={"question": q, "category": category or None}, timeout=60).json()
                st.markdown(r["answer"])
                if r.get("sources"):
                    with st.expander(f"来源引用 ({len(r['sources'])})"):
                        for s in r["sources"]:
                            st.markdown(f"**{s['name']}** · `{s['category']}` · 相关度 {s['score']:.3f}")
                st.session_state.messages.append({"role": "assistant", "content": r["answer"], "sources": r.get("sources", [])})
            except Exception as e:
                st.error(f"请求失败: {e}")
