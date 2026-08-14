// @ts-nocheck
'use strict';

/**
 * API 网关云函数（URL-化）
 * 将 REST API 请求路由到对应的内部云函数，统一前端 /api/* 调用。
 *
 * 部署后需在 uniCloud 控制台开启 URL-化，路径配置为 /api
 */
exports.main = async (event, context) => {
  const { path, httpMethod, headers = {}, body, queryStringParameters = {} } = event;
  const method = (httpMethod || 'GET').toUpperCase();

  // OPTIONS 预检请求
  if (method === 'OPTIONS') {
    return handleOptions();
  }

  // 解析请求体
  let payload = {};
  if (body) {
    try { payload = JSON.parse(body); } catch (e) { payload = {}; }
  }

  // 从 Authorization header 中提取 token
  const authHeader = headers.authorization || headers.Authorization || '';
  const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : (payload.token || '');

  // 将 query 参数合并到 payload
  Object.assign(payload, queryStringParameters);
  if (token) payload.token = token;

  try {
    // ── 路由表 ──
    const result = await routeRequest(method, path, payload, token);
    return result;
  } catch (e) {
    if (e.code && e.message) {
      return {
        mpserverlessComposedResponse: true,
        statusCode: e.code >= 100 && e.code < 600 ? e.code : 500,
        headers: CORS_HEADERS,
        body: JSON.stringify({ error: e.message }),
      };
    }
    return {
      mpserverlessComposedResponse: true,
      statusCode: 500,
      headers: CORS_HEADERS,
      body: JSON.stringify({ error: e.message || '服务器内部错误' }),
    };
  }
};

/**
 * 路由分发：映射 REST 路径 → 云函数 + action
 */
