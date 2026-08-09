'use strict';

/**
 * StructMind 数据导入云函数
 * 将题库数据批量导入到对应的数据库集合中
 *
 * 调用方式：传入 action + 三组题目JSON数组
 *   action: 'importAll'  — 导入全部三类题目
 *   action: 'importExams' — 仅导入考试题
 *   action: 'importAssignments' — 仅导入作业题
 *   action: 'importDiscussions' — 仅导入讨论题
 *   action: 'clearAll'  — 清空所有题目集合（危险操作）
 *
 * params.examQuestions:  考试题数组 (323道)
 * params.assignmentQuestions: 作业题数组 (26道)
 * params.discussionQuestions: 讨论题数组 (35道)
 */

const db = uniCloud.database();
const sessionsCollection = db.collection('structmind_sessions');
const usersCollection = db.collection('structmind_users');

// ── 权限验证 ──
async function requireAdmin(token) {
  if (!token) throw { code: 401, message: '请先登录' };
  const sessionResult = await sessionsCollection.where({ token }).get();
  if (sessionResult.data.length === 0) throw { code: 401, message: '登录已过期' };
  const userResult = await usersCollection.doc(sessionResult.data[0].user_id).get();
  if (userResult.data.length === 0 || userResult.data[0].role !== 'admin') {
    throw { code: 403, message: '仅管理员可执行此操作' };
  }
  return userResult.data[0];
}

// ── 工具函数 ──
function generateId(prefix, index) {
  const padded = String(index + 1).padStart(4, '0');
  return `${prefix}_${padded}`;
}

function isValidQuestion(q) {
  return q && typeof q.content === 'string' && q.content.trim().length > 0;
}

// ── 批量导入（分批处理避免超时） ──
async function batchImport(collection, items, idPrefix, batchSize = 50) {
  const col = db.collection(collection);
  const now = Date.now();
  let imported = 0;
  let skipped = 0;
  const errors = [];

  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    const docs = [];

    for (let j = 0; j < batch.length; j++) {
      const item = batch[j];
      if (!isValidQuestion(item)) {
        skipped++;
        continue;
      }
      docs.push({
        question_id: item.question_id || generateId(idPrefix, imported),
        ...item,
        created_at: now,
        updated_at: now,
      });
    }

    if (docs.length > 0) {
      try {
        // uniCloud 批量添加：逐个添加并在完成后统计
        const addPromises = docs.map(doc => col.add(doc));
        const results = await Promise.allSettled(addPromises);
        results.forEach(r => {
          if (r.status === 'fulfilled') imported++;
          else {
            skipped++;
            errors.push(r.reason);
          }
        });
      } catch (e) {
        errors.push(`批次 ${Math.floor(i / batchSize) + 1} 导入失败: ${e.message}`);
      }
    }
  }

  return { imported, skipped, errors };
}

// ── 清空集合 ──
async function clearCollection(collectionName) {
  const col = db.collection(collectionName);
  // 由于 uniCloud 限制单次删除条数，分页删除
  let deleted = 0;
  const MAX_DELETE = 100;

  while (true) {
    const result = await col.limit(MAX_DELETE).get();
    if (result.data.length === 0) break;

    const deletePromises = result.data.map(doc => col.doc(doc._id).remove());
    const results = await Promise.allSettled(deletePromises);
    deleted += results.filter(r => r.status === 'fulfilled').length;

    if (result.data.length < MAX_DELETE) break;
  }

  return deleted;
}

// ── 校验题目数据 ──
function validateExamQuestion(q) {
  const errors = [];
  if (!q.type) errors.push('缺少题型(type)');
  else {
    const validTypes = ['single_choice', 'multi_choice', 'true_false', 'fill_blank'];
    if (!validTypes.includes(q.type)) errors.push(`无效题型: ${q.type}`);
  }
  if (!q.chapter) errors.push('缺少章节(chapter)');
  if (!q.content) errors.push('缺少题目内容(content)');
  if (!q.answer && q.answer !== 0 && q.answer !== false) errors.push('缺少答案(answer)');
  if (q.type === 'single_choice' || q.type === 'multi_choice') {
    if (!Array.isArray(q.options) || q.options.length < 2) {
      errors.push('选择题缺少选项(options)');
    }
  }
  return errors;
}

function validateAssignmentQuestion(q) {
  const errors = [];
  if (!q.chapter) errors.push('缺少章节(chapter)');
  if (!q.content) errors.push('缺少题目内容(content)');
  if (!q.rubric) errors.push('缺少评分标准(rubric)');
  return errors;
}

function validateDiscussionQuestion(q) {
  const errors = [];
  if (!q.chapter) errors.push('缺少章节(chapter)');
  if (!q.topic) errors.push('缺少话题(topic)');
  if (!q.content) errors.push('缺少题目内容(content)');
  return errors;
}

