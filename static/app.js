/* ═══════════════════════════════════════════
   StructMind — App Core v2.0
   ═══════════════════════════════════════════ */

const APP = { name: 'StructMind', subtitle: '数据结构 AI 智练中心' };
const $ = (s, p=document) => p.querySelector(s);
const $$ = (s, p=document) => [...p.querySelectorAll(s)];

// ═══ State ═══
const S = {
  tab: 'dashboard',
  stats: null, config: null, discussions: [],
  // Auth
  token: null, user: null,
  // Practice
  session: null, idx: 0, results: {},
  assignmentSession: null, assignmentIdx: 0, assignmentResults: {},
  // AI
  aiQuestion: null, aiModal: null,
  tutorMessages: [], tutorConvId: null, tutorLoading: false, tutorStreamContent: '',
  // WebSocket
  wsConnected: false, ws: null, wsReconnectTimer: null,
  // Profile
  profile: null,
  // Misc
  wrongItems: [], discussionResult: null, selectedDiscussionId: null,
  toast: '', loading: false, modal: null,
};

// ═══ API ═══
async function api(path, opts={}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers||{}) };
  if (S.token) headers['Authorization'] = `Bearer ${S.token}`;
  const res = await fetch(path, { ...opts, headers });
  const data = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error(data.error || `请求失败: ${res.status}`);
  return data;
}

async function streamApi(path, payload, onEvent) {
  const headers = { 'Content-Type': 'application/json' };
  if (S.token) headers['Authorization'] = `Bearer ${S.token}`;
  const res = await fetch(path, { method:'POST', headers, body: JSON.stringify(payload) });
  if (!res.ok) { const d = await res.json().catch(()=>({})); throw new Error(d.error||`请求失败`); }
  if (!res.body) throw new Error('浏览器不支持流式读取');
  const reader = res.body.getReader(), decoder = new TextDecoder('utf-8');
  let buffer = '';
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream:true});
    const parts = buffer.split('\n\n'); buffer = parts.pop()||'';
    for (const part of parts) {
      const line = part.split('\n').find(l=>l.startsWith('data:'));
      if (!line) continue;
      try { onEvent(JSON.parse(line.slice(5).trim())); } catch(e) {}
    }
  }
}

// ═══ Auth ═══
function loadAuth() {
  try { const s = localStorage.getItem('sm_auth'); if (s) { const d = JSON.parse(s); S.token = d.token; S.user = d.user; } } catch(e) {}
}
function saveAuth() { localStorage.setItem('sm_auth', JSON.stringify({token:S.token, user:S.user})); }
function clearAuth() { S.token = null; S.user = null; localStorage.removeItem('sm_auth'); }
function isLoggedIn() { return !!S.token && S.user?.status === 'approved'; }
function isAdmin() { return S.user?.role === 'admin'; }

async function handleLogin(account, password) {
  const d = await api('/api/auth/login', { method:'POST', body: JSON.stringify({account, password}) });
  S.token = d.token; S.user = d.user; saveAuth();
}
async function handleRegister(account, password, name, phone) {
  return api('/api/auth/register', { method:'POST', body: JSON.stringify({account, password, name, phone}) });
}
async function handleLogout() {
  try { await api('/api/auth/logout', { method:'POST' }); } catch(e) {}
  clearAuth(); S.profile = null; S.tab = 'dashboard'; S.modal = null; render();
}

// ═══ Init ═══
async function init() {
  loadAuth();
  connectWsTutor();
  try {
    const [stats, config, discussions] = await Promise.all([api('/api/stats'), api('/api/config'), api('/api/discussions')]);
    S.stats = stats; S.config = config; S.discussions = discussions.discussions||[];
    S.selectedDiscussionId = S.discussions[0]?.id||null;
    if (isLoggedIn()) {
      try { S.profile = (await api('/api/profile')).profile; } catch(e) {}
    }
    render();
  } catch(e) {
    document.querySelector('#app').innerHTML = `<main class="boot"><p>${esc(e.message)}</p></main>`;
  }
}

async function refreshStats() {
  const [stats, config] = await Promise.all([api('/api/stats'), api('/api/config')]);
  S.stats = stats; S.config = config;
  if (isLoggedIn()) { try { S.profile = (await api('/api/profile')).profile; } catch(e) {} }
}

// ═══ Render ═══
function render() {
  if (!S.stats || !S.config) return;
  document.querySelector('#app').innerHTML = S.modal
    ? renderModal() + renderShell()
    : renderShell();
  bindEvents();
}

function renderShell() {
  const title = pageTitle();
  return `<div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <img src="/logo.svg" class="brand-logo" alt="StructMind"/>
        <div><h1>${APP.name}</h1><p>${APP.subtitle}</p></div>
      </div>
      <nav class="nav">${navItems().map(([k,l,i])=>`
        <button class="nav-btn ${S.tab===k?'active':''}" data-tab="${k}">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icons[i]||''}</svg>
          <span>${l}</span>
        </button>`).join('')}</nav>
      ${isLoggedIn() ? `
        <div class="sidebar-user" data-action="profile">
          <div class="user-avatar">${(S.user.name||'?')[0]}</div>
          <div><div class="user-name">${esc(S.user.name)}</div><div class="user-role">${isAdmin()?'管理员':'学生'} · ${profileAccuracy()}%</div></div>
        </div>` : `
        <button class="btn btn-primary" style="margin-top:auto;width:100%" data-action="showLogin">登录 / 注册</button>`}
    </aside>
    <main class="main">
      <header class="topbar">
        <div><h2>${title.title}</h2><p>${title.subtitle}</p></div>
        <div class="topbar-right">
          ${isAdmin()?`<button class="btn btn-soft btn-sm" data-tab="admin">🔐 管理审批</button>`:''}
          <span id="wsStatus" class="ai-status ${S.wsConnected?'online':''}"><span class="dot ${S.wsConnected?'':'offline'}"></span>${S.wsConnected?'WS已连接':'WS未连接'}</span>
          <span class="ai-status ${anyAIConfigured()?'online':''}"><span class="dot ${anyAIConfigured()?'':'offline'}"></span>${anyAIConfigured()?`AI已连接·${esc(S.config.default_model)}`:'AI未配置'}</span>
        </div>
      </header>
      <div class="content-area">${renderTab()}</div>
      <footer class="footer">${APP.name} · ${APP.subtitle} · ©️谭书宏<br><a href="https://beian.miit.gov.cn" target="_blank" rel="noopener" style="color:var(--muted);text-decoration:none">湘ICP备2026021754号-2</a></footer>
    </main>
    ${S.toast?`<div class="toast" role="alert">${esc(S.toast)}</div>`:''}
    ${renderAiModal()}
  </div>`;
}

function renderModal() {
  if (S.modal === 'login') return renderLoginModal();
  return '';
}

// ═══ Login Modal ═══
function renderLoginModal() {
  return `<div class="modal-overlay" data-action="closeModal">
    <div class="modal" data-stop-propagation>
      <div class="modal-header">
        <div></div>
        <button class="modal-close" data-action="closeModal">×</button>
      </div>
      <div class="modal-body">
        <img src="/logo.svg" class="login-logo" alt="StructMind"/>
        <h3 style="text-align:center;margin:0">欢迎来到 StructMind</h3>
        <p style="text-align:center;color:var(--muted);font-size:0.9rem">数据结构 AI 智练中心</p>
        <div class="login-tabs">
          <button class="login-tab active" data-login-tab="login">登录</button>
          <button class="login-tab" data-login-tab="register">注册</button>
        </div>
        <div id="loginForm">
          <div class="form-group"><label class="form-label">账号</label><input class="form-input" id="loginAccount" placeholder="请输入账号" autocomplete="username"/></div>
          <div class="form-group"><label class="form-label">密码</label><input class="form-input" id="loginPassword" type="password" placeholder="请输入密码" autocomplete="current-password"/></div>
          <div id="registerFields" style="display:none">
            <div class="form-group"><label class="form-label">姓名</label><input class="form-input" id="regName" placeholder="请输入真实姓名"/></div>
            <div class="form-group"><label class="form-label">手机号</label><input class="form-input" id="regPhone" type="tel" placeholder="请输入手机号码" maxlength="11"/></div>
            <div class="card" style="background:var(--info-bg);border-color:#b8ddd4"><small style="color:var(--sm-primary)">📋 注册后需等待管理员审批通过方可登录使用</small></div>
          </div>
          <div id="loginError" style="display:none;background:var(--danger-bg);border:1px solid #fecaca;border-radius:10px;padding:10px 14px;margin-top:8px;color:var(--danger);font-size:0.88rem"></div>
          <div id="loginSuccess" style="display:none;background:var(--success-bg);border:1px solid #bbf7d0;border-radius:10px;padding:10px 14px;margin-top:8px;color:var(--success);font-size:0.88rem"></div>
          <button class="btn btn-primary" style="width:100%;margin-top:12px" data-action="submitLogin">登 录</button>
        </div>
      </div>
    </div>
  </div>`;
}