async function routeRequest(method, path, payload, token) {
  // 去掉 /api 前缀
  const normalizedPath = (path || '').replace(/^\/api\/?/, '/');

  // ── 认证相关 ──
  if (normalizedPath === '/auth/login' && method === 'POST') {
    const result = await callFunction('structmind-auth', 'login', { account: payload.account, password: payload.password });
    return ok(result.data);
  }
  if (normalizedPath === '/auth/register' && method === 'POST') {
    const result = await callFunction('structmind-auth', 'register', {
      account: payload.account, password: payload.password,
      name: payload.name, phone: payload.phone,
    });
    return ok(result.data);
  }
  if (normalizedPath === '/auth/logout' && method === 'POST') {
    const result = await callFunction('structmind-auth', 'logout', { token });
    return ok({ ok: true });
  }

  // ── 管理 ──
  if (normalizedPath === '/admin/pending' && method === 'GET') {
    const result = await callFunction('structmind-admin', 'pending', { token });
    return ok({ users: result.data?.users || [] });
  }
  if (normalizedPath === '/admin/users' && method === 'GET') {
    const result = await callFunction('structmind-admin', 'users', { token });
    return ok({ users: result.data?.users || [] });
  }
  if (normalizedPath === '/admin/approve' && method === 'POST') {
    const result = await callFunction('structmind-admin', 'approve', {
      token, user_id: payload.user_id, approved: payload.approved,
    });
    return ok({ user: result.data?.user || null });
  }

  // ── 练习会话 ──
  if (normalizedPath === '/session' && method === 'POST') {
    const result = await callFunction('structmind-practice', 'createSession', { ...payload, token });
    return ok(result.data || result);
  }
  if (normalizedPath === '/answer' && method === 'POST') {
    const result = await callFunction('structmind-practice', 'submitAnswer', {
      token, session_id: payload.session_id, question_id: payload.question_id,
      user_answer: payload.answer, time_spent: payload.time_spent_seconds || payload.time_spent || 0,
      attempt_token: payload.attempt_token,
    });
    return ok(result.data || result);
  }

  const eventMatch = normalizedPath.match(/^\/learning\/events\/([^/]+)$/);
  if (eventMatch && method === 'GET') {
    const result = await callFunction('structmind-learning', 'getEvent', { token, event_id: eventMatch[1] });
    return ok(result.data);
  }
  if (normalizedPath === '/learning/reviews' && method === 'GET') {
    const result = await callFunction('structmind-learning', 'getReviews', { token, at: payload.at });
    return ok(result.data);
  }
  if (normalizedPath === '/learning/reviews/feedback' && method === 'POST') {
    const result = await callFunction('structmind-learning', 'reviewFeedback', { ...payload, token });
    return ok(result.data);
  }
  if (normalizedPath === '/learning/generate-plan' && method === 'POST') {
    const result = await callFunction('structmind-learning', 'savePlan', { ...payload, token });
    return ok(result.data);
  }
  if ((normalizedPath === '/learning/plan' || normalizedPath === '/learning/plans') && method === 'GET') {
    const result = await callFunction('structmind-learning', 'getPlan', { token });
    return ok(normalizedPath.endsWith('/plans') ? { plans: result.data?.plans || [] } : { plan: result.data?.plan || null });
  }
  const summaryMatch = normalizedPath.match(/^\/learning\/conversations\/([^/]+)\/summary$/);
  if (summaryMatch && method === 'POST') {
    const result = await callFunction('structmind-learning', 'summarizeConversation', {
      token, conversation_id: summaryMatch[1],
    });
    return ok(result.data);
  }
  if (normalizedPath === '/learning/notes' && method === 'GET') {
    const result = await callFunction('structmind-learning', 'listNotes', { ...payload, token });
    return ok(result.data);
  }
  if (normalizedPath === '/learning/notes' && method === 'POST') {
    const result = await callFunction('structmind-learning', 'createNote', { ...payload, token });
    return ok(result.data);
  }
  const noteMatch = normalizedPath.match(/^\/learning\/notes\/([^/]+)$/);
  if (noteMatch && method === 'PATCH') {
    const result = await callFunction('structmind-learning', 'updateNote', {
      ...payload, token, note_id: noteMatch[1],
    });
    return ok(result.data);
  }

  // ── 错题 ──
  if (normalizedPath === '/wrong' && method === 'GET') {
    const result = await callFunction('structmind-practice', 'getWrongQuestions', {
      token, page: payload.page || 1, page_size: payload.page_size || 80,
    });
    const questions = result.data?.questions || [];
    const items = questions.map(q => ({
      question: q,
      user_answer: q.user_answer || '',
      created_at: q.wrong_at || Date.now(),
    }));
    return ok({ items });
  }

  // ── 用户画像 ──
  if (normalizedPath === '/profile' && (method === 'GET' || method === 'POST')) {
    const result = await callFunction('structmind-stats', 'userProfile', { token });
    return ok({ profile: result.data?.profile || null });
  }

  // ── AI 对话 ──
  if (normalizedPath === '/ai/tutor' && method === 'POST') {
    const result = await callFunction('structmind-ai', 'tutor', {
      token, message: payload.message,
      conversation_id: payload.conversation_id,
      question_id: payload.question_id,
      chapter: payload.chapter,
    });
    return ok({ reply: result.data?.message || '', conversation_id: result.data?.conversation_id || null });
  }
  if (normalizedPath === '/ai/generate' && method === 'POST') {
    const result = await callFunction('structmind-ai', 'generateQuestion', {
      token, chapter: payload.chapter || '综合', type: payload.qtype || 'single_choice',
      difficulty: payload.difficulty || 3, count: 1,
    });
    const gen = result.data?.generated?.[0] || result.data?.final_questions?.[0] || null;
    return ok({ question: gen });
  }
  if (normalizedPath === '/question/ai' && method === 'POST') {
    const result = await callFunction('structmind-ai', 'questionAI', {
      token, question_id: payload.question_id, mode: payload.mode,
      message: payload.message, model: payload.model,
    });
    return ok(result.data || {});
  }

  // ── 讨论 / 作业评分 ──
  if (normalizedPath === '/discussion/grade' && method === 'POST') {
    const result = await callFunction('structmind-ai', 'gradeDiscussion', {
      token, discussion_id: payload.discussion_id, user_answer: payload.answer,
    });
    return ok({ feedback: result.data?.grade || null });
  }
  if (normalizedPath === '/assignment/grade' && method === 'POST') {
    const result = await callFunction('structmind-ai', 'gradeAssignment', {
      token, assignment_id: payload.assignment_id || payload.question_id,
      user_answer: payload.answer, model: payload.model,
    });
    return ok({ feedback: result.data?.feedback || null,
      provider_id: result.data?.provider_id, model_id: result.data?.model_id });
  }

  // ── 统计 / 仪表盘 ──
  if (normalizedPath === '/stats' && method === 'GET') {
    const dashResult = await callFunction('structmind-stats', 'dashboard', { token, range: 'week' });
    const dash = dashResult.data || {};
    return ok({
      counts: {
        objective: dash.overview?.exam_questions || 0,
        discussion: dash.overview?.discussion_questions || 0,
      },
      chapters: {},
      practice: { attempts: 0, correct: 0 },
      banks: {
        exam: { audit: [], counts: { questions: dash.overview?.exam_questions || 0 } },
        assignment: { audit: [], counts: { questions: dash.overview?.assignment_questions || 0, word_answers: 0, ai_reference_answers: 0 } },
      },
      integrity: {},
    });
  }

  // ── 配置 ──
  if (normalizedPath === '/config' && method === 'GET') {
    const result = await callFunction('structmind-ai', 'getAIConfig', { token });
    return ok(result.data || {});
  }
  if (normalizedPath === '/config' && method === 'POST') {
    let result;
    if (payload.api_key && payload.provider_id) {
      result = await callFunction('structmind-ai', 'saveAIConfig', {
        token, provider_id: payload.provider_id,
        api_key: payload.api_key, model_id: payload.model_id || payload.model,
      });
    } else {
      result = await callFunction('structmind-ai', 'selectAIModel', {
        token, model_id: payload.model_id || payload.model,
      });
    }
    return ok(result.data || {});
  }

  // ── 讨论题列表 ──
  if (normalizedPath === '/discussions' && method === 'GET') {
    return ok({ discussions: [] });
  }

  // ── 推荐 ──
  if (normalizedPath === '/recommend/questions' && method === 'POST') {
    const result = await callFunction('structmind-learning', 'recommend', {
      token, count: payload.count || 15, types: payload.types || [],
    });
    return ok(result.data);
  }

  // ── AI 流式（非流式降级） ──
  if (normalizedPath === '/ai/tutor/stream' && method === 'POST') {
    const result = await callFunction('structmind-ai', 'tutor', {
      token, message: payload.message,
      conversation_id: payload.conversation_id,
    });
    return ok({ reply: result.data?.message || '', conversation_id: result.data?.conversation_id || null });
  }
  if (normalizedPath.startsWith('/question/ai/stream') && method === 'POST') {
    const result = await callFunction('structmind-ai', 'tutor', {
      token, message: `请${payload.mode === 'explain' ? '详细讲解' : payload.mode === 'check' ? '检查' : '回答'}这道题`,
      question_id: payload.question_id,
    });
    return ok({ reply: result.data?.message || '', conversation_id: result.data?.conversation_id || null });
  }

  // ── 404 ──
  return {
    mpserverlessComposedResponse: true,
    statusCode: 404,
    headers: CORS_HEADERS,
    body: JSON.stringify({ error: `未知接口: ${method} ${normalizedPath}` }),
  };
}

/**
 * 调用内部云函数
 */
async function callFunction(name, action, params = {}) {
  const result = await uniCloud.callFunction({
    name,
    data: { action, params },
  });
  const r = result.result || {};
  if (r.code && r.code !== 0) {
    throw { code: r.code >= 100 && r.code < 600 ? r.code : 400, message: r.message || '请求失败' };
  }
  return r;
}

/**
 * 统一成功响应（适配 mpserverless 响应格式）
 */
const CORS_HEADERS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PATCH, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

function ok(data) {
  return {
    mpserverlessComposedResponse: true,
    statusCode: 200,
    headers: CORS_HEADERS,
    body: JSON.stringify(data),
  };
}

// OPTIONS 预检请求
function handleOptions() {
  return {
    mpserverlessComposedResponse: true,
    statusCode: 204,
    headers: CORS_HEADERS,
    body: '',
  };
}
