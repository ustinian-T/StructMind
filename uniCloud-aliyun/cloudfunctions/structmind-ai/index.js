// @ts-nocheck
'use strict';

/**
 * StructMind AI 云函数
 * 处理：AI题目生成、苏格拉底式辅导、讨论题评分
 *
 * 外部AI API配置：
 *   通过云函数环境变量配置:
 *     SM_AI_API_URL   — AI API 地址
 *     SM_AI_API_KEY   — AI API 密钥
 *     SM_AI_MODEL     — 模型名称 (默认: deepseek-chat)
 */

const db = uniCloud.database();
const sessionsCollection = db.collection('structmind_sessions');
const usersCollection = db.collection('structmind_users');
const questionsCollection = db.collection('structmind_questions');
const assignmentsCollection = db.collection('structmind_assignments');
const discussionsCollection = db.collection('structmind_discussions');
const conversationsCollection = db.collection('structmind_ai_conversations');
const conversationSummariesCollection = db.collection('structmind_conversation_summaries');
let learningRules;
try { learningRules = require('structmind-learning-rules'); }
catch (_error) { learningRules = require('../common/structmind-learning-rules'); }
const SESSION_MAX_AGE_MS = Number(process.env.SM_SESSION_MAX_AGE_MS) || 7 * 24 * 60 * 60 * 1000;

// ── AI API 配置 ──
const AI_API_URL = process.env.SM_AI_API_URL || 'https://api.deepseek.com/v1/chat/completions';
const AI_API_KEY = process.env.SM_AI_API_KEY || '';
const AI_MODEL = process.env.SM_AI_MODEL || 'deepseek-chat';

// Tutor Agent 只允许通过 FastAPI 核心执行；该凭据与终端用户 token 分离。
const AGENT_CORE_URL = (process.env.SM_AGENT_CORE_URL || '').replace(/\/+$/, '');
const AGENT_SERVICE_KEY = process.env.SM_AGENT_SERVICE_KEY || '';

// ── 权限验证 ──
async function requireAuth(token) {
  if (!token) throw { code: 401, message: '请先登录' };
  const sessionResult = await sessionsCollection.where({ token }).get();
  if (sessionResult.data.length === 0) throw { code: 401, message: '登录已过期' };
  const session = sessionResult.data[0];
  if ((session.expires_at || session.created_at + SESSION_MAX_AGE_MS) <= Date.now()) {
    await sessionsCollection.where({ token }).remove();
    throw { code: 401, message: '登录已过期' };
  }
  const userResult = await usersCollection.doc(session.user_id).get();
  if (userResult.data.length === 0) throw { code: 401, message: '用户不存在' };
  if (userResult.data[0].status !== 'approved') {
    throw { code: 403, message: '账号未通过审批' };
  }
  return { user: userResult.data[0], userId: userResult.data[0]._id };
}