// ═══ AI Modal ═══
function renderAiModal() {
  const m = S.aiModal; if (!m?.open) return '';
  const q = m.question; const showReply = m.loading || m.reply;
  return `<div class="modal-overlay" data-action="closeAiModal">
    <div class="modal ai-modal" data-stop-propagation>
      <div class="modal-header">
        <div><h3>题目 AI 辅助</h3><p style="color:var(--muted);font-size:0.85rem">${esc(q.chapter)} · ${esc(q.qtype)} · #${esc(q.source_order||q.id)}</p></div>
        <button class="modal-close" data-action="closeAiModal">×</button>
      </div>
      <div class="modal-body">
        <div class="card" style="background:var(--bg)">
          <div class="question-meta">${renderQuestionTags(q)}</div>
          <div class="stem compact">${renderRich(q.stem)}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div class="form-group"><label class="form-label">模型</label><select class="form-select" id="aiModalModel">${modelOpts(m.model)}</select></div>
          <div class="form-group"><label class="form-label">追问</label><input class="form-input" id="aiModalMsg" placeholder="例如：为什么不是B？"/></div>
        </div>
        <div class="action-row" style="display:flex;gap:8px">
          <button class="btn btn-primary" data-ai-action="explain" ${anyAIConfigured()&&!m.loading?'':'disabled'}>🤖 ${m.loading&&m.mode==='explain'?'讲解中...':'讲解这题'}</button>
          <button class="btn btn-soft" data-ai-action="check" ${anyAIConfigured()&&!m.loading?'':'disabled'}>🔍 检查题目</button>
          <button class="btn btn-ghost" data-ai-action="ask" ${anyAIConfigured()&&!m.loading?'':'disabled'}>💬 追问</button>
        </div>
        ${anyAIConfigured()?'':'<div class="empty">请先到 AI 配置页填写 API Key。</div>'}
        ${m.error?`<div class="result wrong"><strong>AI 请求失败</strong><div>${renderRich(m.error)}</div></div>`:''}
        ${showReply?`<div class="ai-reply" id="aiReplyBox"><div style="display:flex;justify-content:space-between;margin-bottom:8px"><span style="color:var(--muted)">${modeTitle(m.mode)}</span><strong>${esc(m.model||S.config.default_model)}</strong></div><div id="aiReplyContent">${renderRich(m.reply||'')||'<span style="color:var(--muted)">正在连接模型...</span>'}</div></div>`:''}
      </div>
    </div>
  </div>`;
}

// ═══ Tabs ═══
function navItems() {
  const items = [['dashboard','学习仪表盘','home'],['practice','题库练习','play'],['assignment','作业题库','stack'],['ai','AI 导师','bot'],['discussion','讨论题','message'],['wrong','错题本','book'],['settings','AI 配置','settings'],['audit','导入审计','shield']];
  return items;
}

function pageTitle() {
  const m = {dashboard:[`${APP.name} 仪表盘`,'学习进度、用户画像与个性化推荐'],practice:['题库练习','顺序及随机模式的客观题练习'],assignment:['作业题库','AI参考批改与Word答案对照'],ai:['AI 导师','苏格拉底式引导答疑'],discussion:['讨论题','AI参考批改与要点反馈'],wrong:['错题本','回顾答错的题目'],settings:['AI 配置','设置API Key和模型'],audit:['导入审计','题库导入问题处理记录'],admin:['管理审批','审批新用户注册申请']};
  const t = m[S.tab]||[S.tab,''];
  return {title:t[0],subtitle:t[1]};
}

function renderTab() {
  if (S.modal) return '';
  const fns = {dashboard:renderDashboard,practice:renderPractice,assignment:renderAssignment,ai:renderAI,discussion:renderDiscussion,wrong:renderWrong,settings:renderSettings,audit:renderAudit,admin:renderAdmin};
  return (fns[S.tab]||renderDashboard)();
}

// ═══ Dashboard ═══
function renderDashboard() {
  const c = S.stats.counts, a = S.stats.banks?.assignment, p = S.stats.practice;
  const acc = p.attempts ? Math.round(p.correct/p.attempts*100) : 0;
  const integ = S.stats.integrity||{};
  const intOk = Object.values(integ).filter(v=>v===false).length===0 && !(integ.missing_answer_ids||[]).length;
  return `<div class="grid" style="gap:16px">
    ${!isLoggedIn()?`<div class="card card-glass" style="text-align:center;padding:28px">
      <img src="/logo.svg" class="login-logo" style="margin-bottom:12px" alt="StructMind"/>
      <h3 style="margin:0 0 4px">欢迎使用 StructMind</h3>
      <p style="color:var(--muted);margin:0 0 16px">登录后解锁个性化学习推荐、AI导师答疑、用户画像等全部功能</p>
      <button class="btn btn-primary" data-action="showLogin">立即登录</button>
    </div>`:''}
    ${S.profile?`<div class="card" style="border-left:4px solid var(--sm-primary)">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
        <div><strong style="font-size:1.1rem">📊 ${esc(S.user.name)} 的学习画像</strong>
        <p style="color:var(--muted);margin:4px 0 0">已练习 ${S.profile.total_attempts||0} 题 · 正确率 ${profileAccuracy()}%</p></div>
        <div class="weak-tags">${(S.profile.weak_concepts||[]).map(c=>`<span class="weak-tag">🔍 ${esc(c)}</span>`).join('')}${(S.profile.strong_concepts||[]).slice(0,3).map(c=>`<span class="strong-tag">✅ ${esc(c)}</span>`).join('')}</div>
      </div>
      <div style="margin-top:12px"><button class="btn btn-primary btn-sm" data-action="recommendPractice">🎯 智能推荐练习</button></div>
    </div>`:''}
    <div class="grid grid-2">
      <div class="card"><div class="grid grid-4">${metric('客观题',c.objective,'顺序/随机练习')}${metric('作业题',a?.counts?.questions||0,'Word答案+AI参考')}${metric('讨论题',c.discussion,'AI参考批改')}${metric('题库完整性',intOk?'通过':'需复核',intOk?'全部校验通过':'查看审计')}</div></div>
      <div class="card">${renderProfileRadar()}</div>
    </div>
    <div class="grid grid-3">${Object.entries(S.stats.chapters||{}).map(([ch,n])=>`<div class="metric"><span>${esc(ch)}</span><strong>${n}</strong><span>道题</span></div>`).join('')}</div>
    <div class="action-row" style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn btn-primary" data-tab="practice">▶ 开始练习</button>
      <button class="btn btn-soft" data-tab="ai">🤖 AI 导师答疑</button>
      <button class="btn btn-soft" data-tab="wrong">📖 错题本</button>
      <button class="btn btn-ghost" data-tab="audit">🔍 查看审计</button>
    </div>
  </div>`;
}

function renderProfileRadar() {
  if (!S.profile) return '<div class="empty"><span class="empty-icon">📊</span><p>登录并练习后查看能力雷达图</p></div>';
  const ta = S.profile.type_accuracy||{};
  const types = ['单选题','多选题','填空题','判断题'];
  const vals = types.map(t=>Math.round((ta[t]||0)*100));
  const maxR = 80, cx = 150, cy = 130;
  const points = vals.map((v,i)=>{
    const angle = (Math.PI*2/4)*i - Math.PI/2;
    const r = maxR * (v/100);
    return `${cx+r*Math.cos(angle)},${cy+r*Math.sin(angle)}`;
  });
  return `<svg viewBox="0 0 300 240" style="width:100%;max-width:400px"><text x="150" y="18" text-anchor="middle" fill="#4a5c58" font-size="13" font-weight="600">题型掌握度</text>
    ${[25,50,75,100].map(p=>`<circle cx="${cx}" cy="${cy}" r="${maxR*p/100}" fill="none" stroke="#edf2f0" stroke-width="1"/><text x="${cx}" y="${cy-maxR*p/100-4}" fill="#a0b0ac" font-size="10" text-anchor="middle">${p}%</text>`).join('')}
    ${types.map((t,i)=>{const a=(Math.PI*2/4)*i-Math.PI/2;return`<line x1="${cx}" y1="${cy}" x2="${cx+maxR*Math.cos(a)}" y2="${cy+maxR*Math.sin(a)}" stroke="#edf2f0" stroke-width="1"/>`;}).join('')}
    <polygon points="${points.join(' ')}" fill="rgba(45,138,123,0.15)" stroke="#2d8a7b" stroke-width="2"/>
    ${vals.map((v,i)=>{const a=(Math.PI*2/4)*i-Math.PI/2,r=maxR*(v/100);return`<circle cx="${cx+r*Math.cos(a)}" cy="${cy+r*Math.sin(a)}" r="5" fill="#2d8a7b" stroke="#fff" stroke-width="2"/>`}).join('')}
    ${types.map((t,i)=>{const a=(Math.PI*2/4)*i-Math.PI/2,r=maxR+18;return`<text x="${cx+r*Math.cos(a)}" y="${cy+r*Math.sin(a)}" text-anchor="middle" fill="#4a5c58" font-size="12" dominant-baseline="middle">${t}</text>`;}).join('')}
  </svg>`;
}

