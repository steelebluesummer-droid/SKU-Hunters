/* ============================================================
 * SKU Hunters · API 请求封装（client）
 * 纯 fetch：BASE、request、结构化错误归一化。
 * 只做纯请求，不改写任何 mock 常量；非 2xx 抛结构化错误（{status, code, message}）。
 * ============================================================ */

const BASE = '/api/v1';

// ── GET 短缓存：看板类数据 30 秒内二次请求直接复用，切页免重复转圈 ──
// 仅缓存无参数 GET；带参数 url（含 ?）不缓存；非 GET 不缓存。
const GET_CACHE_TTL = 30 * 1000;
const _getCache = new Map(); // url → { at, promise }

async function requestWithGetCache(url, opts) {
  const cacheable = !opts.method || opts.method === 'GET';
  if (!cacheable || url.includes('?')) return rawRequest(url, opts);
  const hit = _getCache.get(url);
  if (hit && Date.now() - hit.at < GET_CACHE_TTL) return hit.promise;
  const promise = rawRequest(url, opts).catch((e) => {
    _getCache.delete(url); // 失败不缓存
    throw e;
  });
  _getCache.set(url, { at: Date.now(), promise });
  return promise;
}

/**
 * 统一请求封装：返回解析后的 JSON；非 2xx 抛出结构化错误。
 * 数据契约统一为 camelCase（与后端 loader / fixtures 对齐）。
 */
async function rawRequest(url, opts = {}) {
  let res;
  try {
    res = await fetch(BASE + url, {
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      ...opts,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch (e) {
    // 网络层失败（后端不在线 / 断网）：抛出统一错误，由调用方决定是否走演示数据
    const err = new Error('网络请求失败');
    err.code = 'NETWORK_ERROR';
    err.cause = e;
    throw err;
  }

  let data;
  try {
    data = await res.json();
  } catch {
    data = {};
  }

  if (!res.ok) {
    const err = new Error(data?.detail?.error?.message || `请求失败（${res.status}）`);
    err.status = res.status;
    err.code = data?.detail?.error?.code || 'HTTP_ERROR';
    err.request_id = data?.detail?.error?.request_id;
    err.detail = data?.detail;
    throw err;
  }
  return data;
}

export { BASE };


/** 对外请求入口：GET 走 30s 短缓存，其余直接请求 */
export function request(url, opts = {}) {
  return requestWithGetCache(url, opts);
}

/** 使指定 url 的 GET 缓存失效（增删改后调用，保证下次拉到最新数据） */
export function invalidateGetCache(urlPrefix) {
  for (const key of [..._getCache.keys()]) {
    if (!urlPrefix || key.startsWith(urlPrefix)) _getCache.delete(key);
  }
}
