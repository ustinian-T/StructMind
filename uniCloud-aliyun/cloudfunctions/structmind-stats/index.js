'use strict';

/**
 * StructMind 统计云函数
 * 处理：仪表盘数据、用户画像、排行榜
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

// ── 权限验证 ──
async function requireAuth(token) {
  if (!token) throw { code: 401, message: '请先登录' };
  const sessionResult = await sessionsCollection.where({ token }).get();
  if (sessionResult.data.length === 0) throw { code: 401, message: '登录已过期' };
  const userResult = await usersCollection.doc(sessionResult.data[0].user_id).get();
  if (userResult.data.length === 0) throw { code: 401, message: '用户不存在' };
  if (userResult.data[0].status !== 'approved') {
    throw { code: 403, message: '账号未通过审批' };
  }
  return { user: userResult.data[0], userId: userResult.data[0]._id };
}

// ── 难度标签 ──
const DIFFICULTY_LABELS = { 1: '基础', 2: '简单', 3: '中等', 4: '较难', 5: '困难' };

// ── 时间范围工具 ──
function getTimeRange(range) {
  const now = Date.now();
  const ranges = {
    today: now - 24 * 60 * 60 * 1000,
    week: now - 7 * 24 * 60 * 60 * 1000,
    month: now - 30 * 24 * 60 * 60 * 1000,
    quarter: now - 90 * 24 * 60 * 60 * 1000,
    year: now - 365 * 24 * 60 * 60 * 1000,
  };
  return ranges[range] || ranges.week;
}

// ── 主函数 ──
exports.main = async (event, context) => {
  const { action, params = {} } = event;
  const now = Date.now();

  try {
    switch (action) {

      // ── 管理仪表盘（仅管理员） ──
      case 'dashboard': {
        const { userId, user } = await requireAuth(params.token);
        if (user.role !== 'admin') {
          throw { code: 403, message: '仅管理员可查看仪表盘' };
        }

        const timeRange = getTimeRange(params.range || 'week');

        // 并行获取所有统计
        const [
          userCount,
          approvedCount,
          pendingCount,
          questionCount,
          assignCount,
          discCount,
          recentPracticeSessions,
          recentRecords,
          activeUsersToday,
        ] = await Promise.all([
          usersCollection.count(),
          usersCollection.where({ status: 'approved' }).count(),
          usersCollection.where({ status: 'pending' }).count(),
          questionsCollection.count(),
          assignmentsCollection.count(),
          discussionsCollection.count(),
          practiceSessionsCollection
            .where({ created_at: db.command.gte(timeRange) })
            .count(),
          practiceRecordsCollection
            .where({ created_at: db.command.gte(timeRange) })
            .count(),
          practiceRecordsCollection
            .where({ created_at: db.command.gte(getTimeRange('today')) })
            .field({ user_id: true })
            .get(),
        ]);

        // 今日活跃用户（去重）
        const todayActiveUsers = new Set(
          activeUsersToday.data.map(r => r.user_id)
        ).size;

        // 获取今日答题数据
        const todayRecords = await practiceRecordsCollection
          .where({ created_at: db.command.gte(getTimeRange('today')) })
          .get();
        const todayTotal = todayRecords.data.length;
        const todayCorrect = todayRecords.data.filter(r => r.is_correct === true).length;

        // 获取章节统计
        const allRecords = await practiceRecordsCollection
          .where({ created_at: db.command.gte(timeRange) })
          .get();

        const chapterMap = {};
        for (const r of allRecords.data) {
          if (!r.chapter) continue;
          if (!chapterMap[r.chapter]) {
            chapterMap[r.chapter] = { attempted: 0, correct: 0 };
          }
          chapterMap[r.chapter].attempted++;
          if (r.is_correct) chapterMap[r.chapter].correct++;
        }

        const chapterStats = Object.entries(chapterMap).map(([name, stats]) => ({
          chapter: name,
          attempted: stats.attempted,
          correct: stats.correct,
          accuracy: stats.attempted > 0
            ? Math.round((stats.correct / stats.attempted) * 100)
            : 0,
        }));

        // 获取每日趋势（最近7天）
        const dailyTrend = [];
        for (let i = 6; i >= 0; i--) {
          const dayStart = new Date();
          dayStart.setDate(dayStart.getDate() - i);
          dayStart.setHours(0, 0, 0, 0);
          const dayEnd = new Date(dayStart);
          dayEnd.setDate(dayEnd.getDate() + 1);

          const dayRecords = allRecords.data.filter(r => {
            const t = r.created_at;
            return t >= dayStart.getTime() && t < dayEnd.getTime();
          });

          dailyTrend.push({
            date: `${dayStart.getMonth() + 1}/${dayStart.getDate()}`,
            total: dayRecords.length,
            correct: dayRecords.filter(r => r.is_correct).length,
          });
        }

        return {
          code: 0,
          data: {
            overview: {
              total_users: userCount.total,
              approved_users: approvedCount.total,
              pending_users: pendingCount.total,
              total_questions: questionCount.total + assignCount.total + discCount.total,
              exam_questions: questionCount.total,
              assignment_questions: assignCount.total,
              discussion_questions: discCount.total,
            },
            activity: {
              today_active_users: todayActiveUsers,
              today_questions_answered: todayTotal,
              today_accuracy: todayTotal > 0
                ? Math.round((todayCorrect / todayTotal) * 100)
                : 0,
              recent_sessions: recentPracticeSessions.total,
              recent_records: recentRecords.total,
            },
            chapter_stats: chapterStats,
            daily_trend: dailyTrend,
            generated_at: now,
          },
        };
      }

      // ── 用户画像 ──
      case 'userProfile': {
        const { userId } = await requireAuth(params.token);

        // 获取用户统计
        const statsResult = await userStatsCollection
          .where({ user_id: userId })
          .get();

        if (statsResult.data.length === 0) {
          return {
            code: 0,
            data: {
              profile: {
                total_questions_attempted: 0,
                total_correct: 0,
                total_wrong: 0,
                overall_accuracy: 0,
                current_streak: 0,
                longest_streak: 0,
                total_practice_time: 0,
                chapter_stats: {},
                type_stats: {},
                last_practice_at: null,
              },
              message: '还没有练习记录，开始你的第一次练习吧！',
            },
          };
        }

        const stats = statsResult.data[0];

        // 获取最近的答题记录用于趋势分析
        const recentRecords = await practiceRecordsCollection
          .where({ user_id: userId })
          .orderBy('created_at', 'desc')
          .limit(50)
          .get();

        // 计算最近50题的正确率
        const recentTotal = recentRecords.data.length;
        const recentCorrect = recentRecords.data.filter(r => r.is_correct === true).length;

        // 按难度统计
        const difficultyStats = {};
        for (const r of recentRecords.data) {
          const diff = r.difficulty || 3;
          if (!difficultyStats[diff]) {
            difficultyStats[diff] = { attempted: 0, correct: 0 };
          }
          difficultyStats[diff].attempted++;
          if (r.is_correct) difficultyStats[diff].correct++;
        }

        // 最薄弱章节
        const chapterStats = stats.chapter_stats || {};
        const weakChapters = Object.entries(chapterStats)
          .filter(([, s]) => s.attempted >= 5 && s.accuracy < 60)
          .map(([name, s]) => ({ chapter: name, accuracy: s.accuracy, attempted: s.attempted }))
          .sort((a, b) => a.accuracy - b.accuracy);

        // 最强章节
        const strongChapters = Object.entries(chapterStats)
          .filter(([, s]) => s.attempted >= 5)
          .map(([name, s]) => ({ chapter: name, accuracy: s.accuracy, attempted: s.attempted }))
          .sort((a, b) => b.accuracy - a.accuracy);

        // 学习建议
        const recommendations = [];
        if (weakChapters.length > 0) {
          recommendations.push({
            type: 'focus',
            message: `建议重点复习"${weakChapters[0].chapter}"章节（当前正确率${weakChapters[0].accuracy}%）`,
            chapter: weakChapters[0].chapter,
          });
        }
        if (stats.current_streak > 3) {
          recommendations.push({
            type: 'streak',
            message: `已经连续${stats.current_streak}次正确，继续保持！`,
          });
        }
        if (stats.total_practice_time < 3600) {
          recommendations.push({
            type: 'practice_more',
            message: '累计练习时间还较少，建议每天保持至少30分钟的练习时间',
          });
        }

        const profile = {
          total_questions_attempted: stats.total_questions_attempted || 0,
          total_correct: stats.total_correct || 0,
          total_wrong: stats.total_wrong || 0,
          overall_accuracy: (stats.total_questions_attempted || 0) > 0
            ? Math.round((stats.total_correct / stats.total_questions_attempted) * 100)
            : 0,
          recent_accuracy: recentTotal > 0
            ? Math.round((recentCorrect / recentTotal) * 100)
            : 0,
          current_streak: stats.current_streak || 0,
          longest_streak: stats.longest_streak || 0,
          total_practice_time: stats.total_practice_time || 0,
          total_practice_time_formatted: formatTime(stats.total_practice_time || 0),
          chapter_stats: chapterStats,
          type_stats: stats.type_stats || {},
          difficulty_stats: difficultyStats,
          weak_chapters: weakChapters.slice(0, 5),
          strong_chapters: strongChapters.slice(0, 5),
          recommendations,
          last_practice_at: stats.last_practice_at,
        };

        return {
          code: 0,
          data: { profile },
        };
      }

      // ── 更新用户画像设置 ──
      case 'updateUserProfile': {
        const { userId } = await requireAuth(params.token);

        const allowedFields = [
          'daily_goal',          // 每日目标题数
          'focus_chapters',      // 关注的章节
          'preferred_difficulty',// 偏好难度
          'notification_enabled',// 是否开启通知
          'notification_time',   // 通知时间（HH:mm）
        ];

        const updates = {};
        for (const field of allowedFields) {
          if (params[field] !== undefined) {
            updates[field] = params[field];
          }
        }

        if (Object.keys(updates).length === 0) {
          throw { code: 400, message: '没有可更新的字段' };
        }

        // 获取或创建用户统计
        const statsResult = await userStatsCollection
          .where({ user_id: userId })
          .get();

        if (statsResult.data.length === 0) {
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
            updated_at: now,
          });
        } else {
          await userStatsCollection.doc(statsResult.data[0]._id).update({
            ...updates,
            updated_at: now,
          });
        }

        return {
          code: 0,
          message: '个人设置已更新',
          data: { updated_fields: Object.keys(updates) },
        };
      }

      // ── 排行榜 ──
      case 'leaderboard': {
        await requireAuth(params.token);

        const {
          type = 'accuracy',     // 'accuracy' | 'streak' | 'volume' | 'time'
          page = 1,
          page_size = 20,
          chapter,               // 按章节筛选（可选）
        } = params;

        // 获取所有用户统计数据
        const statsResult = await userStatsCollection
          .field({
            user_id: true,
            total_questions_attempted: true,
            total_correct: true,
            current_streak: true,
            longest_streak: true,
            total_practice_time: true,
            chapter_stats: true,
          })
          .get();

        let leaderboard = [];

        for (const stats of statsResult.data) {
          // 获取用户名
          let userName = '未知用户';
          try {
            const userResult = await usersCollection.doc(stats.user_id).field({ name: true, account: true }).get();
            if (userResult.data.length > 0) {
              userName = userResult.data[0].name || userResult.data[0].account;
            }
          } catch (e) { /* 用户可能被删除 */ }

          const totalAttempted = stats.total_questions_attempted || 0;
          const totalCorrect = stats.total_correct || 0;
          const accuracy = totalAttempted > 0 ? Math.round((totalCorrect / totalAttempted) * 100) : 0;

          // 如果指定了章节，使用章节数据
          let chapterAccuracy = null;
          let chapterAttempted = 0;
          if (chapter && stats.chapter_stats && stats.chapter_stats[chapter]) {
            const cs = stats.chapter_stats[chapter];
            chapterAttempted = cs.attempted || 0;
            chapterAccuracy = chapterAttempted > 0 ? Math.round((cs.correct / chapterAttempted) * 100) : 0;
          }

          const entry = {
            user_id: stats.user_id,
            name: userName,
            total_attempted: totalAttempted,
            total_correct: totalCorrect,
            accuracy,
            current_streak: stats.current_streak || 0,
            longest_streak: stats.longest_streak || 0,
            total_practice_time: stats.total_practice_time || 0,
            total_practice_time_formatted: formatTime(stats.total_practice_time || 0),
          };

          if (chapter) {
            entry.chapter_accuracy = chapterAccuracy;
            entry.chapter_attempted = chapterAttempted;
          }

          leaderboard.push(entry);
        }

        // 至少答题10道才能上榜（按章节筛选时至少在该章节答5道）
        const minAttempts = chapter ? 5 : 10;
        leaderboard = leaderboard.filter(e => {
          if (chapter) return (e.chapter_attempted || 0) >= minAttempts;
          return e.total_attempted >= minAttempts;
        });

        // 排序
        switch (type) {
          case 'accuracy':
            leaderboard.sort((a, b) => chapter
              ? (b.chapter_accuracy || 0) - (a.chapter_accuracy || 0)
              : b.accuracy - a.accuracy);
            break;
          case 'streak':
            leaderboard.sort((a, b) => b.longest_streak - a.longest_streak);
            break;
          case 'volume':
            leaderboard.sort((a, b) => b.total_attempted - a.total_attempted);
            break;
          case 'time':
            leaderboard.sort((a, b) => b.total_practice_time - a.total_practice_time);
            break;
          default:
            leaderboard.sort((a, b) => b.accuracy - a.accuracy);
        }

        // 添加排名
        leaderboard = leaderboard.map((entry, index) => ({
          rank: index + 1,
          ...entry,
        }));

        // 分页
        const total = leaderboard.length;
        const skip = (page - 1) * page_size;
        const paged = leaderboard.slice(skip, skip + page_size);

        return {
          code: 0,
          data: {
            leaderboard: paged,
            total,
            page,
            page_size,
            total_pages: Math.ceil(total / page_size),
            type,
            chapter: chapter || null,
          },
        };
      }

      // ── 用户排名查询 ──
      case 'myRank': {
        const { userId } = await requireAuth(params.token);

        const { type = 'accuracy' } = params;

        // 获取所有用户统计计算排名
        const statsResult = await userStatsCollection
          .field({
            user_id: true,
            total_questions_attempted: true,
            total_correct: true,
            longest_streak: true,
            total_practice_time: true,
          })
          .get();

        const entries = statsResult.data.map(stats => {
          const totalAttempted = stats.total_questions_attempted || 0;
          const totalCorrect = stats.total_correct || 0;
          const accuracy = totalAttempted > 0 ? Math.round((totalCorrect / totalAttempted) * 100) : 0;
          return {
            user_id: stats.user_id,
            total_attempted: totalAttempted,
            accuracy,
            longest_streak: stats.longest_streak || 0,
            total_practice_time: stats.total_practice_time || 0,
          };
        }).filter(e => e.total_attempted >= 10);

        // 排序
        switch (type) {
          case 'streak':
            entries.sort((a, b) => b.longest_streak - a.longest_streak);
            break;
          case 'volume':
            entries.sort((a, b) => b.total_attempted - a.total_attempted);
            break;
          case 'time':
            entries.sort((a, b) => b.total_practice_time - a.total_practice_time);
            break;
          default:
            entries.sort((a, b) => b.accuracy - a.accuracy);
        }

        const myIndex = entries.findIndex(e => e.user_id === userId);
        const myEntry = myIndex >= 0 ? entries[myIndex] : null;

        return {
          code: 0,
          data: {
            rank: myIndex >= 0 ? myIndex + 1 : null,
            total_participants: entries.length,
            percentile: myIndex >= 0 && entries.length > 0
              ? Math.round(((entries.length - myIndex) / entries.length) * 100)
              : null,
            my_stats: myEntry,
            type,
          },
        };
      }

      default:
        return { code: 404, message: '未知操作: ' + action };
    }
  } catch (e) {
    if (e.code && e.message) return e;
    console.error('Stats error:', e);
    return { code: 500, message: '服务器内部错误' };
  }
};

// ── 时间格式化 ──
function formatTime(seconds) {
  if (seconds < 60) return `${seconds}秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}小时${mins}分`;
}