// ═══ Practice ═══
function renderPractice() {
  if (!S.session) return renderPracticeSetup();
  const q = S.session.questions[S.idx]; if (!q) return '<div class="panel"><div class="panel-inner"><div class="empty">没有符合条件的题目</div><button class="btn btn-primary" style="margin-top:12px" data-reset-session>重新选择</button></div></div>';
  const prog = Math.round((S.idx+1)/S.session.questions.length*100);
  const mn = {random:'随机练习',sequence:'顺序练习',wrong:'错题重做'}[S.session.mode]||S.session.mode;
  return `<div class="workspace-grid grid">
    <div class="panel question-card"><div class="panel-inner">${renderQuestion(q,'bank')}</div></div>
    <aside class="panel"><div class="panel-inner side-list">
      ${sideRow('模式',mn)}${sideRow('进度',`${S.idx+1}/${S.session.questions.length}`)}
      <div class="progress"><div class="progress-bar" style="width:${prog}%"></div></div>
      ${sideRow('抽题数',S.session.count)}${sideRow('可用',S.session.total_available)}
      <div class="action-row" style="display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" data-prev-question ${S.idx===0?'disabled':''}>上一题</button>
        <button class="btn btn-soft btn-sm" data-next-question ${S.idx>=S.session.questions.length-1?'disabled':''}>下一题 →</button>
        <button class="btn btn-danger btn-sm" data-reset-session>结束本组</button>
      </div>
    </div></aside>
  </div>`;
}

function renderPracticeSetup() {
  return `<div class="panel"><div class="panel-inner grid"><h3 style="margin:0">创建练习</h3>
    <div>
      <div class="form-label" style="margin-bottom:6px">题型</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">${['单选题','多选题','填空题','判断题'].map(t=>`<label class="tag" style="cursor:pointer;padding:6px 12px"><input type="checkbox" name="pType" value="${t}" checked style="accent-color:var(--sm-primary)"/> ${t}</label>`).join('')}</div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <div class="form-group"><label class="form-label">章节</label><select class="form-select" id="pChapter"><option value="">全部章节</option>${Object.keys(S.stats.chapters).map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div>
      <div class="form-group"><label class="form-label">题量</label><input class="form-input" id="pCount" type="number" min="1" placeholder="留空=全部"/></div>
    </div>
    <div class="action-row" style="display:flex;gap:8px">
      <button class="btn btn-primary" data-start-mode="sequence">▶ 顺序练习</button>
      <button class="btn btn-soft" data-start-mode="random">🎲 随机出题</button>
      <button class="btn btn-ghost" data-action="recommendPractice">🎯 智能推荐</button>
    </div>
  </div></div>`;
}

// ═══ Assignment ═══
function renderAssignment() {
  const bank = S.stats.banks?.assignment||{};
  if (!S.assignmentSession) {
    return `<div class="workspace-grid grid">
      <div class="panel"><div class="panel-inner grid"><h3 style="margin:0">创建作业练习</h3>
        <div>
          <div class="form-label" style="margin-bottom:6px">题型</div>
          <div style="display:flex;gap:6px">${['简答题','填空题'].map(t=>`<label class="tag" style="cursor:pointer;padding:6px 12px"><input type="checkbox" name="aType" value="${t}" checked style="accent-color:var(--sm-primary)"/> ${t}</label>`).join('')}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div class="form-group"><label class="form-label">分组</label><select class="form-select" id="aChapter"><option value="">全部</option>${Object.keys(bank.chapters||{}).map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div>
          <div class="form-group"><label class="form-label">题量</label><input class="form-input" id="aCount" type="number" min="1" placeholder="留空=全部"/></div>
        </div>
        <div class="action-row" style="display:flex;gap:8px">
          <button class="btn btn-primary" data-start-assignment="sequence">▶ 顺序练习</button>
          <button class="btn btn-soft" data-start-assignment="random">🎲 随机出题</button>
        </div>
      </div></div>
      <aside class="panel"><div class="panel-inner side-list">
        ${sideRow('作业题',bank.counts?.questions||0)}${sideRow('Word答案',bank.counts?.word_answers||0)}${sideRow('AI参考',bank.counts?.ai_reference_answers||0)}
        <span style="color:var(--muted);line-height:1.65">简答题使用AI参考批改，AI参考答案不会计作官方答案。</span>
      </div></aside>
    </div>`;
  }
  const q = S.assignmentSession.questions[S.assignmentIdx]; if (!q) return '<div class="panel"><div class="panel-inner"><div class="empty">没有符合条件的题目</div><button class="btn btn-primary" style="margin-top:12px" data-reset-assignment>重新选择</button></div></div>';
  const prog = Math.round((S.assignmentIdx+1)/S.assignmentSession.questions.length*100);
  return `<div class="workspace-grid grid">
    <div class="panel question-card"><div class="panel-inner">${renderQuestion(q,'assignment','assignment')}</div></div>
    <aside class="panel"><div class="panel-inner side-list">
      ${sideRow('进度',`${S.assignmentIdx+1}/${S.assignmentSession.questions.length}`)}
      <div class="progress"><div class="progress-bar" style="width:${prog}%"></div></div>
      ${sideRow('答案来源',ansSrc(q.answer_source))}
      <div class="action-row" style="display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" data-prev-assignment ${S.assignmentIdx===0?'disabled':''}>上一题</button>
        <button class="btn btn-soft btn-sm" data-next-assignment ${S.assignmentIdx>=S.assignmentSession.questions.length-1?'disabled':''}>下一题 →</button>
        <button class="btn btn-danger btn-sm" data-reset-assignment>结束</button>
      </div>
    </div></aside>
  </div>`;
}