// ── 主函数 ──
exports.main = async (event, context) => {
  const { action, params = {} } = event;

  try {
    switch (action) {

      // ── 导入全部数据 ──
      case 'importAll': {
        await requireAdmin(params.token);

        const {
          examQuestions = [],
          assignmentQuestions = [],
          discussionQuestions = [],
        } = params;

        const results = {
          exams: { total: examQuestions.length, imported: 0, skipped: 0, validationErrors: [] },
          assignments: { total: assignmentQuestions.length, imported: 0, skipped: 0, validationErrors: [] },
          discussions: { total: discussionQuestions.length, imported: 0, skipped: 0, validationErrors: [] },
        };

        // 校验考试题
        const validExams = [];
        for (let i = 0; i < examQuestions.length; i++) {
          const q = examQuestions[i];
          const vErrors = validateExamQuestion(q);
          if (vErrors.length > 0) {
            results.exams.validationErrors.push({ index: i, question_id: q.question_id, errors: vErrors });
          } else {
            validExams.push(q);
          }
        }
        const examResult = await batchImport('structmind_questions', validExams, 'EXAM');
        results.exams.imported = examResult.imported;
        results.exams.skipped = examResult.skipped + results.exams.validationErrors.length;

        // 校验作业题
        const validAssignments = [];
        for (let i = 0; i < assignmentQuestions.length; i++) {
          const q = assignmentQuestions[i];
          const vErrors = validateAssignmentQuestion(q);
          if (vErrors.length > 0) {
            results.assignments.validationErrors.push({ index: i, question_id: q.question_id, errors: vErrors });
          } else {
            validAssignments.push(q);
          }
        }
        const assignResult = await batchImport('structmind_assignments', validAssignments, 'ASGN');
        results.assignments.imported = assignResult.imported;
        results.assignments.skipped = assignResult.skipped + results.assignments.validationErrors.length;

        // 校验讨论题
        const validDiscussions = [];
        for (let i = 0; i < discussionQuestions.length; i++) {
          const q = discussionQuestions[i];
          const vErrors = validateDiscussionQuestion(q);
          if (vErrors.length > 0) {
            results.discussions.validationErrors.push({ index: i, question_id: q.question_id, errors: vErrors });
          } else {
            validDiscussions.push(q);
          }
        }
        const discResult = await batchImport('structmind_discussions', validDiscussions, 'DISC');
        results.discussions.imported = discResult.imported;
        results.discussions.skipped = discResult.skipped + results.discussions.validationErrors.length;

        const totalImported = results.exams.imported + results.assignments.imported + results.discussions.imported;
        const totalSkipped = results.exams.skipped + results.assignments.skipped + results.discussions.skipped;

        return {
          code: 0,
          message: `导入完成：成功 ${totalImported} 条，跳过 ${totalSkipped} 条`,
          data: {
            summary: {
              total_expected: examQuestions.length + assignmentQuestions.length + discussionQuestions.length,
              total_imported: totalImported,
              total_skipped: totalSkipped,
            },
            details: results,
          },
        };
      }

      // ── 仅导入考试题 ──
      case 'importExams': {
        await requireAdmin(params.token);
        const { examQuestions = [] } = params;
        const validExams = [];
        const validationErrors = [];
        for (let i = 0; i < examQuestions.length; i++) {
          const vErrors = validateExamQuestion(examQuestions[i]);
          if (vErrors.length > 0) {
            validationErrors.push({ index: i, errors: vErrors });
          } else {
            validExams.push(examQuestions[i]);
          }
        }
        const result = await batchImport('structmind_questions', validExams, 'EXAM');
        return {
          code: 0,
          message: `考试题导入完成：成功 ${result.imported}，跳过 ${result.skipped + validationErrors.length}`,
          data: { ...result, validationErrors },
        };
      }

      // ── 仅导入作业题 ──
      case 'importAssignments': {
        await requireAdmin(params.token);
        const { assignmentQuestions = [] } = params;
        const validAssignments = [];
        const validationErrors = [];
        for (let i = 0; i < assignmentQuestions.length; i++) {
          const vErrors = validateAssignmentQuestion(assignmentQuestions[i]);
          if (vErrors.length > 0) {
            validationErrors.push({ index: i, errors: vErrors });
          } else {
            validAssignments.push(assignmentQuestions[i]);
          }
        }
        const result = await batchImport('structmind_assignments', validAssignments, 'ASGN');
        return {
          code: 0,
          message: `作业题导入完成：成功 ${result.imported}，跳过 ${result.skipped + validationErrors.length}`,
          data: { ...result, validationErrors },
        };
      }

      // ── 仅导入讨论题 ──
      case 'importDiscussions': {
        await requireAdmin(params.token);
        const { discussionQuestions = [] } = params;
        const validDiscussions = [];
        const validationErrors = [];
        for (let i = 0; i < discussionQuestions.length; i++) {
          const vErrors = validateDiscussionQuestion(discussionQuestions[i]);
          if (vErrors.length > 0) {
            validationErrors.push({ index: i, errors: vErrors });
          } else {
            validDiscussions.push(discussionQuestions[i]);
          }
        }
        const result = await batchImport('structmind_discussions', validDiscussions, 'DISC');
        return {
          code: 0,
          message: `讨论题导入完成：成功 ${result.imported}，跳过 ${result.skipped + validationErrors.length}`,
          data: { ...result, validationErrors },
        };
      }

      // ── 清空所有题目集合 ──
      case 'clearAll': {
        await requireAdmin(params.token);
        const collections = [
          'structmind_questions',
          'structmind_assignments',
          'structmind_discussions',
        ];
        const results = {};
        for (const name of collections) {
          results[name] = await clearCollection(name);
        }
        return {
          code: 0,
          message: '所有题目集合已清空',
          data: { deleted: results },
        };
      }

      // ── 获取导入统计 ──
      case 'getStats': {
        await requireAdmin(params.token);
        const [examCount, assignCount, discCount] = await Promise.all([
          db.collection('structmind_questions').count(),
          db.collection('structmind_assignments').count(),
          db.collection('structmind_discussions').count(),
        ]);
        return {
          code: 0,
          data: {
            exam_questions: examCount.total,
            assignment_questions: assignCount.total,
            discussion_questions: discCount.total,
            total: examCount.total + assignCount.total + discCount.total,
          },
        };
      }

      default:
        return { code: 404, message: '未知操作: ' + action };
    }
  } catch (e) {
    if (e.code && e.message) return e;
    console.error('Import error:', e);
    return { code: 500, message: '导入出错: ' + (e.message || '未知错误') };
  }
};