// ── 调用AI API ──
async function callAI(messages, options = {}) {
  const {
    temperature = 0.7,
    max_tokens = 2048,
    stream = false,
  } = options;

  if (!AI_API_KEY) {
    throw { code: 503, message: 'AI服务未配置API密钥，请设置SM_AI_API_KEY环境变量' };
  }

  const requestBody = {
    model: AI_MODEL,
    messages,
    temperature,
    max_tokens,
    stream: false,
  };

  // 使用 uniCloud HTTP 请求
  const result = await uniCloud.httpclient.request(AI_API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${AI_API_KEY}`,
    },
    data: requestBody,
    dataType: 'json',
    timeout: 60000,
  });

  if (result.status !== 200) {
    console.error('AI API error:', result.status, result.data);
    throw { code: 502, message: 'AI服务调用失败: ' + (result.data?.error?.message || result.status) };
  }

  const responseData = result.data;
  if (!responseData.choices || responseData.choices.length === 0) {
    throw { code: 502, message: 'AI服务返回空结果' };
  }

  return {
    content: responseData.choices[0].message.content,
    usage: responseData.usage || {},
    model: responseData.model,
  };
}

async function callTutorAgent(payload) {
  if (!AGENT_CORE_URL || !AGENT_SERVICE_KEY) {
    throw { code: 503, message: 'Agent核心代理尚未配置' };
  }
  const result = await uniCloud.httpclient.request(
    `${AGENT_CORE_URL}/api/internal/agent/tutor`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-StructMind-Service-Key': AGENT_SERVICE_KEY,
      },
      data: payload,
      dataType: 'json',
      timeout: 70000,
    },
  );
  if (result.status < 200 || result.status >= 300) {
    const detail = result.data?.detail || result.data?.error || result.status;
    throw { code: 502, message: `Agent核心调用失败: ${detail}` };
  }
  const data = result.data || {};
  if (data.protocol !== 'structmind.agent.v1' || !Array.isArray(data.events)) {
    throw { code: 502, message: 'Agent核心返回了不兼容的事件协议' };
  }
  return data;
}

// ── 题目去重检查 ──
async function checkDuplicate(content, collection) {
  // 使用文本相似度简化的去重：检查是否存在内容高度相似的题目
  const words = content.replace(/[^一-龥a-zA-Z0-9]/g, ' ').split(/\s+/).filter(w => w.length > 1);
  if (words.length < 3) return false;

  // 取前5个关键词进行粗筛
  const keywords = words.slice(0, 5).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const regexStr = keywords.join('|');
  const regex = new RegExp(regexStr, 'i');

  const result = await collection.where({
    content: regex,
  }).limit(5).get();

  if (result.data.length === 0) return false;

  // 计算简单的 Jaccard 相似度
  for (const existing of result.data) {
    const existingWords = new Set(
      existing.content.replace(/[^一-龥a-zA-Z0-9]/g, ' ').split(/\s+/).filter(w => w.length > 1)
    );
    const wordSet = new Set(words);
    const intersection = [...wordSet].filter(w => existingWords.has(w)).length;
    const union = new Set([...wordSet, ...existingWords]).size;
    const similarity = union > 0 ? intersection / union : 0;

    if (similarity > 0.7) {
      return { duplicate: true, existing_id: existing._id, similarity };
    }
  }

  return { duplicate: false };
}

// ── 保存对话 ──
async function saveConversation(userId, type, context, messages) {
  const doc = {
    user_id: userId,
    type,            // 'tutor' | 'question_gen' | 'discussion_grade'
    context,          // { chapter, topic, related_question_id, ... }
    messages: messages.map(m => ({
      role: m.role,
      content: m.content,
      timestamp: Date.now(),
    })),
    created_at: Date.now(),
    updated_at: Date.now(),
  };
  const result = await conversationsCollection.add(doc);
  return result.id;
}

// ── 追加对话消息 ──
async function appendToConversation(conversationId, messages) {
  const convResult = await conversationsCollection.doc(conversationId).get();
  if (convResult.data.length === 0) return;

  const existing = convResult.data[0];
  const newMessages = messages.map(m => ({
    role: m.role,
    content: m.content,
    timestamp: Date.now(),
  }));

  await conversationsCollection.doc(conversationId).update({
    messages: [...existing.messages, ...newMessages],
    updated_at: Date.now(),
  });
}

async function refreshRuleSummary(userId, conversationId) {
  const result = await conversationsCollection.doc(conversationId).get();
  const conversation = result.data[0];
  if (!conversation || conversation.user_id !== userId) return null;
  const messages = (conversation.messages || []).map((item, index) => ({
    role: item.role, content: item.content, id: item.id || `${conversationId}:${index + 1}`,
  }));
  const summary = learningRules.summarizeConversation({ messages,
    known_concepts: ['二叉树遍历', '图的遍历', '递归', '栈', '队列', '哈希', '排序'] });
  const existing = (await conversationSummariesCollection.where({
    user_id: userId, conversation_id: conversationId,
  }).get()).data[0];
  const now = Date.now();
  const document = { summary_rule: summary, summary_final: summary,
    generation_method: 'rule', rule_version: learningRules.RULE_VERSION, updated_at: now };
  if (existing) await conversationSummariesCollection.doc(existing._id).update(document);
  else await conversationSummariesCollection.add({ user_id: userId, conversation_id: conversationId,
    ...document, created_at: now });
  return summary;
}

// ── 主函数 ──
exports.main = async (event, context) => {
  const { action, params = {} } = event;
  const now = Date.now();

  try {
    switch (action) {

      // ── AI 题目生成 ──
      case 'generateQuestion': {
        const { user, userId } = await requireAuth(params.token);

        const {
          chapter,
          type = 'single_choice',   // single_choice | multi_choice | true_false | fill_blank
          difficulty = 3,            // 1-5
          count = 1,                 // 一次生成几道
          extra_requirements = '',   // 额外的生成要求
          auto_import = false,       // 是否自动导入题库
        } = params;

        if (!chapter) throw { code: 400, message: '请指定章节' };
        if (count < 1 || count > 10) throw { code: 400, message: '生成数量应在1-10之间' };

        const typeLabels = {
          single_choice: '单选题',
          multi_choice: '多选题',
          true_false: '判断题',
          fill_blank: '填空题',
        };
        const difficultyLabels = { 1: '基础', 2: '简单', 3: '中等', 4: '较难', 5: '困难' };

        const systemPrompt = `你是一位专业的数学教育工作者，擅长根据教学大纲设计高质量的数学题目。
你需要生成${count}道${typeLabels[type] || type}，难度为${difficultyLabels[difficulty] || difficulty}，所属章节为"${chapter}"。

生成规则：
1. 题目内容要严谨、准确，符合数学规范
2. 如果是选择题，选项要有迷惑性，但只有一个正确选项
3. 如果是填空题，答案要明确
4. 每道题都要有详细的解析
5. 题目要原创，避免与常见题库重复
6. 难度级别：${difficulty}/5

${extra_requirements ? `额外要求：${extra_requirements}` : ''}

请以JSON数组格式返回，每个元素结构如下：
{
  "content": "题目正文",
  "options": [{"key": "A", "value": "选项内容"}],   // 仅选择题需要
  "answer": "正确答案",
  "explanation": "详细解析",
  "difficulty": ${difficulty},
  "tags": ["标签1", "标签2"]
}`;

        const messages = [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: `请为章节"${chapter}"生成${count}道${typeLabels[type] || type}` },
        ];

        const aiResult = await callAI(messages, { temperature: 0.8, max_tokens: 4096 });

        // 解析AI返回的JSON
        let generatedQuestions = [];
        try {
          // 尝试提取JSON数组
          const jsonMatch = aiResult.content.match(/\[[\s\S]*\]/);
          if (jsonMatch) {
            generatedQuestions = JSON.parse(jsonMatch[0]);
          } else {
            // 尝试整体解析
            generatedQuestions = JSON.parse(aiResult.content);
          }
        } catch (parseErr) {
          console.error('Failed to parse AI response:', aiResult.content);
          return {
            code: 500,
            message: 'AI返回格式解析失败',
            data: { raw_response: aiResult.content },
          };
        }

        if (!Array.isArray(generatedQuestions) || generatedQuestions.length === 0) {
          return { code: 500, message: 'AI未生成有效题目', data: { raw_response: aiResult.content } };
        }

        // 去重检查
        const dedupResults = [];
        const finalQuestions = [];
        for (const q of generatedQuestions) {
          const dupCheck = await checkDuplicate(q.content, questionsCollection);
          dedupResults.push({ question: q.content.substring(0, 80), is_duplicate: dupCheck.duplicate, similarity: dupCheck.similarity });
          if (!dupCheck.duplicate) {
            finalQuestions.push(q);
          }
        }

        // 自动导入到题库
        const importResults = [];
        const publishDenied = Boolean(auto_import && user.role !== 'admin');
        if (auto_import && user.role === 'admin' && finalQuestions.length > 0) {
          for (const q of finalQuestions) {
            const doc = {
              type,
              chapter,
              difficulty: q.difficulty || difficulty,
              content: q.content,
              options: q.options || [],
              answer: q.answer || '',
              explanation: q.explanation || '',
              tags: q.tags || [],
              source: 'ai_generated',
              created_at: now,
              updated_at: now,
            };
            const addResult = await questionsCollection.add(doc);
            importResults.push({ id: addResult.id, content: q.content.substring(0, 80) });
          }
        }

        // 保存对话
        const convId = await saveConversation(userId, 'question_gen', { chapter, type, difficulty }, [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: `请为章节"${chapter}"生成${count}道${typeLabels[type] || type}` },
          { role: 'assistant', content: aiResult.content },
        ]);

        return {
          code: 0,
          message: `成功生成${generatedQuestions.length}道题目，${dedupResults.filter(r => r.is_duplicate).length}道被去重`,
          data: {
            conversation_id: convId,
            generated: generatedQuestions,
            final_questions: finalQuestions,
            dedup: dedupResults,
            imported: importResults,
            publish_denied: publishDenied,
            tokens_used: aiResult.usage,
          },
        };
      }

      // ── 苏格拉底式AI辅导 ──
      case 'tutor': {
        const { userId } = await requireAuth(params.token);

        let conversation_id = params.conversation_id;
        const {
          message,
          question_id,
          chapter,
          language = 'zh',
          mode = 'standard',
          model,
        } = params;

        if (!message) throw { code: 400, message: '请输入问题' };

        let questionContext = {};
        if (question_id) {
          const qResult = await questionsCollection.doc(question_id).get();
          if (qResult.data.length > 0) {
            const q = qResult.data[0];
            questionContext = {
              type: q.type,
              content: q.content,
              options: q.options || [],
              chapter: q.chapter || chapter || '',
            };
          }
        }

        let historyMessages = [];
        if (conversation_id) {
          const convResult = await conversationsCollection.doc(conversation_id).get();
          if (convResult.data.length === 0) {
            throw { code: 404, message: '对话不存在' };
          }
          const conversation = convResult.data[0];
          if (conversation.user_id !== userId) {
            throw { code: 403, message: '无权访问此对话' };
          }
          historyMessages = (conversation.messages || [])
            .filter(item => item.role === 'user' || item.role === 'assistant')
            .map(item => ({ role: item.role, content: item.content }));
        }

        const agentResult = await callTutorAgent({
          external_user_id: userId,
          message,
          history: historyMessages,
          question_context: JSON.stringify({ chapter: chapter || '', question: questionContext }),
          conversation_id,
          question_id,
          mode: mode === 'multi-agent' || mode === 'multi_agent' ? 'multi_agent' : 'standard',
          model,
        });

        const assistantMessage = agentResult.events
          .filter(item => item.type === 'delta' && typeof item.content === 'string')
          .map(item => item.content)
          .join('') || agentResult.reply || agentResult.message || '';
        if (!assistantMessage) throw { code: 502, message: 'Agent核心未返回导师回复' };

        const newMessages = [
          { role: 'user', content: message, timestamp: now },
          { role: 'assistant', content: assistantMessage, timestamp: now },
        ];

        if (conversation_id) {
          await appendToConversation(conversation_id, newMessages);
        } else {
          conversation_id = await saveConversation(userId, 'tutor', {
            chapter,
            question_id,
            language,
            mode,
          }, newMessages);
        }
        await refreshRuleSummary(userId, conversation_id);

        return {
          code: 0,
          data: {
            conversation_id,
            protocol: agentResult.protocol,
            events: agentResult.events,
            message: assistantMessage,
            context: {
              chapter,
              question_id,
              mode,
            },
          },
        };
      }

      // ── AI 讨论题评分 ──
      case 'gradeDiscussion': {
        const { userId } = await requireAuth(params.token);

        const {
          discussion_id,        // 讨论题ID
          user_answer,          // 用户答案
          record_id,            // 答题记录ID（用于回写分数）
        } = params;

        if (!user_answer) throw { code: 400, message: '缺少用户答案' };
        if (!discussion_id && !params.reference_points) {
          throw { code: 400, message: '缺少讨论题ID或参考要点' };
        }

        // 获取讨论题信息
        let discussion = null;
        let referencePoints = params.reference_points || [];
        if (discussion_id) {
          const discResult = await discussionsCollection.doc(discussion_id).get();
          if (discResult.data.length > 0) {
            discussion = discResult.data[0];
            referencePoints = discussion.reference_points || referencePoints;
          }
        }

        const systemPrompt = `你是一位数学教育评分专家，负责对学生的讨论题答案进行评分。

评分标准（满分10分）：
- 观点正确性（0-4分）：答案中的数学观点是否准确
- 论证完整性（0-3分）：论证过程是否完整、逻辑清晰
- 表达严谨性（0-2分）：数学语言和符号使用是否规范
- 深度与创新（0-1分）：是否有深入的思考或独特的见解

请以JSON格式返回评分结果：
{
  "score": 8,
  "max_score": 10,
  "breakdown": {
    "correctness": 3,
    "completeness": 3,
    "rigor": 1,
    "depth": 1
  },
  "feedback": "总体评价...",
  "strengths": ["优点1", "优点2"],
  "improvements": ["改进建议1", "改进建议2"],
  "model_answer": "参考答案概要..."
}

${referencePoints.length > 0 ? `参考要点：\n${referencePoints.map((p, i) => `${i + 1}. ${p}`).join('\n')}` : ''}
${discussion ? `题目：${discussion.content}` : ''}`;

        const userPrompt = `请对以下学生的讨论题答案进行评分：\n\n${user_answer}`;

        const messages = [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt },
        ];

        const aiResult = await callAI(messages, {
          temperature: 0.3,
          max_tokens: 2048,
        });

        // 解析评分结果
        let gradeResult;
        try {
          const jsonMatch = aiResult.content.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            gradeResult = JSON.parse(jsonMatch[0]);
          } else {
            gradeResult = JSON.parse(aiResult.content);
          }
        } catch (parseErr) {
          console.error('Failed to parse grade result:', aiResult.content);
          return {
            code: 500,
            message: '评分结果解析失败',
            data: { raw_response: aiResult.content },
          };
        }

        // 回写到答题记录
        if (record_id) {
          const recordsCollection = db.collection('structmind_practice_records');
          await recordsCollection.doc(record_id).update({
            score: gradeResult.score,
            max_score: gradeResult.max_score || 10,
            is_correct: (gradeResult.score || 0) >= 6,
            ai_feedback: gradeResult.feedback || '',
            ai_breakdown: gradeResult.breakdown || {},
            graded_by: 'ai',
            graded_at: now,
          });
        }

        // 保存对话
        const convId = await saveConversation(userId, 'discussion_grade', {
          discussion_id,
          record_id,
        }, [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt },
          { role: 'assistant', content: aiResult.content },
        ]);

        return {
          code: 0,
          message: '评分完成',
          data: {
            conversation_id: convId,
            grade: gradeResult,
            tokens_used: aiResult.usage,
          },
        };
      }

      // ── 获取对话历史 ──
      case 'getConversations': {
        const { userId } = await requireAuth(params.token);

        const { type, page = 1, page_size = 10 } = params;
        const conditions = { user_id: userId };
        if (type) conditions.type = type;

        const skip = (page - 1) * page_size;

        const [convResult, countResult] = await Promise.all([
          conversationsCollection
            .where(conditions)
            .orderBy('updated_at', 'desc')
            .skip(skip)
            .limit(page_size)
            .field({ messages: false })  // 列表不返回消息细节
            .get(),
          conversationsCollection.where(conditions).count(),
        ]);

        return {
          code: 0,
          data: {
            conversations: convResult.data,
            total: countResult.total,
            page,
            page_size,
            total_pages: Math.ceil(countResult.total / page_size),
          },
        };
      }

      // ── 获取对话详情 ──
      case 'getConversationDetail': {
        const { userId } = await requireAuth(params.token);
        const { conversation_id } = params;

        if (!conversation_id) throw { code: 400, message: '缺少对话ID' };

        const convResult = await conversationsCollection.doc(conversation_id).get();
        if (convResult.data.length === 0) {
          throw { code: 404, message: '对话不存在' };
        }

        if (convResult.data[0].user_id !== userId) {
          throw { code: 403, message: '无权查看此对话' };
        }

        return {
          code: 0,
          data: { conversation: convResult.data[0] },
        };
      }

      default:
        return { code: 404, message: '未知操作: ' + action };
    }
  } catch (e) {
    if (e.code && e.message) return e;
    console.error('AI error:', e);
    return { code: 500, message: 'AI服务出错: ' + (e.message || '未知错误') };
  }
};