// ═══ AI Tutor ═══
function renderAI() {
  return `<div class="workspace-grid grid">
    <div class="panel"><div class="panel-inner">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px">
        <div><h3 style="margin:0">🦉 AI 导师 · 苏格拉底式答疑</h3><p style="color:var(--muted);margin:4px 0 0;font-size:0.85rem">我不直接给你答案，但我会提出正确的问题，帮你真正理解数据结构</p></div>
        <button class="btn btn-ghost btn-sm" data-action="resetTutor">🔄 新对话</button>
      </div>
      <div class="chat-area" id="tutorChat" style="max-height:380px;min-height:200px">
        ${S.tutorMessages.length===0?`<div class="empty">
          <span class="empty-icon">🦉</span><p class="empty-title">我是你的苏格拉底式AI导师</p>
          <p class="empty-desc">我不会直接给你答案，而是通过提问引导你自己发现答案。</p>
          <div style="margin-top:12px;text-align:left">
            <p style="color:var(--muted);font-size:0.85rem;margin-bottom:8px">试试这些问题：</p>
            ${['🌳 二叉树的三种遍历有什么区别？','🔑 哈希表冲突解决有哪些方法？','📊 快速排序和归并排序的复杂度分析','📐 如何判断一个图是否有环？'].map(q=>`<button class="btn btn-ghost btn-sm" style="margin:4px;text-align:left" data-tutor-example="${escAttr(q)}">${q}</button>`).join('')}
          </div>
        </div>`:''}
        ${S.tutorMessages.map(m=>`<div class="chat-msg ${m.role}"><div class="chat-avatar">${m.role==='user'?'👤':'🦉'}</div><div class="chat-bubble">${renderRich(m.content)}</div></div>`).join('')}
        ${S.tutorLoading?`<div class="chat-msg assistant"><div class="chat-avatar">🦉</div><div class="chat-bubble"><span class="skeleton" style="display:inline-block;width:60%;height:14px"></span></div></div>`:''}
      </div>
      <div class="chat-input-row">
        <input class="chat-input" id="tutorInput" placeholder="输入你的问题或思考..."/>
        <button class="btn btn-primary" data-action="sendTutor" ${S.tutorLoading||!anyAIConfigured()?'disabled':''}>发送</button>
      </div>
      ${anyAIConfigured()?`<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">${['请帮我理解二叉树的遍历','栈和队列有什么区别','什么是哈夫曼树'].map(q=>`<button class="btn btn-ghost btn-sm" data-tutor-example="${escAttr(q)}">${q}</button>`).join('')}</div>`:''}
      ${S.tutorConvId?`<div style="margin-top:8px;color:var(--muted);font-size:0.78rem">对话 #${S.tutorConvId}</div>`:''}
    </div></div>
    <aside class="panel"><div class="panel-inner side-list">
      <strong>🦉 苏格拉底式导师</strong>
      <div class="card" style="background:var(--info-bg);border-color:#b8ddd4"><p style="margin:0;font-size:0.85rem;color:var(--sm-primary)">我不会直接给你答案。我会通过提问引导你思考关键概念，帮你建立自己的理解。</p></div>
      <div style="display:grid;gap:8px">
        ${['数据结构概念理解','算法步骤推导','复杂度的直观理解','解题思路引导','概念辨析与对比'].map(t=>`<span class="tag tag-info">${t}</span>`).join('')}
      </div>
      <div style="margin-top:8px">
        <button class="btn btn-primary btn-sm" style="width:100%" data-action="generateAI">🤖 生成AI变式题</button>
        <p style="color:var(--muted);font-size:0.82rem;margin-top:8px">也可以生成AI题目来检验学习效果</p>
      </div>
    </div></aside>
  </div>`;
}

// ═══ Admin ═══
function renderAdmin() {
  if (!isAdmin()) return '<div class="empty"><p>仅管理员可访问</p></div>';
  return `<div class="panel"><div class="panel-inner" id="adminPanel">
    <h3 style="margin:0 0 8px">🔐 管理审批</h3>
    <p style="color:var(--muted);margin:0 0 16px">审批新用户注册申请</p>
    <div id="adminContent"><div class="skeleton skeleton-text" style="width:80%"></div><div class="skeleton skeleton-text" style="width:60%"></div></div>
  </div></div>`;
}

async function loadAdminPanel() {
  try {
    const [pending, all] = await Promise.all([api('/api/admin/pending'), api('/api/admin/users')]);
    const pu = pending.users||[], au = all.users||[];
    document.querySelector('#adminContent').innerHTML = `
      <div class="grid grid-2" style="margin-bottom:16px"><div class="metric"><span>待审批</span><strong>${pu.length}</strong></div><div class="metric"><span>已通过</span><strong>${au.filter(u=>u.status==='approved').length}</strong></div></div>
      ${pu.length===0?'<div class="empty"><p>✅ 没有待审批的申请</p></div>':`<div class="grid" style="gap:8px">${pu.map(u=>`<div class="card" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
        <div style="display:flex;align-items:center;gap:10px"><div class="user-avatar">${esc(u.name[0])}</div><div><strong>${esc(u.name)}</strong><div style="color:var(--muted);font-size:0.85rem">@${esc(u.account)} · ${esc(u.phone)}</div></div></div>
        <div style="display:flex;gap:6px"><button class="btn btn-primary btn-sm" data-approve-user="${escAttr(String(u.id))}" data-approve-val="1">通过</button><button class="btn btn-danger btn-sm" data-approve-user="${escAttr(String(u.id))}" data-approve-val="0">拒绝</button></div>
      </div>`).join('')}</div>`}
      <h4 style="margin:16px 0 8px">全部用户</h4>
      <div class="table-wrap"><table><thead><tr><th>姓名</th><th>账号</th><th>手机</th><th>角色</th><th>状态</th><th>注册时间</th></tr></thead><tbody>${au.map(u=>`<tr><td>${esc(u.name)}</td><td>@${esc(u.account)}</td><td>${esc(u.phone)}</td><td>${u.role==='admin'?'管理员':'学生'}</td><td><span class="tag ${u.status==='approved'?'tag-success':u.status==='rejected'?'tag-danger':'tag-warning'}">${u.status==='approved'?'已通过':u.status==='rejected'?'已拒绝':'待审批'}</span></td><td>${new Date(u.created_at*1000).toLocaleDateString('zh-CN')}</td></tr>`).join('')}</tbody></table></div>`;
  } catch(e) { document.querySelector('#adminContent').innerHTML = `<div class="result wrong">${esc(e.message)}</div>`; }
}

async function approveUser(uid, ok) {
  try { await api('/api/admin/approve',{method:'POST',body:JSON.stringify({user_id:uid,approved:ok})}); loadAdminPanel(); toast(ok?'已通过':'已拒绝','success'); } catch(e) { toast(e.message); }
}

// ═══ Discussion ═══
function renderDiscussion() {
  const sel = S.discussions.find(d=>d.id===S.selectedDiscussionId)||S.discussions[0];
  return `<div class="workspace-grid grid">
    <div class="panel"><div class="panel-inner grid">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div class="form-group"><label class="form-label">讨论题</label><select class="form-select" id="discSelect">${S.discussions.map(d=>`<option value="${d.id}" ${sel&&sel.id===d.id?'selected':''}>${esc(d.chapter)} · ${d.id}</option>`).join('')}</select></div>
        <div class="form-group"><label class="form-label">模型</label><select class="form-select" id="discModel">${modelOpts()}</select></div>
      </div>
      ${sel?`<div class="stem">${renderRich(sel.prompt)}</div>`:'<div class="empty">没有讨论题</div>'}
      <div class="form-group"><label class="form-label">你的回答</label><textarea class="form-textarea" id="discAnswer" placeholder="写出你的理解、推理过程或关键词"></textarea></div>
      <button class="btn btn-primary" data-grade-discussion ${anyAIConfigured()&&!S.loading?'':'disabled'}>💬 ${S.loading?'批改中...':'提交参考批改'}</button>
      ${S.discussionResult?renderDiscResult(S.discussionResult):''}
    </div></div>
    <aside class="panel"><div class="panel-inner side-list"><strong>讨论题说明</strong><span style="color:var(--muted);line-height:1.65">讨论题无Word标准答案，AI反馈只作为复习参考，不计入正确率。</span></div></aside>
  </div>`;
}

// ═══ Wrong ═══
function renderWrong() {
  const ids = S.wrongItems.map(it=>it.question.id);
  return `<div class="panel"><div class="panel-inner grid">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
      <div><h3 style="margin:0">错题预览</h3><p style="color:var(--muted);margin:4px 0 0">最近答错的题目，按去重排列</p></div>
      <div style="display:flex;gap:8px"><button class="btn btn-soft btn-sm" data-load-wrong>🔄 刷新</button><button class="btn btn-primary btn-sm" data-redo-all ${ids.length?'':'disabled'}>▶ 重做全部</button></div>
    </div>
    ${S.wrongItems.length?S.wrongItems.map(it=>renderWrongItem(it)).join(''):'<div class="empty"><span class="empty-icon">🎉</span><p>还没有错题记录</p></div>'}
  </div></div>`;
}

function renderWrongItem(it) {
  const q = it.question;
  return `<div class="card" style="margin-top:12px">
    <div class="question-meta">${renderQuestionTags(q)}<span class="tag tag-danger">答错</span></div>
    <div class="stem compact">${renderRich(q.stem)}</div>
    ${(q.images||[]).map(s=>`<img src="${esc(s)}" style="max-width:100%;border-radius:8px;margin:8px 0" alt="配图"/>`).join('')}
    ${q.options?.length?`<div style="margin:8px 0;display:grid;gap:4px;padding:10px;border-radius:8px;background:var(--bg)">${q.options.map(o=>`<span><strong>${esc(o.key)}.</strong> ${renderInline(o.text)} ${o.ai_supplemented?'<span class="option-note">AI补全</span>':''}</span>`).join('')}</div>`:''}
    <div class="side-row"><span>你的答案</span><strong style="color:var(--danger)">${esc(Array.isArray(it.user_answer)?it.user_answer.join(''):it.user_answer)}</strong></div>
    <div class="side-row"><span>标准答案</span><strong style="color:var(--success)">${esc(q.answer)}</strong></div>
    <div style="display:flex;gap:8px;margin-top:8px"><button class="btn btn-primary btn-sm" data-redo-question="${q.id}">▶ 重做本题</button><button class="btn btn-ghost btn-sm" data-open-question-ai="${q.id}">🤖 AI解析</button></div>
  </div>`;
}

// ═══ Settings ═══
function renderSettings() {
  const zp = providerStatus('zhipu'), ds = providerStatus('deepseek');
  return `<div class="workspace-grid grid">
    <div class="panel"><div class="panel-inner grid"><h3 style="margin:0">AI 配置</h3>
      <div class="grid grid-2">${metric('智谱AI',zp.ai_configured?'已配置':'未配置',zp.key_preview||'支持glm系列')}${metric('DeepSeek',ds.ai_configured?'已配置':'未配置',ds.key_preview||'支持deepseek-v4')}</div>
      <div style="display:grid;gap:10px">
        <div class="form-group"><label class="form-label">智谱 API Key</label><input class="form-input" id="sZhipuKey" type="password" placeholder="留空不修改"/></div>
        <div class="form-group"><label class="form-label">DeepSeek API Key</label><input class="form-input" id="sDeepSeekKey" type="password" placeholder="留空不修改"/></div>
        <div class="form-group"><label class="form-label">默认模型</label><select class="form-select" id="sModel">${modelOpts()}</select></div>
      </div>
      <div class="action-row" style="display:flex;gap:8px">
        <button class="btn btn-primary" data-save-config>💾 保存配置</button>
        <button class="btn btn-danger btn-sm" data-clear-provider="zhipu" ${zp.api_key_source==='runtime'?'':'disabled'}>清除智谱</button>
        <button class="btn btn-danger btn-sm" data-clear-provider="deepseek" ${ds.api_key_source==='runtime'?'':'disabled'}>清除DeepSeek</button>
      </div>
      <div class="empty">页面配置的密钥只保存在后端进程内存中。环境变量 BIGMODEL_API_KEY / DEEPSEEK_API_KEY 可永久生效。</div>
    </div></div>
    <aside class="panel"><div class="panel-inner side-list"><strong>模型说明</strong><span style="color:var(--muted)">支持智谱 glm-5.1/glm-5/glm-4.7-flash，DeepSeek deepseek-v4-flash/pro。AI导师使用流式输出。</span></div></aside>
  </div>`;
}

// ═══ Audit ═══
function renderAudit() {
  const ex = S.stats.banks?.exam||S.stats, as = S.stats.banks?.assignment||{};
  const audit = [...(ex.audit||[]).map(a=>({...a,bank_label:'考试题库'})),...(as.audit||[]).map(a=>({...a,bank_label:'作业题库'}))];
  return `<div class="panel"><div class="panel-inner">
    <h3 style="margin:0 0 12px">导入审计</h3>
    <div class="table-wrap"><table><thead><tr><th>题库</th><th>题号</th><th>章节</th><th>题型</th><th>问题</th><th>处理</th></tr></thead><tbody>${audit.length?audit.map(a=>`<tr><td>${esc(a.bank_label)}</td><td>${esc(a.question_id||'')}</td><td>${esc(a.chapter||'')}</td><td>${esc(a.qtype||'')}</td><td>${esc(a.issue)}</td><td>${esc(a.handling)}</td></tr>`).join(''):'<tr><td colspan="6">未发现导入异常</td></tr>'}</tbody></table></div>
  </div></div>`;
}

// ═══ Question Rendering (shared) ═══
function renderQuestion(q, src, bankId=q.bank_id||'exam') {
  const rk = `${src}-${q.id}`, result = src==='assignment'? S.assignmentResults[rk] : S.results[rk];
  const canAI = ['bank','assignment'].includes(src) && Number.isFinite(Number(q.id));
  return `<div class="question-head">${renderQuestionTags(q)}<div class="question-tools"><span class="tag">#${esc(q.source_order||q.id)}</span>${canAI?`<button class="btn btn-ghost btn-sm" data-open-question-ai="${q.id}" data-open-question-bank="${bankId}">🤖 AI解析</button>`:''}</div></div>
    ${q.ai_completed?`<div style="padding:8px 12px;border-radius:8px;background:var(--info-bg);color:var(--sm-primary);margin-bottom:10px;font-size:0.85rem">${esc(q.completion_note||'本题显示文本已由AI补全表修复，标准答案不变')}</div>`:''}
    <div class="stem">${renderRich(q.stem)}</div>
    ${(q.images||[]).map(s=>`<img src="${esc(s)}" style="max-width:min(100%,600px);border-radius:8px;border:1px solid var(--border);margin:10px 0" alt="配图"/>`).join('')}
    ${renderAnswerControl(q,src)}
    ${src==='assignment'?renderAssignmentActions(q):`<div class="action-row" style="margin-top:12px"><button class="btn btn-primary" data-submit-${src}>✅ 提交答案</button></div>`}
    ${result?(src==='assignment'?renderAssignmentResult(result):renderResult(result)):''}`;
}

function renderQuestionTags(q) {
  return `<div class="question-meta">
    <span class="tag">${esc(q.chapter||'AI出题')}</span><span class="tag">${esc(q.qtype)}</span>
    ${q.answer_source?`<span class="tag ${q.answer_source==='ai_reference'?'tag-warning':'tag-success'}">${ansSrc(q.answer_source)}</span>`:''}
    ${q.ai_completed?'<span class="tag tag-info">AI补全</span>':''}
    ${q.repaired?'<span class="tag tag-warning">已校验</span>':''}
  </div>`;
}

function renderAnswerControl(q, src) {
  if (q.qtype==='简答题') return `<div class="form-group" style="margin:12px 0"><label class="form-label">你的回答</label><textarea class="form-textarea" id="${src}-answer" placeholder="写出解题过程或结论"></textarea></div>`;
  if (q.qtype==='填空题') return `<div class="form-group" style="margin:12px 0"><label class="form-label">你的答案</label><input class="form-input" id="${src}-answer" placeholder="输入填空答案"/></div>`;
  const multi = q.qtype==='多选题';
  const opts = q.options?.length?q.options:[{key:'A',text:'对'},{key:'B',text:'错'}];
  return `<div class="options">${opts.map(o=>`<label class="option"><input type="${multi?'checkbox':'radio'}" name="${src}-answer" value="${esc(o.key)}"/><span><span class="option-key">${esc(o.key)}.</span> ${renderInline(o.text||'选项缺失')}${o.ai_supplemented?'<span class="option-note">AI补全</span>':''}</span></label>`).join('')}</div>`;
}

function renderAssignmentActions(q) {
  if (q.qtype==='简答题') return `<div class="form-group" style="margin:8px 0"><label class="form-label">批改模型</label><select class="form-select" id="aModel">${modelOpts()}</select></div>
    <div class="action-row" style="display:flex;gap:8px"><button class="btn btn-primary" data-grade-assignment ${anyAIConfigured()&&!S.loading?'':'disabled'}>💬 ${S.loading?'批改中...':'AI参考批改'}</button><button class="btn btn-ghost" data-show-assignment-answer="${q.id}">👁 查看参考答案</button></div>`;
  return `<div class="action-row" style="display:flex;gap:8px"><button class="btn btn-primary" data-submit-assignment>✅ 提交答案</button><button class="btn btn-ghost" data-show-assignment-answer="${q.id}">👁 参考答案</button></div>`;
}

function renderResult(r) {
  return `<div class="result ${r.is_correct?'correct':'wrong'}"><div class="result-head"><span class="result-icon">${r.is_correct?'✅':'❌'}</span><strong>${r.is_correct?'回答正确！':'回答错误'}</strong></div>
    <div class="answer-line"><span>标准答案</span>${renderRich(r.correct_answer)}</div>${r.analysis?`<div class="answer-line"><span>解析</span>${renderRich(r.analysis)}</div>`:''}</div>`;
}

function renderAssignmentResult(r) {
  if (r.kind==='answer') return `<div class="result"><strong>${ansSrc(r.answer_source)}</strong><div class="answer-line"><span>参考答案</span>${renderRich(r.answer||'暂无')}</div>${r.answer_source==='ai_reference'?'<div style="color:var(--warning);font-size:0.82rem;margin-top:4px">⚠ 此答案为AI参考，非Word官方答案</div>':''}</div>`;
  if (r.feedback) { const fb = r.feedback||{}; return `<div class="result"><strong>${esc(fb.level||'参考反馈')} · ${fb.score??0}分</strong>
    ${fb.verdict?`<div class="answer-line"><span>结论</span>${renderRich(fb.verdict)}</div>`:''}
    ${fb.reference_answer?`<div class="answer-line"><span>参考答案</span>${renderRich(fb.reference_answer)}</div>`:''}
    ${fb.suggestion?`<div class="answer-line"><span>建议</span>${renderRich(fb.suggestion)}</div>`:''}
    <div class="grid grid-2" style="margin-top:8px"><div class="card"><strong>已覆盖</strong>${renderRich((fb.covered_points||[]).map(p=>'- '+p).join('\n')||'暂无')}</div><div class="card"><strong>可补充</strong>${renderRich((fb.missing_points||[]).map(p=>'- '+p).join('\n')||'暂无')}</div></div></div>`; }
  return renderResult(r);
}

function renderDiscResult(r) {
  const fb = r.feedback||{};
  return `<div class="result"><strong>${esc(fb.level||'参考反馈')} · ${fb.score??0}分</strong>
    ${fb.suggestion?`<div class="answer-line"><span>建议</span>${renderRich(fb.suggestion)}</div>`:''}
    ${fb.reference_answer?`<div class="answer-line"><span>参考答案</span>${renderRich(fb.reference_answer)}</div>`:''}
    <div class="grid grid-2" style="margin-top:8px"><div class="card"><strong>已覆盖</strong>${renderRich((fb.covered_points||[]).map(p=>'- '+p).join('\n')||'暂无')}</div><div class="card"><strong>可补充</strong>${renderRich((fb.missing_points||[]).map(p=>'- '+p).join('\n')||'暂无')}</div></div></div>`;
}

// ═══ AI Generation ═══
function renderAIGenerate() {
  return `<div class="card" style="margin-bottom:16px">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
      <div class="form-group"><label class="form-label">模型</label><select class="form-select" id="aiGenModel">${modelOpts()}</select></div>
      <div class="form-group"><label class="form-label">题型</label><select class="form-select" id="aiGenType"><option>单选题</option><option>多选题</option><option>填空题</option><option>判断题</option></select></div>
    </div>
    <button class="btn btn-primary" data-generate-ai ${anyAIConfigured()&&!S.loading?'':'disabled'}>🤖 ${S.loading?'生成中...':'生成AI变式题'}</button>
    ${S.aiQuestion?`<div class="card" style="margin-top:12px;background:var(--bg)">${renderQuestion(S.aiQuestion,'ai')}</div>`:'<div class="empty" style="margin-top:12px">生成后在此答题，AI解析支持公式与代码渲染</div>'}
  </div>`;
}

// ═══ Helpers ═══
function metric(l,v,n) { return `<div class="metric"><span>${esc(l)}</span><strong>${esc(v)}</strong><span>${esc(n)}</span></div>`; }
function sideRow(l,v) { return `<div class="side-row"><span>${esc(l)}</span><strong>${esc(v)}</strong></div>`; }
function ansSrc(s) { return s==='word_answer'?'Word答案':s==='ai_reference'?'AI参考':'无答案'; }
function modeTitle(m) { return {explain:'AI讲解',check:'题目检查',ask:'追问回答'}[m]||'AI辅助'; }
function anyAIConfigured() { return (S.config.providers||[]).some(p=>p.ai_configured); }
function providerStatus(id) { return (S.config.providers||[]).find(p=>p.id===id)||{}; }
function profileAccuracy() { return S.profile?.total_attempts?Math.round((S.profile.total_correct||0)/S.profile.total_attempts*100):0; }
function modelOpts(sel=S.config.default_model) {
  return (S.config.providers||[]).map(p=>`<optgroup label="${esc(p.label)}">${(p.models||[]).map(m=>`<option value="${m}" ${m===sel?'selected':''}>${m}</option>`).join('')}</optgroup>`).join('');
}

function esc(v) { return String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;'); }
function escAttr(v) { return esc(v).replaceAll('"','&quot;').replaceAll("'",'&#39;'); }
function toast(msg, type='') { S.toast = msg; render(); setTimeout(()=>{S.toast='';render();},3600); }

function renderInline(v) {
  let h = esc(v);
  h = h.replace(/`([^`]+)`/g,'<code>$1</code>');
  h = h.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  h = h.replace(/\\\((.+?)\\\)|\$([^$]+)\$/g,(_,a,b)=>`<span class="formula">${renderFormula(a||b)}</span>`);
  h = h.replace(/\bO\(([^)]+)\)/g,(_,c)=>`<span class="formula">O(${renderFormula(c)})</span>`);
  return h;
}
function renderFormula(v) { return (v||'').replace(/\^\{([^}]+)\}/g,'<sup>$1</sup>').replace(/\^([A-Za-z0-9+\-]+)/g,'<sup>$1</sup>').replace(/_\{([^}]+)\}/g,'<sub>$1</sub>').replace(/_([A-Za-z0-9]+)/g,'<sub>$1</sub>'); }

