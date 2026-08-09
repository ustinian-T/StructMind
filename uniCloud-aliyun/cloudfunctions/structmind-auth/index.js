'use strict';

/**
 * StructMind 用户认证云函数
 * 处理：注册、登录、获取用户信息
 */
const db = uniCloud.database();
const usersCollection = db.collection('structmind_users');
const sessionsCollection = db.collection('structmind_sessions');
const crypto = require('crypto');

// 密码哈希
function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.pbkdf2Sync(password, salt, 200000, 32, 'sha256').toString('hex');
  return `${salt}$${hash}`;
}

function verifyPassword(password, stored) {
  try {
    const [salt, storedHash] = stored.split('$');
    const hash = crypto.pbkdf2Sync(password, salt, 200000, 32, 'sha256').toString('hex');
    return hash === storedHash;
  } catch (e) {
    return false;
  }
}

function generateToken() {
  return crypto.randomBytes(32).toString('base64url');
}

// 输入验证
function validateAccount(account) {
  if (!account || account.length < 2 || account.length > 32) {
    throw { code: 400, message: '账号长度需在2-32个字符之间' };
  }
  if (!/^[a-zA-Z0-9_@.\-]+$/.test(account)) {
    throw { code: 400, message: '账号只能包含字母、数字、下划线、@、点和短横线' };
  }
  return account.trim();
}

function validatePassword(password) {
  if (!password || password.length < 6 || password.length > 128) {
    throw { code: 400, message: '密码长度需在6-128个字符之间' };
  }
  return password;
}

function validateName(name) {
  name = (name || '').trim();
  if (!name || name.length < 1 || name.length > 50) {
    throw { code: 400, message: '姓名长度需在1-50个字符之间' };
  }
  return name;
}

function validatePhone(phone) {
  phone = (phone || '').trim();
  if (!/^\d{11}$/.test(phone)) {
    throw { code: 400, message: '请输入正确的11位手机号码' };
  }
  return phone;
}

// 管理员配置（从云函数环境变量读取）
const ADMIN_ACCOUNT = process.env.SM_ADMIN_ACCOUNT || 'tanshuhong';
const ADMIN_PASSWORD = process.env.SM_ADMIN_PASSWORD || 'XX05020604';

exports.main = async (event, context) => {
  const { action, params } = event;
  const now = Date.now();

  try {
    switch (action) {
      // ── 注册 ──
      case 'register': {
        const account = validateAccount(params.account);
        const password = validatePassword(params.password);
        const name = validateName(params.name);
        const phone = validatePhone(params.phone);

        // 检查账号是否已存在
        const existing = await usersCollection.where({ account }).get();
        if (existing.data.length > 0) {
          return { code: 409, message: '该账号已被注册' };
        }

        const isAdmin = account === ADMIN_ACCOUNT;
        const userData = {
          account,
          password_hash: hashPassword(password),
          name,
          phone,
          role: isAdmin ? 'admin' : 'student',
          status: isAdmin ? 'approved' : 'pending',
          created_at: now,
          updated_at: now,
        };

        const result = await usersCollection.add(userData);
        return {
          code: 0,
          message: isAdmin ? '管理员账号已创建' : '注册成功，请等待管理员审批',
          data: { id: result.id, account, name, role: userData.role, status: userData.status },
        };
      }

      // ── 登录 ──
      case 'login': {
        const account = validateAccount(params.account);
        const password = params.password || '';

        const userResult = await usersCollection.where({ account }).get();
        if (userResult.data.length === 0) {
          return { code: 401, message: '账号或密码错误' };
        }

        const user = userResult.data[0];
        if (!verifyPassword(password, user.password_hash)) {
          return { code: 401, message: '账号或密码错误' };
        }

        if (user.status === 'pending') {
          return { code: 403, message: '账号正在等待管理员审批' };
        }
        if (user.status === 'rejected') {
          return { code: 403, message: '账号注册已被拒绝' };
        }
        if (user.status === 'banned') {
          return { code: 403, message: '账号已被封禁' };
        }

        const token = generateToken();
        await sessionsCollection.add({
          token,
          user_id: user._id,
          created_at: now,
        });

        // 更新最后登录时间
        await usersCollection.doc(user._id).update({
          last_login_at: now,
          last_login_ip: context.CLIENTIP,
        });

        return {
          code: 0,
          message: '登录成功',
          data: {
            token,
            user: { id: user._id, account: user.account, name: user.name, role: user.role, status: user.status, phone: user.phone },
          },
        };
      }

      // ── 获取当前用户 ──
      case 'me': {
        const authHeader = params.token || '';
        if (!authHeader) {
          return { code: 401, message: '未登录' };
        }

        const sessionResult = await sessionsCollection.where({ token: authHeader }).get();
        if (sessionResult.data.length === 0) {
          return { code: 401, message: '登录已过期，请重新登录' };
        }

        const session = sessionResult.data[0];
        const userResult = await usersCollection.doc(session.user_id).get();
        if (userResult.data.length === 0) {
          return { code: 401, message: '用户不存在' };
        }

        const user = userResult.data[0];
        return {
          code: 0,
          data: {
            user: { id: user._id, account: user.account, name: user.name, role: user.role, status: user.status, phone: user.phone },
          },
        };
      }

      // ── 退出登录 ──
      case 'logout': {
        const authHeader = params.token || '';
        if (authHeader) {
          await sessionsCollection.where({ token: authHeader }).remove();
        }
        return { code: 0, message: '已退出登录' };
      }

      default:
        return { code: 404, message: '未知操作: ' + action };
    }
  } catch (e) {
    if (e.code && e.message) return e;
    console.error('Auth error:', e);
    return { code: 500, message: '服务器内部错误' };
  }
};
