'use strict';

/**
 * StructMind 缓存工具模块
 *
 * 提供 TTL 内存缓存，在 uniCloud Redis 不可用时作为降级方案。
 * 同时支持尝试使用 uniCloud Redis（如果可用）。
 *
 * 使用方式：
 *   const cache = require('structmind-cache');
 *   await cache.set('key', data, 300);  // 缓存300秒
 *   const data = await cache.get('key');
 *   await cache.del('key');
 *   await cache.clear('prefix_*');
 *
 * 缓存策略：
 *   1. 优先尝试 uniCloud Redis（如果可用）
 *   2. 降级到内存缓存
 *   3. 内存缓存大小限制，LRU淘汰
 */

// ── 内存缓存实现 ──
const MAX_CACHE_SIZE = 500;           // 最大缓存条目数
const DEFAULT_TTL = 300;              // 默认过期时间 5分钟
const CLEANUP_INTERVAL = 60000;       // 清理间隔 1分钟

class MemoryCache {
  constructor() {
    this.store = new Map();
    this.accessOrder = [];            // LRU 访问顺序
  }

  /**
   * 设置缓存
   * @param {string} key
   * @param {*} value
   * @param {number} ttl - 过期时间（秒）
   */
  set(key, value, ttl = DEFAULT_TTL) {
    // LRU 淘汰
    if (this.store.size >= MAX_CACHE_SIZE && !this.store.has(key)) {
      const oldest = this.accessOrder.shift();
      if (oldest) this.store.delete(oldest);
    }

    const expiresAt = Date.now() + ttl * 1000;

    this.store.set(key, {
      value,
      expiresAt,
      ttl,
    });

    // 更新访问顺序
    this.accessOrder = this.accessOrder.filter(k => k !== key);
    this.accessOrder.push(key);
  }

  /**
   * 获取缓存
   * @param {string} key
   * @returns {*|null}
   */
  get(key) {
    const entry = this.store.get(key);
    if (!entry) return null;

    // 检查是否过期
    if (Date.now() > entry.expiresAt) {
      this.store.delete(key);
      this.accessOrder = this.accessOrder.filter(k => k !== key);
      return null;
    }

    // 更新访问顺序（LRU）
    this.accessOrder = this.accessOrder.filter(k => k !== key);
    this.accessOrder.push(key);

    return entry.value;
  }

  /**
   * 删除缓存
   * @param {string} key
   */
  del(key) {
    this.store.delete(key);
    this.accessOrder = this.accessOrder.filter(k => k !== key);
  }

  /**
   * 按前缀匹配删除
   * @param {string} pattern - 支持 'prefix_*' 格式
   */
  clearByPattern(pattern) {
    const regexStr = pattern
      .replace(/\*/g, '.*')
      .replace(/\?/g, '.');
    const regex = new RegExp(`^${regexStr}$`);

    for (const key of this.store.keys()) {
      if (regex.test(key)) {
        this.store.delete(key);
      }
    }
    this.accessOrder = this.accessOrder.filter(k => this.store.has(k));
  }

  /**
   * 清空所有缓存
   */
  clearAll() {
    this.store.clear();
    this.accessOrder = [];
  }

  /**
   * 获取或设置缓存（带工厂函数）
   * @param {string} key
   * @param {Function} factory - 如果缓存未命中，调用此函数生成值
   * @param {number} ttl
   * @returns {*}
   */
  async getOrSet(key, factory, ttl = DEFAULT_TTL) {
    const cached = this.get(key);
    if (cached !== null) return cached;

    const value = await factory();
    this.set(key, value, ttl);
    return value;
  }

  /**
   * 获取缓存统计
   */
  stats() {
    let expired = 0;
    const now = Date.now();
    for (const [, entry] of this.store) {
      if (now > entry.expiresAt) expired++;
    }
    return {
      size: this.store.size,
      maxSize: MAX_CACHE_SIZE,
      expired,
      active: this.store.size - expired,
    };
  }
}

// ── Redis 适配器（如果可用） ──
class RedisAdapter {
  constructor() {
    this.redisAvailable = false;
    this.initPromise = this.init();
  }

  async init() {
    try {
      if (typeof uniCloud !== 'undefined' && uniCloud.redis) {
        this.redis = uniCloud.redis();
        // 测试连接
        await this.redis.set('__cache_test__', '1', 1);
        await this.redis.del('__cache_test__');
        this.redisAvailable = true;
        console.log('[StructMind Cache] Redis connected');
      }
    } catch (e) {
      console.log('[StructMind Cache] Redis unavailable, using memory cache:', e.message);
      this.redisAvailable = false;
    }
  }