function renderRich(v) {
  const text = (v||'').trim(); if (!text) return '';
  const lines = text.split('\n'); let blocks=[], i=0;
  while (i<lines.length) {
    const l = lines[i]; if (!l.trim()) { i++; continue; }
    if (l.trim().startsWith('```')) { let code=[]; i++; while(i<lines.length&&!lines[i].trim().startsWith('```')){code.push(lines[i]);i++;} i++; blocks.push(`<pre class="code-block"><code>${esc(code.join('\n'))}</code></pre>`); continue; }
    if (l.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i+1]||'')) {
      let rows=[]; while(i<lines.length&&lines[i].includes('|')){rows.push(lines[i]);i++;}
      const cells=rows.filter((_,ri)=>ri!==1).map(r=>r.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(c=>c.trim()));
      const h=cells.shift()||[], b=cells;
      blocks.push(`<div class="rich-table-wrap"><table class="rich-table"><thead><tr>${h.map(c=>`<th>${renderInline(c)}</th>`).join('')}</tr></thead><tbody>${b.map(r=>`<tr>${r.map(c=>`<td>${renderInline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`); continue;
    }
    if (/^\s*#{1,4}\s+/.test(l)){blocks.push(`<h4 style="color:var(--sm-primary-dark);margin:0">${renderInline(l.replace(/^\s*#{1,4}\s+/,''))}</h4>`);i++;continue;}
    if (/^\s*[-*]\s+/.test(l)){let items=[];while(i<lines.length&&/^\s*[-*]\s+/.test(lines[i])){items.push(lines[i].replace(/^\s*[-*]\s+/,''));i++;}blocks.push(`<ul style="padding-left:1.2rem;display:grid;gap:4px">${items.map(it=>`<li>${renderInline(it)}</li>`).join('')}</ul>`);continue;}
    let para=[]; while(i<lines.length&&lines[i].trim()&&!lines[i].trim().startsWith('```')&&!lines[i].includes('|')&&!/^\s*#{1,4}\s+/.test(lines[i])&&!/^\s*[-*]\s+/.test(lines[i])){para.push(lines[i]);i++;} blocks.push(`<p>${para.map(renderInline).join('<br>')}</p>`);
  }
  return `<div class="rich-text">${blocks.join('')}</div>`;
}

// ═══ Icons (SVG paths) ═══
const icons = {
  home:'<path d="M3 10.5 12 3l9 7.5"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/>',
  play:'<path d="M8 5v14l11-7z"/>',
  bot:'<path d="M12 8V4"/><rect x="5" y="8" width="14" height="10" rx="3"/><path d="M8 21h8"/><path d="M9 13h.01"/><path d="M15 13h.01"/>',
  message:'<path d="M4 5h16v11H8l-4 4z"/>',
  book:'<path d="M5 4h10a4 4 0 0 1 4 4v12H9a4 4 0 0 0-4-4z"/><path d="M5 4v12"/>',
  shield:'<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/><path d="m9 12 2 2 4-4"/>',
  settings:'<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.05.05a2 2 0 1 1-2.83 2.83l-.05-.05A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.05A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.88.34l-.05.05a2 2 0 1 1-2.83-2.83l.05-.05A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.05A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.88l-.05-.05a2 2 0 1 1 2.83-2.83l.05.05A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.05A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.88-.34l.05-.05a2 2 0 1 1 2.83 2.83l-.05.05A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.05A1.7 1.7 0 0 0 19.4 15z"/>',
  stack:'<path d="m12 3 8 4-8 4-8-4z"/><path d="m4 12 8 4 8-4"/><path d="m4 17 8 4 8-4"/>',
  shuffle:'<path d="M16 3h5v5"/><path d="M4 20 21 3"/><path d="M21 16v5h-5"/><path d="m15 15 6 6"/><path d="m4 4 5 5"/>',
};

// ═══ Collect Answer ═══
function collectAnswer(src, qtype) {
  if (qtype==='简答题') return document.querySelector(`#${src}-answer`)?.value.trim()||'';
  if (qtype==='填空题') return document.querySelector(`#${src}-answer`)?.value.trim()||'';
  const checked = [...document.querySelectorAll(`input[name="${src}-answer"]:checked`)].map(c=>c.value);
  return qtype==='多选题'?checked:checked[0]||'';
}

// ═══ Session Starters ═══
async function startSession(mode) {
  const types = [...document.querySelectorAll('input[name="pType"]:checked')].map(c=>c.value);
  const ch = document.querySelector('#pChapter')?.value||'';
  const cnt = document.querySelector('#pCount')?.value||'';
  S.session = await api('/api/session',{method:'POST',body:JSON.stringify({mode,types,chapters:ch?[ch]:[],count:cnt||'all'})});
  S.idx=0; S.results={}; render();
}
async function startAssignmentSession(mode) {
  const types = [...document.querySelectorAll('input[name="aType"]:checked')].map(c=>c.value);
  const ch = document.querySelector('#aChapter')?.value||'';
  const cnt = document.querySelector('#aCount')?.value||'';
  S.assignmentSession = await api('/api/session',{method:'POST',body:JSON.stringify({bank_id:'assignment',mode,types,chapters:ch?[ch]:[],count:cnt||'all'})});
  S.assignmentIdx=0; S.assignmentResults={}; render();
}

async function recommendPractice() {
  if (!isLoggedIn()) { toast('请先登录'); S.modal='login'; render(); return; }
  try {
    const d = await api('/api/recommend/questions',{method:'POST',body:JSON.stringify({count:15})});
    if (!d.questions?.length) { toast('暂无推荐题目，请先练习一些题目'); return; }
    const ids = d.questions.map(q=>q.id);
    S.session = await api('/api/session',{method:'POST',body:JSON.stringify({mode:'random',question_ids:ids,count:'all'})});
    S.idx=0; S.results={}; S.tab='practice'; render();
  } catch(e) { toast(e.message); }
}

// ═══ Answer Submission ═══
async function submitBankAnswer() {
  const q = S.session.questions[S.idx]; const ans = collectAnswer('bank',q.qtype);
  if (!ans||(Array.isArray(ans)&&!ans.length)){toast('请先作答');return;}
  const r = await api('/api/answer',{method:'POST',body:JSON.stringify({question_id:q.id,answer:ans})});
  S.results[`bank-${q.id}`]=r; await refreshStats(); render();
}
async function submitAssignmentAnswer() {
  const q = S.assignmentSession?.questions?.[S.assignmentIdx]; if (!q) return;
  const ans = collectAnswer('assignment',q.qtype);
  if (!ans||(Array.isArray(ans)&&!ans.length)){toast('请先作答');return;}
  const r = await api('/api/answer',{method:'POST',body:JSON.stringify({bank_id:'assignment',question_id:q.id,answer:ans})});
  S.assignmentResults[`assignment-${q.id}`]=r; await refreshStats(); render();
}
function showAssignmentAnswer(qid) {
  const q = S.assignmentSession?.questions?.find(q=>Number(q.id)===Number(qid)); if (!q) return;
  S.assignmentResults[`assignment-${q.id}`]={kind:'answer',answer:q.answer,answer_source:q.answer_source}; render();
}
async function gradeAssignment() {
  const q = S.assignmentSession?.questions?.[S.assignmentIdx]; if (!q) return;
  const ans = collectAnswer('assignment',q.qtype); if (!ans){toast('请先作答');return;}
  const model = document.querySelector('#aModel')?.value||S.config.default_model; S.loading=true; render();
  try { S.assignmentResults[`assignment-${q.id}`] = await api('/api/assignment/grade',{method:'POST',body:JSON.stringify({question_id:q.id,answer:ans,model})}); } finally { S.loading=false; render(); }
}
async function gradeDiscussion() {
  const did = Number(document.querySelector('#discSelect')?.value);
  const model = document.querySelector('#discModel')?.value;
  const ans = document.querySelector('#discAnswer')?.value.trim(); if (!ans){toast('请先作答');return;}
  S.loading=true; render();
  try { S.discussionResult = await api('/api/discussion/grade',{method:'POST',body:JSON.stringify({discussion_id:did,model,answer:ans})}); } finally { S.loading=false; render(); }
}

// ═══ AI ═══
async function generateAI() {
  const model = document.querySelector('#aiGenModel')?.value; const qtype = document.querySelector('#aiGenType')?.value;
  S.loading=true; render();
  try { const d = await api('/api/ai/generate',{method:'POST',body:JSON.stringify({model,qtype})}); S.aiQuestion = d.question; S.results={...S.results,['ai-']:undefined}; } finally { S.loading=false; render(); }
}
async function submitAIAnswer() {
  const q = S.aiQuestion; if (!q) return;
  const ans = collectAnswer('ai',q.qtype); if (!ans||(Array.isArray(ans)&&!ans.length)){toast('请先作答');return;}
  const r = await api('/api/ai/answer',{method:'POST',body:JSON.stringify({ai_question_id:q.id,answer:ans})});
  S.results[`ai-${q.id}`]=r; render();
}

// ═══ WebSocket Tutor ═══
function connectWsTutor() {
  if (S.ws && (S.ws.readyState === WebSocket.OPEN || S.ws.readyState === WebSocket.CONNECTING)) return;
  if (S.wsReconnectTimer) { clearTimeout(S.wsReconnectTimer); S.wsReconnectTimer = null; }
  try {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws/tutor`;
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => {
      S.wsConnected = true;
      if (S.token && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type:'auth',token:S.token}));
      }
      updateWsIndicator();
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'delta') {
          S.tutorStreamContent = (S.tutorStreamContent||'') + (data.content||'');
          // Update the last assistant bubble in-place without full re-render for performance
          const chatArea = document.querySelector('#tutorChat');
          if (chatArea) {
            let lastBubble = chatArea.querySelector('.chat-msg.assistant:last-of-type .chat-bubble');
            if (!lastBubble) {
              // First delta: create a new assistant message
              S.tutorMessages.push({role:'assistant',content:S.tutorStreamContent});
              S.tutorLoading = false;
              render();
              return;
            }
            lastBubble.innerHTML = renderRich(S.tutorStreamContent);
            chatArea.scrollTop = chatArea.scrollHeight;
          }
        } else if (data.type === 'done') {
          S.tutorConvId = data.conversation_id;
          S.tutorLoading = false;
          S.tutorStreamContent = '';
          updateWsIndicator();
        } else if (data.type === 'error') {
          S.tutorMessages.push({role:'assistant',content:data.error||'AI服务暂时不可用。'});
          S.tutorLoading = false;
          S.tutorStreamContent = '';
          render();
        }
      } catch(e) { /* ignore parse errors */ }
    };
    ws.onclose = () => {
      S.wsConnected = false;
      updateWsIndicator();
      S.ws = null;
      // Auto-reconnect after 5s
      S.wsReconnectTimer = setTimeout(() => {
        if (!S.ws || S.ws.readyState !== WebSocket.OPEN) {
          connectWsTutor();
        }
      }, 5000);
    };
    ws.onerror = () => {
      S.wsConnected = false;
      updateWsIndicator();
    };
    S.ws = ws;
  } catch(e) {
    S.wsConnected = false;
  }
}

function sendViaWebSocket(msg) {
  const ws = S.ws;
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify({
    type: 'message',
    message: msg,
    conversation_id: S.tutorConvId,
    token: S.token,
  }));
  S.tutorStreamContent = '';
  return true;
}

function updateWsIndicator() {
  const el = document.querySelector('#wsStatus');
  if (el) {
    el.className = 'ai-status ' + (S.wsConnected ? 'online' : '');
    el.innerHTML = `<span class="dot ${S.wsConnected ? '' : 'offline'}"></span>${S.wsConnected ? 'WS已连接' : 'WS未连接'}`;
  }
}

// ═══ AI Tutor ═══
async function sendTutorMsg() {
  const input = document.querySelector('#tutorInput'); if (!input) return;
  const msg = input.value.trim(); if (!msg||S.tutorLoading) return;
  input.value = ''; S.tutorMessages.push({role:'user',content:msg}); S.tutorLoading=true; render();

  // Try WebSocket first for streaming
  if (S.wsConnected && sendViaWebSocket(msg)) {
    // Response streams in via ws.onmessage above
    setTimeout(()=>{const c=document.querySelector('#tutorChat');if(c)c.scrollTop=c.scrollHeight;},100);
    return;
  }

  // Fall back to REST API
  try {
    const d = await api('/api/ai/tutor',{method:'POST',body:JSON.stringify({message:msg,conversation_id:S.tutorConvId})});
    S.tutorMessages.push({role:'assistant',content:d.reply}); S.tutorConvId = d.conversation_id;
  } catch(e) { S.tutorMessages.push({role:'assistant',content:'抱歉，AI服务暂时不可用。请检查API配置。'}); }
  finally { S.tutorLoading=false; render(); setTimeout(()=>{const c=document.querySelector('#tutorChat');if(c)c.scrollTop=c.scrollHeight;},100); }
}

// ═══ Question AI Modal ═══
function openQuestionAI(qid, bankId='exam') {
  const q = S.session?.questions?.find(q=>Number(q.id)===Number(qid)) || S.wrongItems.map(it=>it.question).find(q=>Number(q.id)===Number(qid));
  if (!q){toast('未找到该题目');return;}
  S.aiModal = {open:true,question:q,bankId,mode:'explain',model:S.config.default_model,message:'',reply:'',error:'',loading:false}; render();
}
async function runQuestionAI(mode) {
  if (!S.aiModal?.question) return;
  const model = document.querySelector('#aiModalModel')?.value||S.config.default_model;
  const msg = document.querySelector('#aiModalMsg')?.value.trim()||'';
  if (mode==='ask'&&!msg){toast('请输入追问');return;}
  const rid = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  S.aiModal = {...S.aiModal,requestId:rid,mode,model,message:msg,reply:'',loading:true,error:''}; render();
  let reply='';
  const isActive = ()=>S.aiModal?.requestId===rid;
  try {
    await streamApi('/api/question/ai/stream',{question_id:S.aiModal.question.id,bank_id:S.aiModal.bankId||'exam',mode,message:msg,model},(e)=>{
      if (e.delta&&isActive()){reply+=e.delta;S.aiModal={...S.aiModal,reply};render();}
    });
    if (!isActive()) return;
    S.aiModal = {...S.aiModal,reply,loading:false}; render();
  } catch(e) {
    if (!isActive()) return;
    S.aiModal = {...S.aiModal,error:e.message,loading:false}; render();
  }
}

// ═══ Wrong ═══
async function loadWrong() { try { S.wrongItems = (await api('/api/wrong')).items||[]; } catch(e) {} }
async function startWrongSession(ids) {
  if (!ids.length){toast('没有可重做的错题');return;}
  S.session = await api('/api/session',{method:'POST',body:JSON.stringify({mode:'wrong',question_ids:ids,count:'all'})});
  S.idx=0; S.results={}; S.tab='practice'; render();
}

// ═══ Config ═══
async function saveConfig() {
  const zk = document.querySelector('#sZhipuKey')?.value.trim()||'';
  const dk = document.querySelector('#sDeepSeekKey')?.value.trim()||'';
  const model = document.querySelector('#sModel')?.value;
  S.config = await api('/api/config',{method:'POST',body:JSON.stringify({zhipu_api_key:zk,deepseek_api_key:dk,model})});
  await refreshStats(); toast('配置已保存','success');
}
async function clearRuntimeKey(provider) {
  S.config = await api('/api/config',{method:'POST',body:JSON.stringify({clear_provider:provider})});
  await refreshStats(); toast('密钥已清除','success');
}

// ═══ Event Binding ═══
function bindEvents() {
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('button'); if (!btn) return;
    try {
      if (btn.dataset.action==='showLogin') { S.modal='login'; render(); }
      else if (btn.dataset.action==='closeModal') { S.modal=null; render(); }
      else if (btn.dataset.action==='closeAiModal') { S.aiModal=null; render(); }
      else if (btn.dataset.action==='profile') { S.tab='profile'; S.modal=null; render(); }
      else if (btn.dataset.action==='recommendPractice') { await recommendPractice(); }
      else if (btn.dataset.action==='generateAI') { S.tab='ai'; render(); }
      else if (btn.dataset.loginTab) {
        const isReg = btn.dataset.loginTab==='register';
        document.querySelectorAll('.login-tab').forEach(t=>t.classList.toggle('active',t.dataset.loginTab===btn.dataset.loginTab));
        document.querySelector('#registerFields').style.display = isReg?'grid':'none';
        const submitBtn = document.querySelector('[data-action="submitLogin"]');
        if (submitBtn) submitBtn.textContent = isReg?'注 册':'登 录';
      }
      else if (btn.dataset.action==='submitLogin') {
        const isReg = document.querySelector('.login-tab.active')?.dataset.loginTab==='register';
        const account = document.querySelector('#loginAccount')?.value.trim();
        const password = document.querySelector('#loginPassword')?.value.trim();
        if (!account||!password){showLoginError('请填写账号和密码');return;}
        if (isReg) {
          const name = document.querySelector('#regName')?.value.trim();
          const phone = document.querySelector('#regPhone')?.value.trim();
          if (!name||!phone){showLoginError('请填写完整信息');return;}
          if (password.length<6){showLoginError('密码长度不能少于6位');return;}
          if (phone.length!==11){showLoginError('请输入正确的11位手机号');return;}
          await handleRegister(account,password,name,phone);
          showLoginSuccess('注册成功！请等待管理员审批后登录。');
          setTimeout(()=>{S.modal=null;render();},2000);
        } else {
          await handleLogin(account,password);
          S.modal=null;
          try { S.profile = (await api('/api/profile')).profile; } catch(x) {}
          render(); toast('登录成功！','success');
        }
      }
      else if (btn.dataset.tab) {
        S.aiModal=null; S.modal=null; S.tab=btn.dataset.tab;
        if (S.tab==='wrong') await loadWrong();
        if (S.tab==='admin') { render(); await loadAdminPanel(); return; }
        render();
      }
      else if (btn.dataset.startMode) await startSession(btn.dataset.startMode);
      else if (btn.dataset.startAssignment) await startAssignmentSession(btn.dataset.startAssignment);
      else if (btn.hasAttribute('data-submit-bank')) await submitBankAnswer();
      else if (btn.hasAttribute('data-submit-assignment')) await submitAssignmentAnswer();
      else if (btn.hasAttribute('data-grade-assignment')) await gradeAssignment();
      else if (btn.dataset.showAssignmentAnswer) showAssignmentAnswer(btn.dataset.showAssignmentAnswer);
      else if (btn.hasAttribute('data-prev-question')) { S.idx=Math.max(0,S.idx-1); render(); }
      else if (btn.hasAttribute('data-next-question')) { S.idx=Math.min(S.session.questions.length-1,S.idx+1); render(); }
      else if (btn.hasAttribute('data-reset-session')) { S.session=null; S.idx=0; render(); }
      else if (btn.hasAttribute('data-prev-assignment')) { S.assignmentIdx=Math.max(0,S.assignmentIdx-1); render(); }
      else if (btn.hasAttribute('data-next-assignment')) { S.assignmentIdx=Math.min(S.assignmentSession.questions.length-1,S.assignmentIdx+1); render(); }
      else if (btn.hasAttribute('data-reset-assignment')) { S.assignmentSession=null; S.assignmentIdx=0; render(); }
      else if (btn.hasAttribute('data-generate-ai')) await generateAI();
      else if (btn.hasAttribute('data-submit-ai')) await submitAIAnswer();
      else if (btn.hasAttribute('data-grade-discussion')) await gradeDiscussion();
      else if (btn.hasAttribute('data-load-wrong')) { await loadWrong(); render(); }
      else if (btn.dataset.redoQuestion) await startWrongSession([Number(btn.dataset.redoQuestion)]);
      else if (btn.hasAttribute('data-redo-all')) await startWrongSession(S.wrongItems.map(it=>it.question.id));
      else if (btn.hasAttribute('data-save-config')) await saveConfig();
      else if (btn.dataset.clearProvider) await clearRuntimeKey(btn.dataset.clearProvider);
      else if (btn.dataset.openQuestionAi) openQuestionAI(btn.dataset.openQuestionAi, btn.dataset.openQuestionBank||'exam');
      else if (btn.dataset.aiAction) await runQuestionAI(btn.dataset.aiAction);
      else if (btn.dataset.action==='resetTutor') { S.tutorMessages=[]; S.tutorConvId=null; render(); }
      else if (btn.dataset.action==='sendTutor') { await sendTutorMsg(); }
    } catch(err) { toast(err.message); }
  });

  // 委托事件：stop-propagation (替代 inline onclick="event.stopPropagation()")
  document.addEventListener('click', (e) => {
    if (e.target.closest('[data-stop-propagation]')) {
      e.stopPropagation();
    }
  });

  // 委托事件：tutor example 按钮 (替代 inline onclick)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-tutor-example]');
    if (btn) {
      const input = document.querySelector('#tutorInput');
      if (input) input.value = btn.dataset.tutorExample;
      sendTutorMsg();
    }
  });

  // 委托事件：管理审批按钮（避免内联onclick的XSS风险）
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-approve-user]');
    if (btn) {
      const uid = parseInt(btn.dataset.approveUser);
      const approved = btn.dataset.approveVal === '1';
      if (!isNaN(uid)) approveUser(uid, approved);
    }
  });

  // 委托事件：tutor input 回车发送 (替代 inline onkeydown)
  document.addEventListener('keydown', (e) => {
    if (e.target?.id==='tutorInput' && e.key==='Enter') {
      e.preventDefault();
      sendTutorMsg();
    }
  });

  document.addEventListener('change', (e) => {
    if (e.target?.id==='discSelect') { S.selectedDiscussionId=Number(e.target.value); S.discussionResult=null; render(); }
  });
}

// ═══ Login helpers ═══
function showLoginError(msg) { const el = document.querySelector('#loginError'); if (el) { el.style.display='block'; el.textContent=msg; } }
function showLoginSuccess(msg) { const el = document.querySelector('#loginSuccess'); if (el) { el.style.display='block'; el.textContent=msg; } }

// ═══ Boot ═══
window.addEventListener('beforeunload', () => {
  if (S.wsReconnectTimer) clearTimeout(S.wsReconnectTimer);
  if (S.ws) { S.ws.onclose = null; S.ws.close(); S.ws = null; }
});
init();
