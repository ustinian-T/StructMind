// @ts-nocheck
'use strict';

/**
 * StructMind 推送通知云函数
 * 处理：每日练习提醒、新题推送、审批通知
 *
 * UniPush 配置说明：
 *   需要在 uniCloud 后台开启 UniPush 服务，
 *   并在 manifest.json 中配置 push 模块。
 *
 * 调用方式：
 *   action: 'dailyReminder'  — 每日练习提醒
 *   action: 'newQuestion'    — 新题推送
 *   action: 'approvalNotify' — 审批结果通知
 *   action: 'sendToUser'     — 发送给指定用户
 *   action: 'broadcast'      — 全员广播（仅管理员）
 *   action: 'registerDevice' — 注册设备Token
 */

const db = uniCloud.database();
const sessionsCollection = db.collection('structmind_sessions');
const usersCollection = db.collection('structmind_users');
const userStatsCollection = db.collection('structmind_user_stats');
const pushDevicesCollection = db.collection('structmind_push_devices');
const pushLogsCollection = db.collection('structmind_push_logs');
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
  if (userResult.data[0].status !== 'approved') throw { code: 403, message: '账号未通过审批' };
  return { user: userResult.data[0], userId: userResult.data[0]._id };
}

async function requireAdmin(token) {
  const { user, userId } = await requireAuth(token);
  if (user.role !== 'admin') {
    throw { code: 403, message: '仅管理员可执行此操作' };
  }
  return { user, userId };
}

// ── UniPush 发送函数 ──
// uniCloud 内置 UniPush 支持，通过 uniCloud.push 调用
async function sendPushMessage(pushData) {
  const {
    client_ids = [],      // 设备 clientid 列表
    title,
    content,
    payload = {},
    options = {},
  } = pushData;

  if (client_ids.length === 0) {
    console.log('[Push] No client_ids, skipping');
    return { sent: 0, skipped: 0, reason: 'no_devices' };
  }

  // 检查 UniPush 是否可用
  if (typeof uniCloud.push === 'undefined') {
    console.log('[Push] UniPush not available');
    return { sent: 0, skipped: client_ids.length, reason: 'unipush_unavailable' };
  }

  try {
    const result = await uniCloud.push.sendMessage({
      title,
      content,
      payload: JSON.stringify(payload),
      options: {
        ...options,
        // 厂商通道配置
        phone: true,        // 手机端
        PC: false,          // PC端
      },
      push_clientid: client_ids,
    });

    return {
      sent: client_ids.length,
      skipped: 0,
      result,
    };
  } catch (e) {
    console.error('[Push] Send failed:', e.message);

    // 如果是部分失败，尝试逐个发送
    if (client_ids.length > 1) {
      console.log('[Push] Retrying individually...');
      let sent = 0;
      let skipped = 0;
      for (const cid of client_ids) {
        try {
          await uniCloud.push.sendMessage({
            title,
            content,
            payload: JSON.stringify(payload),
            push_clientid: [cid],
          });
          sent++;
        } catch (err) {
          skipped++;
        }
      }
      return { sent, skipped, reason: 'partial_failure' };
    }

    return { sent: 0, skipped: client_ids.length, reason: e.message };
  }
}

// ── 获取用户推送设备 ──
async function getUserDevices(userId) {
  const result = await pushDevicesCollection
    .where({ user_id: userId, enabled: true })
    .get();
  return result.data.map(d => d.client_id).filter(Boolean);
}

// ── 获取所有活跃用户设备 ──
async function getAllActiveDevices() {
  const result = await pushDevicesCollection
    .where({ enabled: true })
    .field({ client_id: true })
    .get();
  return result.data.map(d => d.client_id).filter(Boolean);
}

// ── 记录推送日志 ──
async function logPush(type, userId, title, content, result) {
  await pushLogsCollection.add({
    type,
    user_id: userId,
    title,
    content,
    sent: result.sent || 0,
    skipped: result.skipped || 0,
    reason: result.reason || '',
    created_at: Date.now(),
  });
}

