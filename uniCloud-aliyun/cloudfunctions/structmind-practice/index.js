// @ts-nocheck
'use strict';

/**
 * StructMind 练习云函数
 * 处理：创建练习会话、提交答案、获取题目、错题管理
 */

const db = uniCloud.database();
const sessionsCollection = db.collection('structmind_sessions');
const usersCollection = db.collection('structmind_users');
const questionsCollection = db.collection('structmind_questions');
const assignmentsCollection = db.collection('structmind_assignments');
const discussionsCollection = db.collection('structmind_discussions');
const practiceSessionsCollection = db.collection('structmind_practice_sessions');
const practiceRecordsCollection = db.collection('structmind_practice_records');
const userStatsCollection = db.collection('structmind_user_stats');
const SESSION_MAX_AGE_MS = Number(process.env.SM_SESSION_MAX_AGE_MS) || 7 * 24 * 60 * 60 * 1000;

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

// ── 题目难度映射 ──
const DIFFICULTY_LABELS = {
  1: '基础',
  2: '简单',
  3: '中等',
  4: '较难',
  5: '困难',
};

// ── 随机排列 ──
function shuffleArray(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// ── 获取或创建用户统计 ──
async function getOrCreateUserStats(userId) {
  const result = await userStatsCollection.where({ user_id: userId }).get();
  if (result.data.length === 0) {
    const stats = {
      user_id: userId,
      total_questions_attempted: 0,
      total_correct: 0,
      total_wrong: 0,
      current_streak: 0,
      longest_streak: 0,
      total_practice_time: 0,
      chapter_stats: {},
      type_stats: {},
      last_practice_at: null,
      created_at: Date.now(),
      updated_at: Date.now(),
    };
    const addResult = await userStatsCollection.add(stats);
    return { ...stats, _id: addResult.id };
  }
  return result.data[0];
}

// ── 更新用户章节统计 ──
function updateChapterStats(chapterStats, chapter, isCorrect) {
  const stats = chapterStats || {};
  if (!stats[chapter]) {
    stats[chapter] = { attempted: 0, correct: 0, wrong: 0 };
  }
  stats[chapter].attempted++;
  if (isCorrect) stats[chapter].correct++;
  else stats[chapter].wrong++;
  stats[chapter].accuracy = stats[chapter].attempted > 0
    ? Math.round((stats[chapter].correct / stats[chapter].attempted) * 100)
    : 0;
  return stats;
}

function updateTypeStats(typeStats, type, isCorrect) {
  const stats = typeStats || {};
  if (!stats[type]) {
    stats[type] = { attempted: 0, correct: 0, wrong: 0 };
  }
  stats[type].attempted++;
  if (isCorrect) stats[type].correct++;
  else stats[type].wrong++;
  stats[type].accuracy = stats[type].attempted > 0
    ? Math.round((stats[type].correct / stats[type].attempted) * 100)
    : 0;
  return stats;
}

// ── 题目评分 ──
function gradeAnswer(question, userAnswer) {
  // 选择题和判断题：精确匹配
  if (question.type === 'single_choice' || question.type === 'true_false') {
    const normalizedUser = String(userAnswer).trim().toUpperCase();
    const normalizedAnswer = String(question.answer).trim().toUpperCase();
    return {
      is_correct: normalizedUser === normalizedAnswer,
      score: normalizedUser === normalizedAnswer ? 1 : 0,
      max_score: 1,
    };
  }

  // 多选题：比较排序后的答案
  if (question.type === 'multi_choice') {
    const userArr = String(userAnswer).replace(/[^A-Za-z]/g, '').toUpperCase().split('').sort().join('');
    const answerArr = String(question.answer).replace(/[^A-Za-z]/g, '').toUpperCase().split('').sort().join('');
    const isCorrect = userArr === answerArr;
    return {
      is_correct: isCorrect,
      score: isCorrect ? 1 : 0,
      max_score: 1,
    };
  }

  // 填空题：模糊匹配
  if (question.type === 'fill_blank') {
    const userNorm = String(userAnswer).trim().replace(/\s+/g, '');
    const answerNorm = String(question.answer).trim().replace(/\s+/g, '');
    const isCorrect = userNorm === answerNorm;
    return {
      is_correct: isCorrect,
      score: isCorrect ? 1 : 0,
      max_score: 1,
    };
  }

  // 作业题和讨论题：返回待评分状态（由AI或教师评分）
  return {
    is_correct: null,
    score: 0,
    max_score: question.max_score || 10,
    pending_review: true,
  };
}

// ── 主函数 ──
exports.main = async (event, context) => {
  const { action, params = {} } = event;
  const now = Date.now();

  try {
    switch (action) {

      // ── 创建练习会话 ──
      case 'createSession': {
        const { userId } = await requireAuth(params.token);

        const {
          types = ['single_choice', 'multi_choice', 'true_false', 'fill_blank'],
          chapters = [],        // 空数组表示全部章节
          difficulty = [],      // 空数组表示全部难度
          limit = 20,           // 每次练习题目数
          mode = 'sequence',    // 'sequence' | 'random'
          include_wrong = false,// 是否包含错题
        } = params;

        // 构建查询条件
        const conditions = {};
        if (types.length > 0) conditions.type = db.command.in(types);
        if (chapters.length > 0) conditions.chapter = db.command.in(chapters);
        if (difficulty.length > 0) conditions.difficulty = db.command.in(difficulty);

        // 查询符合条件的题目
        let query = questionsCollection.where(conditions);

        // 如果包含错题，先查错题ID
        let wrongQuestionIds = [];
        if (include_wrong) {
          const wrongRecords = await practiceRecordsCollection
            .where({ user_id: userId, is_correct: false })
            .field({ question_id: true })
            .get();
          wrongQuestionIds = [...new Set(wrongRecords.data.map(r => r.question_id))];
          if (wrongQuestionIds.length > 0) {
            query = questionsCollection.where({
              ...conditions,
              question_id: db.command.in(wrongQuestionIds),
            });
          }
        }

        const questionResult = await query.limit(200).get();
        let questions = questionResult.data;

        // 随机模式
        if (mode === 'random') {
          questions = shuffleArray(questions);
        }

        // 限制数量
        questions = questions.slice(0, limit);

        if (questions.length === 0) {
          return { code: 404, message: '没有找到符合条件的题目' };
        }

        // 创建会话
        const sessionData = {
          user_id: userId,
          question_ids: questions.map(q => q._id),
          total: questions.length,
          completed: 0,
          correct: 0,
          wrong: 0,
          mode,
          filters: { types, chapters, difficulty },
          status: 'in_progress',
          created_at: now,
          updated_at: now,
        };

        const sessionResult = await practiceSessionsCollection.add(sessionData);

        // 返回题目（隐藏答案字段）
        const sanitizedQuestions = questions.map(q => {
          const { answer, explanation, ...rest } = q;
          return rest;
        });

        return {
          code: 0,
          message: '练习会话已创建',
          data: {
            session_id: sessionResult.id,
            questions: sanitizedQuestions,
            total: questions.length,
            mode,
          },
        };
      }

      // ── 提交答案 ──
      case 'submitAnswer': {
        const { userId } = await requireAuth(params.token);

        const {
          session_id,
          question_id,
          user_answer,
          time_spent = 0,  // 答题耗时(秒)
        } = params;

        if (!session_id) throw { code: 400, message: '缺少会话ID' };
        if (!question_id) throw { code: 400, message: '缺少题目ID' };

        // 获取题目信息
        const questionResult = await questionsCollection.doc(question_id).get();
        if (questionResult.data.length === 0) {
          throw { code: 404, message: '题目不存在' };
        }
        const question = questionResult.data[0];

        // 获取会话
        const sessionResult = await practiceSessionsCollection.doc(session_id).get();
        if (sessionResult.data.length === 0) {
          throw { code: 404, message: '练习会话不存在' };
        }
        const session = sessionResult.data[0];

        if (session.user_id !== userId) {
          throw { code: 403, message: '无权操作此会话' };
        }

        if (session.status !== 'in_progress') {
          throw { code: 400, message: '该练习会话已结束' };
        }

        // 评分
        const gradeResult = gradeAnswer(question, user_answer);

        // 记录答题记录
        const recordData = {
          session_id,
          user_id: userId,
          question_id,
          question_type: question.type,
          chapter: question.chapter,
          difficulty: question.difficulty,
          user_answer: String(user_answer),
          correct_answer: question.answer,
          is_correct: gradeResult.is_correct,
          score: gradeResult.score,
          max_score: gradeResult.max_score,
          time_spent,
          pending_review: gradeResult.pending_review || false,
          created_at: now,
        };

        await practiceRecordsCollection.add(recordData);

        // 更新会话进度
        const isCorrect = gradeResult.is_correct === true;
        const updateData = {
          completed: session.completed + 1,
          correct: isCorrect ? session.correct + 1 : session.correct,
          wrong: isCorrect ? session.wrong : session.wrong + 1,
          updated_at: now,
        };

        // 全部完成时更新状态
        if (updateData.completed >= session.total) {
          updateData.status = 'completed';
          updateData.accuracy = session.total > 0
            ? Math.round((updateData.correct / session.total) * 100)
            : 0;
        }

        await practiceSessionsCollection.doc(session_id).update(updateData);

        // 更新用户统计
        const userStats = await getOrCreateUserStats(userId);
        const updatedChapterStats = updateChapterStats(
          userStats.chapter_stats, question.chapter, isCorrect
        );
        const updatedTypeStats = updateTypeStats(
          userStats.type_stats, question.type, isCorrect
        );

        // 更新连续正确天数
        let currentStreak = userStats.current_streak || 0;
        if (isCorrect) {
          currentStreak++;
        } else {
          currentStreak = 0;
        }

        await userStatsCollection.doc(userStats._id).update({
          total_questions_attempted: (userStats.total_questions_attempted || 0) + 1,
          total_correct: isCorrect ? (userStats.total_correct || 0) + 1 : (userStats.total_correct || 0),
          total_wrong: isCorrect ? (userStats.total_wrong || 0) : (userStats.total_wrong || 0) + 1,
          current_streak: currentStreak,
          longest_streak: Math.max(currentStreak, userStats.longest_streak || 0),
          total_practice_time: (userStats.total_practice_time || 0) + time_spent,
          chapter_stats: updatedChapterStats,
          type_stats: updatedTypeStats,
          last_practice_at: now,
          updated_at: now,
        });

        // 返回结果
        const response = {
          code: 0,
          message: isCorrect ? '回答正确！' : '回答错误',
          data: {
            is_correct: gradeResult.is_correct,
            score: gradeResult.score,
            max_score: gradeResult.max_score,
            correct_answer: question.answer,
            explanation: question.explanation || '',
            session_progress: {
              completed: updateData.completed,
              total: session.total,
              accuracy: updateData.completed > 0
                ? Math.round((updateData.correct / updateData.completed) * 100)
                : 0,
            },
            streak: currentStreak,
            pending_review: gradeResult.pending_review || false,
          },
        };

        return response;
      }

      // ── 获取题目列表（带筛选） ──
      case 'getQuestions': {
        await requireAuth(params.token);

        const {
          type,
          chapter,
          difficulty,
          keyword,
          page = 1,
          page_size = 20,
          question_ids,       // 指定题目ID列表
          exclude_ids,        // 排除的题目ID列表
        } = params;

        const conditions = {};

        if (type) conditions.type = type;
        if (chapter) conditions.chapter = chapter;
        if (difficulty) conditions.difficulty = difficulty;
        if (question_ids && Array.isArray(question_ids)) {
          conditions._id = db.command.in(question_ids);
        }
        if (exclude_ids && Array.isArray(exclude_ids)) {
          conditions._id = db.command.and([
            conditions._id || { _id: db.command.exists(true) },
            db.command.not(db.command.in(exclude_ids)),
          ]);
        }

        // 关键词搜索
        if (keyword) {
          conditions.content = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
        }

        const skip = (page - 1) * page_size;

        const [questionResult, countResult] = await Promise.all([
          questionsCollection
            .where(conditions)
            .skip(skip)
            .limit(page_size)
            .orderBy('created_at', 'desc')
            .get(),
          questionsCollection.where(conditions).count(),
        ]);

        // 移除答案字段
        const sanitizedQuestions = questionResult.data.map(q => {
          const { answer, explanation, ...rest } = q;
          return rest;
        });

        return {
          code: 0,
          data: {
            questions: sanitizedQuestions,
            total: countResult.total,
            page,
            page_size,
            total_pages: Math.ceil(countResult.total / page_size),
          },
        };
      }

      // ── 获取错题 ──
      case 'getWrongQuestions': {
        const { userId } = await requireAuth(params.token);

        const {
          page = 1,
          page_size = 20,
          chapter,
          type,
          days = 30,          // 最近N天的错题
        } = params;

        const timeThreshold = now - days * 24 * 60 * 60 * 1000;

        // 查询错题记录
        const wrongConditions = {
          user_id: userId,
          is_correct: false,
          created_at: db.command.gte(timeThreshold),
        };

        const wrongResult = await practiceRecordsCollection
          .where(wrongConditions)
          .orderBy('created_at', 'desc')
          .field({ question_id: true, chapter: true, question_type: true, created_at: true })
          .get();

        // 按题目去重，保留最近一次错误
        const wrongMap = new Map();
        for (const record of wrongResult.data) {
          if (!wrongMap.has(record.question_id)) {
            wrongMap.set(record.question_id, record);
          }
        }

        let wrongQuestions = [...wrongMap.values()];

        // 额外筛选
        if (chapter) wrongQuestions = wrongQuestions.filter(r => r.chapter === chapter);
        if (type) wrongQuestions = wrongQuestions.filter(r => r.question_type === type);

        const total = wrongQuestions.length;
        const skip = (page - 1) * page_size;
        const pagedIds = wrongQuestions.slice(skip, skip + page_size).map(r => r.question_id);

        // 获取题目详情（不返回答案）
        if (pagedIds.length === 0) {
          return {
            code: 0,
            data: { questions: [], total: 0, page, page_size, total_pages: 0 },
          };
        }

        const questionResult = await questionsCollection
          .where({ _id: db.command.in(pagedIds) })
          .get();

        // 保持分页顺序
        const questionMap = new Map(questionResult.data.map(q => [q._id, q]));
        const orderedQuestions = pagedIds
          .map(id => questionMap.get(id))
          .filter(Boolean)
          .map(q => {
            const wrongRecord = wrongMap.get(q._id);
            const { answer, explanation, ...rest } = q;
            return {
              ...rest,
              wrong_at: wrongRecord ? wrongRecord.created_at : null,
            };
          });

        return {
          code: 0,
          data: {
            questions: orderedQuestions,
            total,
            page,
            page_size,
            total_pages: Math.ceil(total / page_size),
          },
        };
      }

      // ── 获取用户练习历史 ──
      case 'getHistory': {
        const { userId } = await requireAuth(params.token);

        const { page = 1, page_size = 10 } = params;
        const skip = (page - 1) * page_size;

        const [sessionResult, countResult] = await Promise.all([
          practiceSessionsCollection
            .where({ user_id: userId })
            .orderBy('created_at', 'desc')
            .skip(skip)
            .limit(page_size)
            .get(),
          practiceSessionsCollection.where({ user_id: userId }).count(),
        ]);

        return {
          code: 0,
          data: {
            sessions: sessionResult.data,
            total: countResult.total,
            page,
            page_size,
            total_pages: Math.ceil(countResult.total / page_size),
          },
        };
      }

      // ── 获取练习会话详情 ──
      case 'getSessionDetail': {
        const { userId } = await requireAuth(params.token);
        const { session_id } = params;

        if (!session_id) throw { code: 400, message: '缺少会话ID' };

        const sessionResult = await practiceSessionsCollection.doc(session_id).get();
        if (sessionResult.data.length === 0) {
          throw { code: 404, message: '会话不存在' };
        }

        const session = sessionResult.data[0];
        if (session.user_id !== userId) {
          throw { code: 403, message: '无权查看此会话' };
        }

        // 获取答题记录
        const recordsResult = await practiceRecordsCollection
          .where({ session_id })
          .orderBy('created_at', 'asc')
          .get();

        return {
          code: 0,
          data: {
            session,
            records: recordsResult.data,
          },
        };
      }

      // ── 获取难度标签映射 ──
      case 'getDifficultyLabels': {
        return {
          code: 0,
          data: { labels: DIFFICULTY_LABELS },
        };
      }

      default:
        return { code: 404, message: '未知操作: ' + action };
    }
  } catch (e) {
    if (e.code && e.message) return e;
    console.error('Practice error:', e);
    return { code: 500, message: '服务器内部错误' };
  }
};
