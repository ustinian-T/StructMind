'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const test = require('node:test');
const path = require('node:path');

const AUTH_MODULE = path.resolve(
  __dirname,
  '../uniCloud-aliyun/cloudfunctions/structmind-auth/index.js',
);

function passwordHash(password) {
  const salt = '0123456789abcdef0123456789abcdef';
  const hash = crypto.pbkdf2Sync(password, salt, 200000, 32, 'sha256').toString('hex');
  return `${salt}$${hash}`;
}

function createCloud(seed = {}) {
  const tables = {
    structmind_users: [...(seed.structmind_users || [])],
    structmind_sessions: [...(seed.structmind_sessions || [])],
  };
  let nextId = 1;

  function collection(name) {
    const rows = tables[name] || (tables[name] = []);
    return {
      where(query) {
        const matches = () => rows.filter(row =>
          Object.entries(query).every(([key, value]) => row[key] === value),
        );
        return {
          async get() { return { data: matches() }; },
          async remove() {
            const found = new Set(matches());
            tables[name] = rows.filter(row => !found.has(row));
            return { deleted: found.size };
          },
        };
      },
      doc(id) {
        return {
          async get() { return { data: rows.filter(row => row._id === id) }; },
          async update(values) {
            const row = rows.find(item => item._id === id);
            if (row) Object.assign(row, values);
            return { updated: row ? 1 : 0 };
          },
        };
      },
      async add(values) {
        const id = `${name}-${nextId++}`;
        rows.push({ _id: id, ...values });
        return { id };
      },
    };
  }

  return {
    tables,
    uniCloud: { database: () => ({ collection }) },
  };
}

function loadAuth(cloud, password = 'CloudAdmin123') {
  global.uniCloud = cloud.uniCloud;
  process.env.SM_ADMIN_ACCOUNT = 'tanshuhong';
  process.env.SM_ADMIN_PASSWORD = password;
  delete require.cache[AUTH_MODULE];
  return require(AUTH_MODULE).main;
}

test('first configured admin login bootstraps an approved administrator', async () => {
  const cloud = createCloud();
  const main = loadAuth(cloud);

  const result = await main({
    action: 'login',
    params: { account: 'tanshuhong', password: 'CloudAdmin123' },
  }, { CLIENTIP: '127.0.0.1' });

  assert.equal(result.code, 0);
  assert.equal(result.data.user.role, 'admin');
  assert.equal(result.data.user.status, 'approved');
  assert.equal(cloud.tables.structmind_users.length, 1);
});

test('public registration cannot claim the configured administrator account', async () => {
  const cloud = createCloud();
  const main = loadAuth(cloud);

  const result = await main({
    action: 'register',
    params: {
      account: 'tanshuhong', password: 'Attacker123',
      name: '攻击者', phone: '13800138000',
    },
  }, {});

  assert.equal(result.code, 403);
  assert.equal(cloud.tables.structmind_users.length, 0);
});

test('configured admin login repairs stale password role and status', async () => {
  const cloud = createCloud({
    structmind_users: [{
      _id: 'legacy-admin', account: 'tanshuhong',
      password_hash: passwordHash('OldPassword123'),
      name: '旧管理员', phone: '13800138000',
      role: 'student', status: 'rejected', created_at: 1, updated_at: 1,
    }],
    structmind_sessions: [{ _id: 'old-session', token: 'old', user_id: 'legacy-admin', created_at: 1 }],
  });
  const main = loadAuth(cloud, 'NewCloudPass456');

  const result = await main({
    action: 'login',
    params: { account: 'tanshuhong', password: 'NewCloudPass456' },
  }, { CLIENTIP: '127.0.0.1' });

  assert.equal(result.code, 0);
  assert.equal(result.data.user.role, 'admin');
  assert.equal(result.data.user.status, 'approved');
  assert.equal(cloud.tables.structmind_sessions.some(item => item.token === 'old'), false);
});

test('login creates an expiring cloud session', async () => {
  const cloud = createCloud();
  const main = loadAuth(cloud);
  await main({
    action: 'login',
    params: { account: 'tanshuhong', password: 'CloudAdmin123' },
  }, { CLIENTIP: '127.0.0.1' });

  const session = cloud.tables.structmind_sessions[0];
  assert.equal(typeof session.expires_at, 'number');
  assert.ok(session.expires_at > session.created_at);
});

test('me rejects and removes an expired cloud session', async () => {
  const cloud = createCloud({
    structmind_users: [{
      _id: 'user-1', account: 'student', password_hash: passwordHash('Student123'),
      name: '学生', phone: '13800138000', role: 'student', status: 'approved',
    }],
    structmind_sessions: [{
      _id: 'session-1', token: 'expired-token', user_id: 'user-1',
      created_at: Date.now() - 10000, expires_at: Date.now() - 1,
    }],
  });
  const main = loadAuth(cloud);

  const result = await main({ action: 'me', params: { token: 'expired-token' } }, {});

  assert.equal(result.code, 401);
  assert.equal(cloud.tables.structmind_sessions.length, 0);
});