  async set(key, value, ttl = DEFAULT_TTL) {
    await this.initPromise;
    if (!this.redisAvailable) return false;
    try {
      const data = JSON.stringify(value);
      await this.redis.set(key, data, ttl);
      return true;
    } catch (e) {
      return false;
    }
  }

  async get(key) {
    await this.initPromise;
    if (!this.redisAvailable) return null;
    try {
      const data = await this.redis.get(key);
      return data ? JSON.parse(data) : null;
    } catch (e) {
      return null;
    }
  }

  async del(key) {
    await this.initPromise;
    if (!this.redisAvailable) return false;
    try {
      await this.redis.del(key);
      return true;
    } catch (e) {
      return false;
    }
  }

  async clearByPattern(pattern) {
    await this.initPromise;
    if (!this.redisAvailable) return false;
    try {
      const keys = await this.redis.keys(pattern);
      if (keys && keys.length > 0) {
        await this.redis.del(...keys);
      }
      return true;
    } catch (e) {
      return false;
    }
  }

  isAvailable() {
    return this.redisAvailable;
  }
}

// ── 统一缓存接口 ──
const memoryCache = new MemoryCache();
const redisAdapter = new RedisAdapter();

// 定时清理过期内存缓存
setInterval(() => {
  // 遍历清理过期条目
  const now = Date.now();
  for (const [key, entry] of memoryCache.store) {
    if (now > entry.expiresAt) {
      memoryCache.del(key);
    }
  }
}, CLEANUP_INTERVAL);

/**
 * 设置缓存（优先 Redis，降级到内存）
 */
async function set(key, value, ttl = DEFAULT_TTL) {
  // 尝试 Redis
  const redisOk = await redisAdapter.set(key, value, ttl);
  if (!redisOk) {
    // 降级到内存
    memoryCache.set(key, value, ttl);
  }
  // 双写：Redis成功时也写内存（加速本地读取）
  if (redisOk) {
    memoryCache.set(key, value, ttl);
  }
}

/**
 * 获取缓存（优先内存，回退到 Redis）
 */
async function get(key) {
  // 先查内存
  const memResult = memoryCache.get(key);
  if (memResult !== null) return memResult;

  // 再查 Redis
  const redisResult = await redisAdapter.get(key);
  if (redisResult !== null) {
    // 回填内存
    memoryCache.set(key, redisResult, DEFAULT_TTL);
    return redisResult;
  }

  return null;
}

/**
 * 删除缓存
 */
async function del(key) {
  memoryCache.del(key);
  await redisAdapter.del(key);
}

/**
 * 按模式清理缓存
 * @param {string} pattern - 如 'question_*', 'leaderboard_*'
 */
async function clear(pattern) {
  memoryCache.clearByPattern(pattern);
  await redisAdapter.clearByPattern(pattern);
}

/**
 * 获取或设置缓存
 * @param {string} key
 * @param {Function} factory
 * @param {number} ttl
 */
async function getOrSet(key, factory, ttl = DEFAULT_TTL) {
  const cached = await get(key);
  if (cached !== null) return cached;

  const value = await factory();
  await set(key, value, ttl);
  return value;
}

/**
 * 获取缓存统计
 */
function stats() {
  return {
    memory: memoryCache.stats(),
    redis_available: redisAdapter.isAvailable(),
  };
}

/**
 * 预热缓存 - 用于常用数据
 * @param {Object} warmupData - { key: factoryFunction, ... }
 */
async function warmup(warmupData) {
  const results = {};
  for (const [key, factory] of Object.entries(warmupData)) {
    try {
      results[key] = await getOrSet(key, factory);
    } catch (e) {
      console.error(`[Cache warmup] Failed for ${key}:`, e.message);
      results[key] = null;
    }
  }
  return results;
}

// ── 预定义的缓存键前缀 ──
const CACHE_KEYS = {
  QUESTION_LIST: 'questions_',        // 题目列表: questions_{hash}
  LEADERBOARD: 'leaderboard_',        // 排行榜: leaderboard_{type}
  USER_PROFILE: 'user_profile_',      // 用户画像: user_profile_{userId}
  DASHBOARD: 'dashboard_',            // 仪表盘: dashboard_{range}
  AI_CONVERSATION: 'ai_conv_',        // AI对话: ai_conv_{convId}
  CHAPTER_STATS: 'chapter_stats_',    // 章节统计
};

module.exports = {
  set,
  get,
  del,
  clear,
  getOrSet,
  stats,
  warmup,
  CACHE_KEYS,
  DEFAULT_TTL,
};