// ── 构建消息内容 ──
function buildReminderMessage(stats) {
  const totalAttempted = stats.total_questions_attempted || 0;
  const dailyGoal = stats.daily_goal || 20;
  const todayAttempted = stats.today_attempted || 0;
  const remaining = Math.max(0, dailyGoal - todayAttempted);

  const messages = [
    '📚 学习提醒：新的一天，新的进步！',
    '💪 每日一练：坚持就是胜利！',
    '🎯 今日目标还未完成，快去练习吧！',
    '📐 数学之美，在于日日精进。',
    '⏰ 别忘了今天的数学练习哦～',
  ];

  const motivationalMsg = messages[Math.floor(Math.random() * messages.length)];

  return {
    title: 'StructMind 学习提醒',
    content: remaining > 0
      ? `${motivationalMsg}\n今日目标还剩${remaining}道题，快去完成吧！`
      : '🎉 今日练习目标已达成！继续保持！',
    payload: {
      type: 'reminder',
      page: '/pages/practice/practice',
      remaining,
      daily_goal: dailyGoal,
    },
  };
}

// ── 主函数 ──
exports.main = async (event, context) => {
  const { action, params = {} } = event;
  const now = Date.now();

  try {
    switch (action) {

      // ── 每日练习提醒 ──
      // 通常由定时触发器调用，也可手动触发
      case 'dailyReminder': {
        // 定时任务调用时可能没有token
        let adminUserId = null;
        if (params.token) {
          const auth = await requireAdmin(params.token);
          adminUserId = auth.userId;
        }

        const {
          target_users = [],   // 空=全部开启了通知的用户
          custom_message = '',
        } = params;

        // 获取开启了通知且设置了提醒时间的用户
        const nowHour = new Date().getHours();
        const nowMinute = new Date().getMinutes();
        const timeStr = `${String(nowHour).padStart(2, '0')}:${String(nowMinute).padStart(2, '0')}`;

        // 查找设置了此刻提醒的用户
        const targetStats = await userStatsCollection
          .where({
            notification_enabled: true,
            notification_time: timeStr,
          })
          .get();

        // 如果指定了特定用户，过滤
        let targetUserIds = targetStats.data.map(s => s.user_id);
        if (target_users.length > 0) {
          targetUserIds = targetUserIds.filter(id => target_users.includes(id));
        }

        const results = [];
        let totalSent = 0;
        let totalSkipped = 0;

        for (const stats of targetStats.data) {
          if (!targetUserIds.includes(stats.user_id)) continue;

          const deviceIds = await getUserDevices(stats.user_id);
          if (deviceIds.length === 0) {
            totalSkipped++;
            continue;
          }

          // 获取今日答题数
          const todayStart = new Date();
          todayStart.setHours(0, 0, 0, 0);
          const todayRecords = await db.collection('structmind_practice_records')
            .where({
              user_id: stats.user_id,
              created_at: db.command.gte(todayStart.getTime()),
            })
            .count();

          const enrichedStats = {
            ...stats,
            today_attempted: todayRecords.total,
          };

          const msg = buildReminderMessage(enrichedStats);
          msg.content = custom_message || msg.content;

          const result = await sendPushMessage({
            client_ids: deviceIds,
            title: msg.title,
            content: msg.content,
            payload: msg.payload,
          });

          await logPush('daily_reminder', stats.user_id, msg.title, msg.content, result);
          results.push({ user_id: stats.user_id, ...result });
          totalSent += result.sent;
          totalSkipped += result.skipped;
        }

        return {
          code: 0,
          message: `提醒发送完成：成功 ${totalSent}，跳过 ${totalSkipped}`,
          data: {
            total_users: targetStats.data.length,
            total_sent: totalSent,
            total_skipped: totalSkipped,
            results,
          },
        };
      }

      // ── 新题推送 ──
      case 'newQuestion': {
        await requireAdmin(params.token);

        const {
          question_id,
          chapter,
          custom_title = '',
          custom_content = '',
          target_chapter = '',  // 推送给关注该章节的用户
        } = params;

        let title = custom_title || '📝 新题目上线啦！';
        let content = custom_content || `章节"${chapter || '未知'}"新增了题目，快来挑战吧！`;

        let deviceIds = [];
        if (target_chapter) {
          // 推送给在统计中关注该章节的用户
          const regex = new RegExp(target_chapter.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
          const targetStats = await userStatsCollection
            .where({
              notification_enabled: true,
              focus_chapters: regex,
            })
            .get();

          for (const stats of targetStats.data) {
            const devices = await getUserDevices(stats.user_id);
            deviceIds.push(...devices);
          }
        } else {
          // 推送给所有开启通知的用户
          deviceIds = await getAllActiveDevices();
        }

        // 去重
        deviceIds = [...new Set(deviceIds)];

        const result = await sendPushMessage({
          client_ids: deviceIds,
          title,
          content,
          payload: {
            type: 'new_question',
            page: '/pages/practice/practice',
            question_id,
            chapter,
          },
        });

        await logPush('new_question', null, title, content, result);

        return {
          code: 0,
          message: `新题推送完成：成功 ${result.sent}，跳过 ${result.skipped}`,
          data: result,
        };
      }

      // ── 审批结果通知 ──
      case 'approvalNotify': {
        await requireAdmin(params.token);

        const { user_id, status, reason = '' } = params;

        if (!user_id) throw { code: 400, message: '缺少用户ID' };
        if (!status) throw { code: 400, message: '缺少审批状态' };

        const deviceIds = await getUserDevices(user_id);
        if (deviceIds.length === 0) {
          return {
            code: 0,
            message: '该用户无可用推送设备',
            data: { sent: 0, reason: 'no_devices' },
          };
        }

        let title, content;
        if (status === 'approved') {
          title = '🎉 账号已通过审批';
          content = '恭喜！您的StructMind账号已通过审批，现在可以开始学习了！';
        } else if (status === 'rejected') {
          title = '账号审批结果';
          content = `很遗憾，您的账号注册未通过审批。${reason ? '原因：' + reason : ''}`;
        } else {
          title = '账号状态更新';
          content = `您的账号状态已更新为：${status}`;
        }

        const payload = {
          type: 'approval',
          page: status === 'approved' ? '/pages/index/index' : '/pages/auth/auth',
          status,
        };

        const result = await sendPushMessage({
          client_ids: deviceIds,
          title,
          content,
          payload,
        });

        await logPush('approval', user_id, title, content, result);

        return {
          code: 0,
          message: '审批通知已发送',
          data: result,
        };
      }

      // ── 发送给指定用户 ──
      case 'sendToUser': {
        await requireAdmin(params.token);

        const {
          user_id,
          title = 'StructMind 通知',
          content = '',
          payload: customPayload = {},
        } = params;

        if (!user_id) throw { code: 400, message: '缺少用户ID' };
        if (!content) throw { code: 400, message: '缺少通知内容' };

        const deviceIds = await getUserDevices(user_id);
        if (deviceIds.length === 0) {
          return {
            code: 0,
            message: '该用户无可用推送设备',
            data: { sent: 0, reason: 'no_devices' },
          };
        }

        const payload = {
          type: 'custom',
          ...customPayload,
        };

        const result = await sendPushMessage({
          client_ids: deviceIds,
          title,
          content,
          payload,
        });

        await logPush('custom', user_id, title, content, result);

        return {
          code: 0,
          message: '通知已发送',
          data: result,
        };
      }

      // ── 全员广播 ──
      case 'broadcast': {
        await requireAdmin(params.token);

        const {
          title = 'StructMind 公告',
          content = '',
          payload: customPayload = {},
        } = params;

        if (!content) throw { code: 400, message: '缺少通知内容' };

        const deviceIds = await getAllActiveDevices();

        const payload = {
          type: 'broadcast',
          ...customPayload,
        };

        const result = await sendPushMessage({
          client_ids: deviceIds,
          title,
          content,
          payload,
        });

        await logPush('broadcast', null, title, content, result);

        return {
          code: 0,
          message: `广播发送完成：成功 ${result.sent}，跳过 ${result.skipped}`,
          data: result,
        };
      }

      // ── 注册推送设备 ──
      case 'registerDevice': {
        const { userId } = await requireAuth(params.token);

        const {
          client_id,       // uniPush clientid
          platform,        // 'ios' | 'android' | 'web'
          enabled = true,
        } = params;

        if (!client_id) throw { code: 400, message: '缺少设备标识(client_id)' };

        // 检查是否已注册
        const existing = await pushDevicesCollection
          .where({ user_id: userId, client_id })
          .get();

        if (existing.data.length > 0) {
          // 更新
          await pushDevicesCollection.doc(existing.data[0]._id).update({
            platform: platform || existing.data[0].platform,
            enabled,
            last_active_at: now,
            updated_at: now,
          });
        } else {
          // 新增
          await pushDevicesCollection.add({
            user_id: userId,
            client_id,
            platform: platform || 'unknown',
            enabled,
            created_at: now,
            last_active_at: now,
            updated_at: now,
          });
        }

        return {
          code: 0,
          message: '设备注册成功',
          data: { client_id, platform, enabled },
        };
      }

      // ── 注销推送设备 ──
      case 'unregisterDevice': {
        const { userId } = await requireAuth(params.token);
        const { client_id } = params;

        if (!client_id) throw { code: 400, message: '缺少设备标识' };

        await pushDevicesCollection
          .where({ user_id: userId, client_id })
          .remove();

        return {
          code: 0,
          message: '设备已注销',
        };
      }

      // ── 设置通知偏好 ──
      case 'setNotificationPrefs': {
        const { userId } = await requireAuth(params.token);

        const {
          enabled,
          time,
          types = [],       // ['reminder', 'new_question', 'system']
        } = params;

        const updates = { updated_at: now };
        if (enabled !== undefined) updates.notification_enabled = enabled;
        if (time !== undefined) updates.notification_time = time;
        if (types.length > 0) updates.notification_types = types;

        // 更新用户统计表
        const statsResult = await userStatsCollection
          .where({ user_id: userId })
          .get();

        if (statsResult.data.length > 0) {
          await userStatsCollection.doc(statsResult.data[0]._id).update(updates);
        } else {
          await userStatsCollection.add({
            user_id: userId,
            ...updates,
            total_questions_attempted: 0,
            total_correct: 0,
            total_wrong: 0,
            current_streak: 0,
            longest_streak: 0,
            total_practice_time: 0,
            chapter_stats: {},
            type_stats: {},
            created_at: now,
          });
        }

        return {
          code: 0,
          message: '通知偏好已更新',
          data: updates,
        };
      }

      // ── 获取推送历史 ──
      case 'getPushHistory': {
        const { userId } = await requireAuth(params.token);

        const { page = 1, page_size = 20 } = params;
        const skip = (page - 1) * page_size;

        const [logResult, countResult] = await Promise.all([
          pushLogsCollection
            .where({ user_id: userId })
            .orderBy('created_at', 'desc')
            .skip(skip)
            .limit(page_size)
            .get(),
          pushLogsCollection.where({ user_id: userId }).count(),
        ]);

        return {
          code: 0,
          data: {
            logs: logResult.data,
            total: countResult.total,
            page,
            page_size,
            total_pages: Math.ceil(countResult.total / page_size),
          },
        };
      }

      default:
        return { code: 404, message: '未知操作: ' + action };
    }
  } catch (e) {
    if (e.code && e.message) return e;
    console.error('Push error:', e);
    return { code: 500, message: '推送服务出错: ' + (e.message || '未知错误') };
  }
};
