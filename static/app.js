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
  eventsBound: false,
};

// ═══ API ═══
const API_BASE = String(window.STRUCTMIND_API_BASE || '').replace(/\/$/, '');
async function api(path, opts={}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers||{}) };
  if (S.token) headers['Authorization'] = `Bearer ${S.token}`;
  const res = await fetch(API_BASE + path, { ...opts, headers });
  const data = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error(data.error || `请求失败: ${res.status}`);
  return data;
}

async function streamApi(path, payload, onEvent) {
  const headers = { 'Content-Type': 'application/json' };
  if (S.token) headers['Authorization'] = `Bearer ${S.token}`;
  const res = await fetch(API_BASE + path, { method:'POST', headers, body: JSON.stringify(payload) });
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
  connectWsTutor();
}
async function handleRegister(account, password, name, phone) {
  return api('/api/auth/register', { method:'POST', body: JSON.stringify({account, password, name, phone}) });
}
async function handleLogout() {
  try { await api('/api/auth/logout', { method:'POST' }); } catch(e) {}
  if (S.wsReconnectTimer) { clearTimeout(S.wsReconnectTimer); S.wsReconnectTimer = null; }
  if (S.ws) { S.ws.onclose = null; S.ws.close(); S.ws = null; }
  S.wsConnected = false;
  clearAuth(); S.profile = null; S.tab = 'dashboard'; S.modal = null; render();
}

