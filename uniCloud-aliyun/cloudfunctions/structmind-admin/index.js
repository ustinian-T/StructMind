// @ts-nocheck
'use strict';

/**
 * StructMind 管理云函数
 * 仅管理员可调用
 */
const db = uniCloud.database();
const usersCollection = db.collection('structmind_users');
const sessionsCollection = db.collection('structmind_sessions');
const SESSION_MAX_AGE_MS = Number(process.env.SM_SESSION_MAX_AGE_MS) || 7 * 24 * 60 * 60 * 1000;

// 验证管理员身份
async function requireAdmin(token) {
  if (!token) throw { code: 401, message: '请先登录' };
  const sessionResult = await sessionsCollection.where({ token }).get();
  if (sessionResult.data.length === 0) throw { code: 401, message: '登录已过期' };
  const session = sessionResult.data[0];
  if ((session.expires_at || session.created_at + SESSION_MAX_AGE_MS) <= Date.now()) {
    await sessionsCollection.where({ token }).remove();
    throw { code: 401, message: '登录已过期' };
  }
  const userResult = await usersCollection.doc(session.user_id).get();
  if (userResult.data.length === 0 || userResult.data[0].role !== 'admin' || userResult.data[0].status !== 'approved') {
    throw { code: 403, message: '仅管理员可执行此操作' };
  }
  return userResult.data[0];
}

exports.main = async (event, context) => {
  const { action, params = {} } = event || {};
  try {
    // 验证管理员
    await requireAdmin(params.token);

    switch (action) {
      // ── 等待审批列表 ──
      case 'pending': {
        const result = await usersCollection
          .where({ status: 'pending' })
          .orderBy('created_at', 'desc')
          .field({ password_hash: false })
          .get();
        return { code: 0, data: { users: result.data } };
      }

      // ── 全部用户列表 ──
      case 'users': {
        const result = await usersCollection
          .orderBy('created_at', 'desc')
          .field({ password_hash: false })
          .get();
        return { code: 0, data: { users: result.data } };
      }

      // ── 审批用户 ──
      case 'approve': {
        const { user_id, approved } = params;
        if (!user_id) throw { code: 400, message: '缺少用户ID' };
        const status = approved ? 'approved' : 'rejected';
        await usersCollection.doc(user_id).update({ status, updated_at: Date.now() });
        const user = await usersCollection.doc(user_id).field({ password_hash: false }).get();
        return { code: 0, message: approved ? '已通过' : '已拒绝', data: { user: user.data[0] } };
      }

      // ── 封禁/解封用户 ──
      case 'ban': {
        const { user_id, banned } = params;
        if (!user_id) throw { code: 400, message: '缺少用户ID' };
        const status = banned ? 'banned' : 'approved';
        await usersCollection.doc(user_id).update({ status, updated_at: Date.now() });
        return { code: 0, message: banned ? '已封禁' : '已解封' };
      }

      // ── 站点统计 ──
      case 'stats': {
        const [totalResult, pendingResult, approvedResult] = await Promise.all([
          usersCollection.count(),
          usersCollection.where({ status: 'pending' }).count(),
          usersCollection.where({ status: 'approved' }).count(),
        ]);
        return {
          code: 0,
          data: {
            total_users: totalResult.total,
            pending_users: pendingResult.total,
            approved_users: approvedResult.total,
          },
        };
      }

      default:
        return { code: 404, message: '未知操作: ' + action };
    }
  } catch (e) {
    if (e.code && e.message) return e;
    console.error('Admin error:', e);
    return { code: 500, message: '服务器内部错误' };
  }
};
