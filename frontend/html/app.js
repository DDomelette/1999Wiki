const messagesEl = document.getElementById('messages');
const formEl = document.getElementById('form');
const questionEl = document.getElementById('question');
const categoryEl = document.getElementById('category');
const statusEl = document.getElementById('status');

async function checkHealth() {
  try {
    const r = await fetch('/health');
    const d = await r.json();
    if (d.status === 'ok') {
      statusEl.textContent = `● 已就绪 · 文档块 ${d.doc_count} · LLM ${d.llm_ready ? '已配置' : '未配置 key'}`;
      statusEl.style.color = d.llm_ready ? '#7ee787' : '#d4af37';
    } else {
      statusEl.textContent = '● 向量库未就绪';
      statusEl.style.color = '#ff6b6b';
    }
  } catch (e) {
    statusEl.textContent = '● 后端未连接';
    statusEl.style.color = '#ff6b6b';
  }
}
checkHealth();

function addMsg(role, html) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.innerHTML = html;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

formEl.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = questionEl.value.trim();
  if (!q) return;
  addMsg('user', escapeHtml(q));
  questionEl.value = '';
  const typing = addMsg('bot', '<span class="typing">思考中…</span>');
  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, category: categoryEl.value || null }),
    });
    const data = await res.json();
    let html = `<div class="answer">${escapeHtml(data.answer)}</div>`;
    if (data.sources && data.sources.length) {
      const items = data.sources.map(s =>
        `<div class="source-item"><span class="name">${escapeHtml(s.name)}</span><span class="cat">${escapeHtml(s.category)}</span> · 相关度 ${s.score.toFixed(3)}</div>`
      ).join('');
      html += `<details class="sources"><summary>来源引用 (${data.sources.length})</summary><div class="source-list">${items}</div></details>`;
    }
    typing.innerHTML = html;
  } catch (err) {
    typing.innerHTML = `<div class="answer" style="color:#ff6b6b">请求失败: ${escapeHtml(String(err))}</div>`;
  }
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
