import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import anthropic

app = FastAPI()

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("MODEL", "claude-sonnet-4-6")
SKILL_PATH = os.environ.get("SKILL_PATH", "SKILL.md")

# In-memory session store {session_id: [messages]}
sessions: dict = {}


def load_system_prompt(path: str = SKILL_PATH) -> str:
    """Load system prompt from SKILL.md, stripping YAML frontmatter if present."""
    content = Path(path).read_text(encoding="utf-8")
    if content.startswith("---"):
        parts = content.split("---", 2)
        return parts[2].strip() if len(parts) >= 3 else content.strip()
    return content.strip()


SYSTEM_PROMPT = load_system_prompt()


# ---------------------------------------------------------------------------
# Admin: reload system prompt from disk without full restart
# ---------------------------------------------------------------------------
class ReloadRequest(BaseModel):
    password: str


@app.post("/admin/reload")
async def reload_prompt(req: ReloadRequest):
    """Reload SKILL.md from disk. Useful after updating the skill file on the server."""
    global SYSTEM_PROMPT
    if not APP_PASSWORD or req.password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    SYSTEM_PROMPT = load_system_prompt()
    return {"status": "reloaded", "prompt_length": len(SYSTEM_PROMPT)}


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CruxPath — Diagnostic Analyst</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #0d0f14;
    color: #e2e4e9;
    height: 100dvh;
    display: flex;
    flex-direction: column;
  }

  /* --- PASSWORD GATE --- */
  #gate {
    position: fixed; inset: 0;
    background: #0d0f14;
    display: flex; align-items: center; justify-content: center;
    z-index: 100;
  }
  #gate.hidden { display: none; }
  .gate-card {
    width: 100%; max-width: 380px;
    padding: 40px 36px;
    background: #13161e;
    border: 1px solid #1e2230;
    border-radius: 12px;
  }
  .gate-logo {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #5b6378;
    margin-bottom: 28px;
  }
  .gate-title {
    font-size: 20px;
    font-weight: 600;
    color: #e2e4e9;
    margin-bottom: 8px;
  }
  .gate-sub {
    font-size: 14px;
    color: #5b6378;
    margin-bottom: 32px;
    line-height: 1.5;
  }
  .gate-card input[type="password"] {
    width: 100%;
    padding: 12px 14px;
    background: #0d0f14;
    border: 1px solid #1e2230;
    border-radius: 8px;
    color: #e2e4e9;
    font-size: 15px;
    outline: none;
    margin-bottom: 12px;
    transition: border-color 0.15s;
  }
  .gate-card input[type="password"]:focus { border-color: #3d4663; }
  .gate-card button {
    width: 100%;
    padding: 12px;
    background: #2a3350;
    border: none;
    border-radius: 8px;
    color: #c8d0e8;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
  }
  .gate-card button:hover { background: #334068; }
  .gate-error {
    font-size: 13px;
    color: #e05757;
    margin-top: 10px;
    min-height: 18px;
  }

  /* --- APP SHELL --- */
  #app { display: flex; flex-direction: column; height: 100dvh; }

  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 24px;
    border-bottom: 1px solid #1a1d27;
    flex-shrink: 0;
  }
  .header-left { display: flex; align-items: center; gap: 12px; }
  .logo-mark {
    width: 28px; height: 28px;
    background: #2a3350;
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700; color: #8899cc;
    letter-spacing: -0.02em;
  }
  .header-title { font-size: 15px; font-weight: 600; color: #c8d0e8; }
  .header-sub { font-size: 12px; color: #3d4663; margin-top: 1px; }
  .new-btn {
    padding: 7px 14px;
    background: transparent;
    border: 1px solid #1e2230;
    border-radius: 7px;
    color: #5b6378;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .new-btn:hover { border-color: #3d4663; color: #8899cc; }

  /* --- MESSAGES --- */
  #messages {
    flex: 1;
    overflow-y: auto;
    padding: 32px 0;
    scroll-behavior: smooth;
  }
  #messages::-webkit-scrollbar { width: 4px; }
  #messages::-webkit-scrollbar-track { background: transparent; }
  #messages::-webkit-scrollbar-thumb { background: #1e2230; border-radius: 2px; }

  .msg-row {
    max-width: 740px;
    margin: 0 auto 24px;
    padding: 0 24px;
    display: flex;
    gap: 14px;
    align-items: flex-start;
  }
  .msg-avatar {
    width: 28px; height: 28px;
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700;
    flex-shrink: 0;
    margin-top: 2px;
  }
  .msg-avatar.agent { background: #2a3350; color: #8899cc; }
  .msg-avatar.user  { background: #1a2a1a; color: #6a9e6a; }

  .msg-content { flex: 1; min-width: 0; }
  .msg-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .msg-label.agent { color: #3d4663; }
  .msg-label.user  { color: #3a5a3a; }

  .msg-body { font-size: 15px; line-height: 1.65; color: #c8d0e8; }
  .msg-body.user-body { color: #a8c0a8; }

  /* Markdown rendering */
  .msg-body p { margin-bottom: 12px; }
  .msg-body p:last-child { margin-bottom: 0; }
  .msg-body strong { color: #e2e4e9; font-weight: 600; }
  .msg-body em { color: #9aaccc; font-style: italic; }
  .msg-body ul, .msg-body ol { margin: 8px 0 12px 20px; }
  .msg-body li { margin-bottom: 4px; }
  .msg-body h3 { font-size: 14px; font-weight: 600; color: #8899cc; margin: 16px 0 6px; text-transform: uppercase; letter-spacing: 0.05em; }
  .msg-body h4 { font-size: 14px; font-weight: 600; color: #c8d0e8; margin: 12px 0 4px; }
  .msg-body code { background: #1a1d27; padding: 2px 6px; border-radius: 4px; font-size: 13px; color: #8899cc; }
  .msg-body hr { border: none; border-top: 1px solid #1a1d27; margin: 16px 0; }

  /* Typing indicator */
  .typing { display: flex; gap: 4px; align-items: center; padding: 4px 0; }
  .typing span {
    width: 6px; height: 6px;
    background: #3d4663;
    border-radius: 50%;
    animation: bounce 1.2s ease-in-out infinite;
  }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-6px); }
  }

  /* --- EMPTY STATE --- */
  #empty {
    max-width: 740px; margin: auto;
    padding: 48px 24px;
    text-align: center;
  }
  .empty-icon {
    width: 44px; height: 44px;
    background: #13161e;
    border: 1px solid #1e2230;
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
    margin: 0 auto 20px;
  }
  .empty-title { font-size: 17px; font-weight: 600; color: #c8d0e8; margin-bottom: 8px; }
  .empty-sub { font-size: 14px; color: #3d4663; line-height: 1.6; max-width: 380px; margin: 0 auto; }

  /* --- INPUT --- */
  .input-area {
    padding: 16px 24px 24px;
    border-top: 1px solid #1a1d27;
    flex-shrink: 0;
  }
  .input-wrap {
    max-width: 740px;
    margin: 0 auto;
    position: relative;
  }
  textarea {
    width: 100%;
    padding: 14px 52px 14px 16px;
    background: #13161e;
    border: 1px solid #1e2230;
    border-radius: 10px;
    color: #e2e4e9;
    font-size: 15px;
    font-family: inherit;
    line-height: 1.5;
    resize: none;
    outline: none;
    transition: border-color 0.15s;
    max-height: 200px;
    overflow-y: auto;
  }
  textarea:focus { border-color: #2a3350; }
  textarea::placeholder { color: #2d3347; }
  .send-btn {
    position: absolute;
    right: 10px; bottom: 10px;
    width: 32px; height: 32px;
    background: #2a3350;
    border: none;
    border-radius: 7px;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.15s;
    color: #8899cc;
  }
  .send-btn:hover:not(:disabled) { background: #334068; }
  .send-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .input-hint {
    font-size: 12px;
    color: #2d3347;
    text-align: center;
    margin-top: 10px;
  }
</style>
</head>
<body>

<!-- Password gate -->
<div id="gate">
  <div class="gate-card">
    <div class="gate-logo">CruxPath</div>
    <div class="gate-title">Diagnostic Analyst</div>
    <div class="gate-sub">Enter the access password to begin a diagnostic session.</div>
    <input type="password" id="pw-input" placeholder="Password" autocomplete="current-password" />
    <button onclick="unlock()">Enter</button>
    <div class="gate-error" id="gate-error"></div>
  </div>
</div>

<!-- Main app -->
<div id="app">
  <header>
    <div class="header-left">
      <div class="logo-mark">CP</div>
      <div>
        <div class="header-title">Diagnostic Analyst</div>
        <div class="header-sub">CruxPath · Evaluation</div>
      </div>
    </div>
    <button class="new-btn" onclick="newSession()">New session</button>
  </header>

  <div id="messages">
    <div id="empty">
      <div class="empty-icon">⬡</div>
      <div class="empty-title">Describe the problem</div>
      <div class="empty-sub">State the challenge, symptom, or situation you want to diagnose. Be as honest as you can — uncertainty is useful data.</div>
    </div>
  </div>

  <div class="input-area">
    <div class="input-wrap">
      <textarea
        id="input"
        rows="1"
        placeholder="Describe the problem..."
        onkeydown="handleKey(event)"
        oninput="autoResize(this)"
      ></textarea>
      <button class="send-btn" id="send-btn" onclick="send()" disabled>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M7 12V2M2 7l5-5 5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </div>
    <div class="input-hint">Enter to send · Shift+Enter for new line</div>
  </div>
</div>

<script>
  let sessionId = crypto.randomUUID();
  let password = '';
  let busy = false;

  const gate = document.getElementById('gate');
  const messagesEl = document.getElementById('messages');
  const emptyEl = document.getElementById('empty');
  const inputEl = document.getElementById('input');
  const sendBtn = document.getElementById('send-btn');

  // Unlock
  function unlock() {
    const pw = document.getElementById('pw-input').value;
    if (!pw) return;
    password = pw;
    gate.classList.add('hidden');
    inputEl.focus();
  }
  document.getElementById('pw-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') unlock();
  });

  // Auto-resize textarea
  function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    sendBtn.disabled = !el.value.trim() || busy;
  }

  inputEl.addEventListener('input', () => {
    sendBtn.disabled = !inputEl.value.trim() || busy;
  });

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!busy && inputEl.value.trim()) send();
    }
  }

  // Append message to DOM
  function appendMessage(role, content, isTyping = false) {
    if (emptyEl) emptyEl.remove();

    const row = document.createElement('div');
    row.className = 'msg-row';

    const avatar = document.createElement('div');
    avatar.className = `msg-avatar ${role}`;
    avatar.textContent = role === 'agent' ? 'DA' : 'You';

    const msgContent = document.createElement('div');
    msgContent.className = 'msg-content';

    const label = document.createElement('div');
    label.className = `msg-label ${role}`;
    label.textContent = role === 'agent' ? 'Diagnostic Analyst' : 'You';

    const body = document.createElement('div');
    body.className = `msg-body ${role === 'user' ? 'user-body' : ''}`;

    if (isTyping) {
      body.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
    } else {
      body.innerHTML = role === 'agent'
        ? marked.parse(content)
        : content.replace(/\\n/g, '<br>');
    }

    msgContent.appendChild(label);
    msgContent.appendChild(body);
    row.appendChild(avatar);
    row.appendChild(msgContent);
    messagesEl.appendChild(row);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    return body;
  }

  async function send() {
    const text = inputEl.value.trim();
    if (!text || busy) return;

    busy = true;
    sendBtn.disabled = true;
    inputEl.value = '';
    inputEl.style.height = 'auto';

    appendMessage('user', text);
    const typingBody = appendMessage('agent', '', true);

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId, password })
      });

      if (res.status === 401) {
        typingBody.innerHTML = '<em style="color:#e05757">Incorrect password. Reload and try again.</em>';
        return;
      }

      const data = await res.json();
      if (!res.ok) {
        typingBody.innerHTML = `<em style="color:#e05757">Error ${res.status}: ${data.detail || 'Unknown error'}</em>`;
        return;
      }
      typingBody.innerHTML = marked.parse(data.response);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } catch (err) {
      typingBody.innerHTML = `<em style="color:#e05757">Error: ${err.message}</em>`;
    } finally {
      busy = false;
      sendBtn.disabled = !inputEl.value.trim();
      inputEl.focus();
    }
  }

  function newSession() {
    if (busy) return;
    sessionId = crypto.randomUUID();
    messagesEl.innerHTML = '';
    const empty = document.createElement('div');
    empty.id = 'empty';
    empty.innerHTML = `
      <div class="empty-icon">⬡</div>
      <div class="empty-title">Describe the problem</div>
      <div class="empty-sub">State the challenge, symptom, or situation you want to diagnose. Be as honest as you can — uncertainty is useful data.</div>
    `;
    messagesEl.appendChild(empty);
    inputEl.value = '';
    inputEl.style.height = 'auto';
    inputEl.focus();
  }
</script>
</body>
</html>"""


class ChatRequest(BaseModel):
    message: str
    session_id: str
    password: str


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.post("/chat")
async def chat(req: ChatRequest):
    if not APP_PASSWORD or req.password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    if req.session_id not in sessions:
        sessions[req.session_id] = []

    sessions[req.session_id].append({"role": "user", "content": req.message})

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=sessions[req.session_id],
        )
    except Exception as e:
        sessions[req.session_id].pop()  # remove the message we just added
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    reply = response.content[0].text
    sessions[req.session_id].append({"role": "assistant", "content": reply})

    return {"response": reply, "session_id": req.session_id}


@app.delete("/session/{session_id}")
async def clear_session(session_id: str, password: str):
    if password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    sessions.pop(session_id, None)
    return {"status": "cleared"}