// ═══ Init ═══
async function init() {
  loadAuth();
  if (S.token) connectWsTutor();
  try {
    const [stats, config, discussions] = await Promise.all([api('/api/stats'), api('/api/config'), api('/api/discussions')]);
    S.stats = stats; S.config = config; S.discussions = discussions.discussions||[];
    S.selectedDiscussionId = S.discussions[0]?.id||null;
    if (isLoggedIn()) {
      try { S.profile = (await api('/api/profile')).profile; } catch(e) {}
    }
    render();
  } catch(e) {
    const app = document.querySelector('#app');
    app.innerHTML = `<main class="boot boot-error" id="main-content"><div class="boot-error-mark" aria-hidden="true">!</div><h1>学习台暂时无法加载</h1><p>请确认服务已启动或网络连接正常，然后重试。</p><button class="btn btn-primary" id="retryBoot">重新加载</button></main>`;
    app.querySelector('#retryBoot')?.addEventListener('click', init, {once:true});
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
  if (!S.eventsBound) bindEvents();
}

function renderShell() {
  const title = pageTitle();
  return `<div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="brand" aria-label="StructMind 数据结构学习工作台">
        <img src="/logo.svg" class="brand-logo" alt="StructMind"/>
        <div><h1>${APP.name}</h1><p>学习工作台</p></div>
      </div>
      <nav class="nav">${navItems().map(([k,l,icon])=>`
        <button class="nav-btn ${S.tab===k?'active':''}" data-tab="${k}" ${S.tab===k?'aria-current="page"':''}>
          <svg class="nav-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${icons[icon]||''}</svg>
          <span>${l}</span>
        </button>`).join('')}</nav>
      <div class="sidebar-system">
        <button class="system-status" data-tab="settings" aria-label="查看系统状态">
          <span class="status-mark ${anyAIConfigured()?'ready':'attention'}" aria-hidden="true"></span>
          <span><strong>系统状态</strong><small>${anyAIConfigured()?`${esc(S.config.default_model)} 可用`:'AI 尚未配置'}</small></span>
        </button>
      </div>
      ${isLoggedIn() ? `
        <div class="sidebar-user">
          <div class="user-avatar">${(S.user.name||'?')[0]}</div>
          <div class="user-copy"><div class="user-name">${esc(S.user.name)}</div><div class="user-role">${isAdmin()?'管理员':'学生'} · 正确率 ${profileAccuracy()}%</div></div>
          <button class="icon-button" data-action="logout" aria-label="退出登录" title="退出登录">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M10 17l5-5-5-5"/><path d="M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/></svg>
          </button>
        </div>` : `
        <button class="btn btn-primary sidebar-login" data-action="showLogin">登录学习</button>`}
    </aside>
    <main class="main" id="main-content" tabindex="-1">
      <header class="topbar">
        <div class="page-heading"><h2>${title.title}</h2><p>${title.subtitle}</p></div>
        <div class="topbar-right">
          ${isAdmin()?`<button class="btn btn-quiet btn-sm" data-tab="admin">管理审批</button>`:''}
          <button class="status-button" data-tab="settings">
            <span id="wsStatus" class="status-mark ${S.wsConnected?'ready':'muted'}" aria-hidden="true"></span>
            <span>${anyAIConfigured()?'AI 导师可用':'配置 AI 导师'}</span>
          </button>
        </div>
      </header>
      <div class="content-area">${renderTab()}</div>
      <footer class="footer"><span>${APP.name} · 数据结构学习工作台</span><a href="https://beian.miit.gov.cn" target="_blank" rel="noopener">湘ICP备2026021754号-2</a></footer>
    </main>
    <nav class="bottom-nav" aria-label="移动端导航">
      ${navItems().filter(([k])=>['dashboard','practice','ai','wrong'].includes(k)).map(([k,l,icon])=>`
        <button class="bottom-nav-item ${S.tab===k?'active':''}" data-tab="${k}" ${S.tab===k?'aria-current="page"':''}>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${icons[icon]||''}</svg>
          <span>${l}</span>
        </button>`).join('')}
    </nav>
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
    <div class="modal" data-stop-propagation role="dialog" aria-modal="true" aria-labelledby="loginTitle">
      <div class="modal-header">
        <div></div>
        <button class="modal-close" data-action="closeModal" aria-label="关闭登录窗口">×</button>
      </div>
      <div class="modal-body">
        <img src="/logo.svg" class="login-logo" alt="StructMind"/>
        <h3 id="loginTitle" style="text-align:center;margin:0">欢迎来到 StructMind</h3>
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
            <div class="inline-notice"><small>注册后需等待管理员审批通过方可登录使用。</small></div>
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
    <div class="modal ai-modal" data-stop-propagation role="dialog" aria-modal="true" aria-labelledby="aiModalTitle">
      <div class="modal-header">
        <div><h3 id="aiModalTitle">题目 AI 辅助</h3><p style="color:var(--muted);font-size:0.85rem">${esc(q.chapter)} · ${esc(q.qtype)} · #${esc(q.source_order||q.id)}</p></div>
        <button class="modal-close" data-action="closeAiModal" aria-label="关闭 AI 辅助窗口">×</button>
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
          <button class="btn btn-primary" data-ai-action="explain" ${anyAIConfigured()&&!m.loading?'':'disabled'}>${m.loading&&m.mode==='explain'?'讲解中...':'讲解这题'}</button>
          <button class="btn btn-soft" data-ai-action="check" ${anyAIConfigured()&&!m.loading?'':'disabled'}>检查题目</button>
          <button class="btn btn-ghost" data-ai-action="ask" ${anyAIConfigured()&&!m.loading?'':'disabled'}>继续追问</button>
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
  const items = [['dashboard','学习台','home'],['practice','题库','play'],['assignment','作业','stack'],['ai','AI 导师','bot'],['wrong','复习','book'],['discussion','讨论题','message'],['audit','导入审计','shield'],['settings','AI 配置','settings']];
  return items;
}

function pageTitle() {
  const m = {dashboard:['学习台','从下一项任务开始，保持稳定练习'],practice:['正式题库','按原题顺序、随机或薄弱项开始练习'],assignment:['课程作业','对照 Word 作业答案，使用 AI 参考批改'],ai:['AI 导师','通过解释、追问和提示建立理解'],discussion:['讨论题','梳理思路，获取 AI 参考反馈'],wrong:['复习','从最近错题和薄弱知识点重新开始'],settings:['AI 配置','管理模型与运行时密钥'],audit:['导入审计','核对题库来源、修复记录和答案处理'],admin:['管理审批','审核注册申请与用户状态']};
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
  const attempts = isLoggedIn() ? (S.profile?.total_attempts||0) : 0;
  const weak = (S.profile?.weak_concepts||[]).slice(0,3);
  const nextTitle = weak.length ? `复习 ${weak[0]}` : attempts ? '继续正式题库练习' : '完成第一组正式题库练习';
  const nextReason = weak.length ? `最近记录显示 ${weak[0]} 需要加强，先练 10 题巩固概念。` : '从正式题库开始，系统会根据作答生成你的学习建议。';
  return `<div class="learning-home">
    <section class="next-session" aria-labelledby="next-session-title">
      <div class="next-session-copy">
        <span class="source-badge source-official">正式题库</span>
        <h3 id="next-session-title">${esc(nextTitle)}</h3>
        <p>${esc(nextReason)}</p>
        <div class="session-facts"><span>10 题</span><span>约 12 分钟</span><span>${attempts?`累计 ${attempts} 题`:'首次练习'}</span></div>
      </div>
      <div class="next-session-action">
        ${isLoggedIn()
          ? `<button class="btn btn-primary" data-action="${weak.length?'recommendPractice':''}" ${weak.length?'':'data-tab="practice"'}>开始这组练习</button>`
          : `<button class="btn btn-primary" data-action="showLogin">登录后开始</button>`}
        <button class="text-button" data-tab="practice">自己选择题目</button>
      </div>
    </section>

    <div class="home-columns">
      <section class="study-agenda" aria-labelledby="agenda-title">
        <div class="section-heading"><div><h3 id="agenda-title">今日计划</h3><p>保持一段完整、可完成的学习节奏</p></div><span class="progress-label">${attempts?'进行中':'未开始'}</span></div>
        <div class="agenda-list">
          <button class="agenda-row" data-tab="practice"><span class="agenda-index">1</span><span><strong>正式题库练习</strong><small>完成 10 道客观题并查看解析</small></span><span class="agenda-meta">12 分钟</span></button>
          <button class="agenda-row" data-tab="wrong"><span class="agenda-index">2</span><span><strong>复习最近错题</strong><small>${S.wrongItems.length?`${S.wrongItems.length} 道错题等待重做`:'答错的题目会自动加入复习'}</small></span><span class="agenda-meta">8 分钟</span></button>
          <button class="agenda-row" data-tab="ai"><span class="agenda-index">3</span><span><strong>向 AI 导师复述概念</strong><small>用自己的话解释一个薄弱知识点</small></span><span class="agenda-meta">5 分钟</span></button>
        </div>
      </section>

      <aside class="progress-summary" aria-labelledby="progress-title">
        <div class="section-heading"><div><h3 id="progress-title">学习进展</h3><p>${attempts?'根据已完成练习更新':'完成练习后生成画像'}</p></div></div>
        ${S.profile?`<div class="progress-primary"><strong>${profileAccuracy()}%</strong><span>累计正确率</span></div>
          <dl class="progress-details"><div><dt>已练习</dt><dd>${S.profile.total_attempts||0} 题</dd></div><div><dt>连续学习</dt><dd>${S.profile.practice_streak||0} 天</dd></div></dl>
          <div class="concept-summary"><span>建议优先</span><div>${weak.length?weak.map(x=>`<button data-action="recommendPractice">${esc(x)}</button>`).join(''):'<small>继续练习以识别薄弱项</small>'}</div></div>`
          : `<div class="progress-empty"><strong>从一次练习开始</strong><p>提交答案后，这里会显示正确率、薄弱知识点和下一步建议。</p><button class="btn btn-quiet" data-tab="practice">选择练习</button></div>`}
      </aside>
    </div>

    <section class="trust-strip" aria-label="题库可信度">
      <div><span>正式客观题</span><strong>${c.objective}</strong></div>
      <div><span>Word 作业题</span><strong>${a?.counts?.questions||0}</strong></div>
      <div><span>讨论题</span><strong>${c.discussion}</strong></div>
      <div><span>导入校验</span><strong>${intOk?'已通过':'需复核'}</strong></div>
      <button class="text-button" data-tab="audit">查看导入审计</button>
    </section>
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
  return `<div class="question-workspace">
    <article class="question-stage">${renderQuestion(q,'bank')}</article>
    <aside class="question-context" aria-label="本组练习信息">
      <div class="context-head"><span class="source-badge source-official">正式题库</span><strong>${esc(mn)}</strong></div>
      <div class="context-progress"><span>${S.idx+1} / ${S.session.questions.length}</span><small>本组进度</small></div>
      <div class="progress" aria-label="完成 ${prog}%"><div class="progress-bar" style="width:${prog}%"></div></div>
      <dl class="context-details"><div><dt>本组题量</dt><dd>${S.session.count}</dd></div><div><dt>筛选可用</dt><dd>${S.session.total_available}</dd></div></dl>
      <div class="context-actions">
        <button class="btn btn-ghost btn-sm" data-prev-question ${S.idx===0?'disabled':''}>上一题</button>
        <button class="btn btn-quiet btn-sm" data-next-question ${S.idx>=S.session.questions.length-1?'disabled':''}>下一题</button>
        <button class="btn btn-danger btn-sm" data-reset-session>结束本组</button>
      </div>
    </aside>
  </div>`;
}

function renderPracticeSetup() {
  const available = S.stats.counts?.objective||0;
  return `<section class="practice-builder" aria-labelledby="practice-builder-title">
    <div class="builder-heading"><span class="source-badge source-official">正式题库 · ${available} 题</span><h3 id="practice-builder-title">创建一组练习</h3><p>选择范围后开始。顺序练习完全遵循原题顺序，随机和推荐也只使用正式题库。</p></div>
    <div class="builder-form">
      <fieldset class="choice-fieldset"><legend>题型</legend><div class="filter-choices">${['单选题','多选题','填空题','判断题'].map(t=>`<label class="filter-choice"><input type="checkbox" name="pType" value="${t}" checked/><span>${t}</span></label>`).join('')}</div></fieldset>
      <div class="builder-fields">
        <div class="form-group"><label class="form-label" for="pChapter">章节范围</label><select class="form-select" id="pChapter"><option value="">全部章节</option>${Object.keys(S.stats.chapters).map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div>
        <div class="form-group"><label class="form-label" for="pCount">练习题量</label><input class="form-input" id="pCount" type="number" min="1" max="${available}" placeholder="留空时使用全部题目"/></div>
      </div>
    </div>
    <div class="builder-summary"><div><strong>${available}</strong><span>道正式客观题可筛选</span></div><p>标准答案来自原始题库，AI 仅用于辅助讲解。</p></div>
    <div class="builder-actions">
      <button class="btn btn-primary" data-start-mode="sequence">开始顺序练习</button>
      <button class="btn btn-quiet" data-start-mode="random">随机出题</button>
      <button class="text-button" data-action="recommendPractice">按薄弱项推荐</button>
    </div>
  </section>`;
}

// ═══ Assignment ═══
function renderAssignment() {
  const bank = S.stats.banks?.assignment||{};
  if (!S.assignmentSession) {
    return `<div class="workspace-grid grid">
      <div class="panel"><div class="panel-inner grid"><h3 style="margin:0">创建作业练习</h3>
        <span class="source-badge source-word">Word 作业题库</span>
        <div>
          <div class="form-label" style="margin-bottom:6px">题型</div>
          <div style="display:flex;gap:6px">${['简答题','填空题'].map(t=>`<label class="tag" style="cursor:pointer;padding:6px 12px"><input type="checkbox" name="aType" value="${t}" checked style="accent-color:var(--primary)"/> ${t}</label>`).join('')}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div class="form-group"><label class="form-label">分组</label><select class="form-select" id="aChapter"><option value="">全部</option>${Object.keys(bank.chapters||{}).map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div>
          <div class="form-group"><label class="form-label">题量</label><input class="form-input" id="aCount" type="number" min="1" placeholder="留空=全部"/></div>
        </div>
        <div class="action-row" style="display:flex;gap:8px">
          <button class="btn btn-primary" data-start-assignment="sequence">顺序练习</button>
          <button class="btn btn-soft" data-start-assignment="random">随机出题</button>
        </div>
      </div></div>
      <aside class="panel"><div class="panel-inner side-list">
        ${sideRow('作业题',bank.counts?.questions||0)}${sideRow('Word答案',bank.counts?.word_answers||0)}${sideRow('AI参考',bank.counts?.ai_reference_answers||0)}
        <span style="color:var(--muted);line-height:1.65">简答题可使用 <span class="source-badge source-ai">AI 参考</span> 批改。AI 内容不会标记为 Word 来源答案。</span>
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
  const examples = ['二叉树的三种遍历分别解决什么问题？','哈希冲突的处理方法该怎样比较？','快速排序最坏情况为什么是 O(n²)？','怎样判断一个有向图是否存在环？'];
  return `<div class="tutor-workspace">
    <section class="tutor-main" aria-label="AI 导师对话">
      <div class="tutor-toolbar"><div><span class="source-badge source-ai">AI 导师</span><strong>苏格拉底式引导</strong></div><button class="text-button" data-action="resetTutor">开始新对话</button></div>
      <div class="tutor-thread" id="tutorChat" aria-live="polite">
        ${S.tutorMessages.length===0?`<div class="tutor-empty"><div class="tutor-mark" aria-hidden="true">S</div><h3>你现在想弄懂什么？</h3><p>描述概念、题目或你的思路。我会先确认你卡住的位置，再给出解释或下一步提示。</p><div class="example-list">${examples.map(q=>`<button data-tutor-example="${escAttr(q)}">${q}<span aria-hidden="true">↗</span></button>`).join('')}</div></div>`:''}
        ${S.tutorMessages.map(m=>`<article class="tutor-message ${m.role}"><div class="message-label">${m.role==='user'?'你':'AI 导师'}</div><div class="message-content">${renderRich(m.content)}</div></article>`).join('')}
        ${S.tutorLoading?`<article class="tutor-message assistant streaming"><div class="message-label">AI 导师</div><div class="message-content">${S.tutorStreamContent?renderRich(S.tutorStreamContent):'<span class="stream-status">正在梳理你的问题</span>'}<span class="stream-caret" aria-hidden="true"></span></div></article>`:''}
      </div>
      <div class="tutor-composer-wrap">
        <div class="tutor-intents" aria-label="学习意图">${[
          ['解释概念','请用直观例子解释：'],['检查思路','请检查我的思路并指出关键问题：'],['逐步提示','请不要直接给答案，逐步提示我：'],['生成变式题','请根据这个知识点生成一道变式题：']
        ].map(([label,prompt])=>`<button class="tutor-intent" data-tutor-fill="${escAttr(prompt)}">${label}</button>`).join('')}</div>
        <div class="tutor-composer ${!anyAIConfigured()?'disabled':''}">
          <textarea id="tutorInput" rows="1" placeholder="写下问题、题目或你的思考" ${!anyAIConfigured()?'disabled':''}></textarea>
          <div class="composer-footer"><span>${anyAIConfigured()?'Enter 发送，Shift + Enter 换行':'配置模型后可开始对话'}</span><button class="send-button" data-action="sendTutor" ${S.tutorLoading||!anyAIConfigured()?'disabled':''} aria-label="发送问题"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19V5"/><path d="m6 11 6-6 6 6"/></svg></button></div>
        </div>
        ${!anyAIConfigured()?`<div class="inline-notice"><span>AI 导师尚未配置。</span><button class="text-button" data-tab="settings">前往配置</button></div>`:''}
      </div>
    </section>
    <aside class="tutor-context">
      <div class="context-head"><span>当前方式</span><strong>引导式学习</strong></div>
      <p>导师会优先追问你的理解，再按需要解释概念、拆解步骤或生成变式题。</p>
      <dl><div><dt>对话</dt><dd>${S.tutorConvId?`#${S.tutorConvId}`:'新对话'}</dd></div><div><dt>模型</dt><dd>${anyAIConfigured()?esc(S.config.default_model):'未配置'}</dd></div><div><dt>内容来源</dt><dd>AI 参考</dd></div></dl>
      <div class="context-note"><strong>答案边界</strong><span>导师回复用于理解与复习，不替代正式题库的标准答案。</span></div>
    </aside>
  </div>`;
}

// ═══ Admin ═══
function renderAdmin() {
  if (!isAdmin()) return '<div class="empty"><p>仅管理员可访问</p></div>';
  return `<div class="panel"><div class="panel-inner" id="adminPanel">
    <h3 style="margin:0 0 8px">管理审批</h3>
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
      ${pu.length===0?'<div class="empty"><p>没有待审批的申请</p></div>':`<div class="grid" style="gap:8px">${pu.map(u=>`<div class="card" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
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
      <button class="btn btn-primary" data-grade-discussion ${anyAIConfigured()&&!S.loading?'':'disabled'}>${S.loading?'批改中':'获取 AI 参考反馈'}</button>
      ${S.discussionResult?renderDiscResult(S.discussionResult):''}
    </div></div>
    <aside class="panel"><div class="panel-inner side-list"><span class="source-badge source-ai">AI 参考</span><strong>讨论题反馈</strong><span style="color:var(--muted);line-height:1.65">讨论题没有 Word 标准答案。AI 反馈只用于复习，不计入正式题库正确率。</span></div></aside>
  </div>`;
}

// ═══ Wrong ═══
function renderWrong() {
  const ids = S.wrongItems.map(it=>it.question.id);
  return `<div class="panel"><div class="panel-inner grid">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
      <div><h3 style="margin:0">最近错题</h3><p style="color:var(--muted);margin:4px 0 0">按题目去重，重做后重新判断掌握情况</p></div>
      <div style="display:flex;gap:8px"><button class="btn btn-quiet btn-sm" data-load-wrong>刷新列表</button><button class="btn btn-primary btn-sm" data-redo-all ${ids.length?'':'disabled'}>开始本组复习</button></div>
    </div>
    ${S.wrongItems.length?S.wrongItems.map(it=>renderWrongItem(it)).join(''):'<div class="empty"><p class="empty-title">还没有错题记录</p><p class="empty-desc">完成正式题库练习后，答错的题目会自动进入这里。</p></div>'}
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
    <div style="display:flex;gap:8px;margin-top:8px"><button class="btn btn-primary btn-sm" data-redo-question="${q.id}">重做本题</button><button class="btn btn-ghost btn-sm" data-open-question-ai="${q.id}">AI 解析</button></div>
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
        <button class="btn btn-primary" data-save-config>保存配置</button>
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
    <div class="section-heading"><div><h3>导入审计</h3><p>所有修复记录都保留原题号、来源和处理方式</p></div><span class="source-badge source-official">来源可追溯</span></div>
    <div class="table-wrap"><table><thead><tr><th>题库</th><th>题号</th><th>章节</th><th>题型</th><th>问题</th><th>处理</th></tr></thead><tbody>${audit.length?audit.map(a=>`<tr><td>${esc(a.bank_label)}</td><td>${esc(a.question_id||'')}</td><td>${esc(a.chapter||'')}</td><td>${esc(a.qtype||'')}</td><td>${esc(a.issue)}</td><td>${esc(a.handling)}</td></tr>`).join(''):'<tr><td colspan="6">未发现导入异常</td></tr>'}</tbody></table></div>
  </div></div>`;
}

// ═══ Question Rendering (shared) ═══
function renderQuestion(q, src, bankId=q.bank_id||'exam') {
  const rk = `${src}-${q.id}`, result = src==='assignment'? S.assignmentResults[rk] : S.results[rk];
  const canAI = ['bank','assignment'].includes(src) && Number.isFinite(Number(q.id));
  const sourceClass = src==='bank'?'source-official':q.answer_source==='word_answer'?'source-word':'source-ai';
  const sourceLabel = src==='bank'?'正式题库':q.answer_source==='word_answer'?'Word 作业答案':'AI 参考';
  return `<div class="question-head"><div>${renderQuestionTags(q)}<span class="source-badge ${sourceClass}">${sourceLabel}</span></div><div class="question-tools"><span class="question-number">第 ${esc(q.source_order||q.id)} 题</span>${canAI?`<button class="btn btn-ghost btn-sm" data-open-question-ai="${q.id}" data-open-question-bank="${bankId}">AI 解析</button>`:''}</div></div>
    ${q.ai_completed?`<div class="inline-notice">${esc(q.completion_note||'本题显示文本已由 AI 补全表修复，标准答案不变')}</div>`:''}
    <div class="stem">${renderRich(q.stem)}</div>
    ${(q.images||[]).map(s=>`<img src="${esc(s)}" style="max-width:min(100%,600px);border-radius:8px;border:1px solid var(--border);margin:10px 0" alt="配图"/>`).join('')}
    ${renderAnswerControl(q,src)}
    ${src==='assignment'?renderAssignmentActions(q):`<div class="question-submit"><button class="btn btn-primary" data-submit-${src}>提交答案</button><span>提交后显示标准答案与解析</span></div>`}
    ${result?(src==='assignment'?renderAssignmentResult(result):renderResult(result)):''}`;
}

function renderQuestionTags(q) {
  return `<div class="question-meta">
    <span>${esc(q.chapter||'AI 出题')}</span><span>${esc(q.qtype)}</span>
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
    <div class="action-row"><button class="btn btn-primary" data-grade-assignment ${anyAIConfigured()&&!S.loading?'':'disabled'}>${S.loading?'批改中':'获取 AI 参考批改'}</button><button class="btn btn-ghost" data-show-assignment-answer="${q.id}">查看来源答案</button></div>`;
  return `<div class="action-row"><button class="btn btn-primary" data-submit-assignment>提交答案</button><button class="btn btn-ghost" data-show-assignment-answer="${q.id}">查看来源答案</button></div>`;
}

function renderResult(r) {
  return `<section class="result ${r.is_correct?'correct':'wrong'}" aria-label="答题结果"><div class="result-head"><span class="result-icon" aria-hidden="true">${r.is_correct?'✓':'×'}</span><div><strong>${r.is_correct?'回答正确':'回答错误'}</strong><span class="source-badge source-official">正式题库标准答案</span></div></div>
    <div class="answer-line"><span>标准答案</span>${renderRich(r.correct_answer)}</div>${r.analysis?`<div class="answer-line"><span>解析</span>${renderRich(r.analysis)}</div>`:''}<div class="result-actions"><button class="btn btn-primary" data-next-question>继续下一题</button></div></section>`;
}

function renderAssignmentResult(r) {
  if (r.kind==='answer') { const isWord=r.answer_source==='word_answer'; return `<div class="result"><span class="source-badge ${isWord?'source-word':'source-ai'}">${isWord?'Word 作业答案':'AI 参考'}</span><div class="answer-line"><span>参考答案</span>${renderRich(r.answer||'暂无')}</div>${!isWord?'<div class="inline-notice">此内容为 AI 参考，不是 Word 来源答案。</div>':''}</div>`; }
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
    <button class="btn btn-primary" data-generate-ai ${anyAIConfigured()&&!S.loading?'':'disabled'}>${S.loading?'生成中...':'生成 AI 变式题'}</button>
    ${S.aiQuestion?`<div class="card" style="margin-top:12px;background:var(--bg)">${renderQuestion(S.aiQuestion,'ai')}</div>`:'<div class="empty" style="margin-top:12px">生成后在此答题，AI解析支持公式与代码渲染</div>'}
  </div>`;
}

// ═══ Helpers ═══
function metric(l,v,n) { return `<div class="metric"><span>${esc(l)}</span><strong>${esc(v)}</strong><span>${esc(n)}</span></div>`; }
function sideRow(l,v) { return `<div class="side-row"><span>${esc(l)}</span><strong>${esc(v)}</strong></div>`; }
function ansSrc(s) { return s==='word_answer'?'Word 作业答案':s==='ai_reference'?'AI 参考':'无来源答案'; }
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
    if (/^\s*#{1,4}\s+/.test(l)){blocks.push(`<h4 style="color:var(--primary-strong);margin:0">${renderInline(l.replace(/^\s*#{1,4}\s+/,''))}</h4>`);i++;continue;}
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
  S.session = await api('/api/session',{method:'POST',body:JSON.stringify({mode,types,chapters:ch?[ch]:[],count:cnt?Number(cnt):null})});
  S.idx=0; S.results={}; render();
}
async function startAssignmentSession(mode) {
  const types = [...document.querySelectorAll('input[name="aType"]:checked')].map(c=>c.value);
  const ch = document.querySelector('#aChapter')?.value||'';
  const cnt = document.querySelector('#aCount')?.value||'';
  S.assignmentSession = await api('/api/session',{method:'POST',body:JSON.stringify({bank_id:'assignment',mode,types,chapters:ch?[ch]:[],count:cnt?Number(cnt):null})});
  S.assignmentIdx=0; S.assignmentResults={}; render();
}

async function recommendPractice() {
  if (!isLoggedIn()) { toast('请先登录'); S.modal='login'; render(); return; }
  try {
    const d = await api('/api/recommend/questions',{method:'POST',body:JSON.stringify({count:15})});
    if (!d.questions?.length) { toast('暂无推荐题目，请先练习一些题目'); return; }
    const ids = d.questions.map(q=>q.id);
    S.session = await api('/api/session',{method:'POST',body:JSON.stringify({mode:'random',question_ids:ids,count:null})});
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
          const chatArea = document.querySelector('#tutorChat');
          if (chatArea) {
            const content = chatArea.querySelector('.tutor-message.streaming .message-content');
            if (content) content.innerHTML = renderRich(S.tutorStreamContent) + '<span class="stream-caret" aria-hidden="true"></span>';
            chatArea.scrollTop = chatArea.scrollHeight;
          }
        } else if (data.type === 'done') {
          S.tutorConvId = data.conversation_id;
          if (S.tutorStreamContent) S.tutorMessages.push({role:'assistant',content:S.tutorStreamContent});
          S.tutorLoading = false;
          S.tutorStreamContent = '';
          render();
        } else if (data.type === 'error') {
          S.tutorMessages.push({role:'assistant',content:data.message||data.error||'AI服务暂时不可用。'});
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
      if (S.token) {
        S.wsReconnectTimer = setTimeout(() => {
          if (S.token && (!S.ws || S.ws.readyState !== WebSocket.OPEN)) connectWsTutor();
        }, 5000);
      }
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
    el.className = `status-mark ${S.wsConnected?'ready':'muted'}`;
    el.setAttribute('aria-label', S.wsConnected?'导师实时连接正常':'导师使用标准连接');
  }
}

// ═══ AI Tutor ═══
async function sendTutorMsg() {
  const input = document.querySelector('#tutorInput'); if (!input) return;
  const msg = input.value.trim(); if (!msg||S.tutorLoading) return;
  input.value = ''; S.tutorMessages.push({role:'user',content:msg}); S.tutorLoading=true; S.tutorStreamContent=''; render();

  // Try WebSocket first for streaming
  if (S.wsConnected && sendViaWebSocket(msg)) {
    setTimeout(()=>{const c=document.querySelector('#tutorChat');if(c)c.scrollTop=c.scrollHeight;},100);
    return;
  }

  // Try SSE streaming via streamApi
  let streamContent = '';
  try {
    await streamApi('/api/ai/tutor/stream', {message:msg, conversation_id:S.tutorConvId}, (e) => {
      if (e.type === 'delta' && e.content) {
        streamContent += e.content;
        S.tutorStreamContent = streamContent;
        const chatArea = document.querySelector('#tutorChat');
        if (chatArea) {
          const content = chatArea.querySelector('.tutor-message.streaming .message-content');
          if (content) content.innerHTML = renderRich(streamContent) + '<span class="stream-caret" aria-hidden="true"></span>';
          chatArea.scrollTop = chatArea.scrollHeight;
        }
      } else if (e.type === 'done') {
        S.tutorConvId = e.conversation_id || S.tutorConvId;
      } else if (e.type === 'error') {
        throw new Error(e.message || 'Agent执行失败');
      }
    });
    // Finalize: push complete message to history
    if (streamContent) {
      S.tutorMessages.push({role:'assistant',content:streamContent});
    }
  } catch(e) {
    // SSE stream failed, fall back to REST API
    try {
      const d = await api('/api/ai/tutor',{method:'POST',body:JSON.stringify({message:msg,conversation_id:S.tutorConvId})});
      S.tutorMessages.push({role:'assistant',content:d.reply}); S.tutorConvId = d.conversation_id;
    } catch(e2) { S.tutorMessages.push({role:'assistant',content:'AI 服务暂时不可用。请检查模型配置或网络连接后重试。'}); }
  } finally {
    S.tutorLoading=false; S.tutorStreamContent=''; render();
    setTimeout(()=>{const c=document.querySelector('#tutorChat');if(c)c.scrollTop=c.scrollHeight;},100);
  }
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
  S.session = await api('/api/session',{method:'POST',body:JSON.stringify({mode:'wrong',question_ids:ids,count:null})});
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
  S.eventsBound = true;
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('button'); if (!btn) return;
    try {
      if (btn.dataset.action==='showLogin') { S.modal='login'; render(); }
      else if (btn.dataset.action==='closeModal') { S.modal=null; render(); }
      else if (btn.dataset.action==='closeAiModal') { S.aiModal=null; render(); }
      else if (btn.dataset.action==='logout') { await handleLogout(); }
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
          showLoginSuccess('注册成功，请等待管理员审批后登录。');
          setTimeout(()=>{S.modal=null;render();},2000);
        } else {
          await handleLogin(account,password);
          S.modal=null;
          try { S.profile = (await api('/api/profile')).profile; } catch(x) {}
          render(); toast('登录成功','success');
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

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-tutor-fill]');
    if (!btn) return;
    const input = document.querySelector('#tutorInput');
    if (input) {
      input.value = btn.dataset.tutorFill;
      input.focus();
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
    if (e.target?.id==='tutorInput' && e.key==='Enter' && !e.shiftKey) {
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
