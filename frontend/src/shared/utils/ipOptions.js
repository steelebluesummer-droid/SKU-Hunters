/* ============================================================
 * SKU Hunters · IP 选项合并与三档分组工具（NewPlan 页）
 *
 * 三档 IP 策略（与后端 feishu/nl_brief.py 同口径）：
 *   1) 无外部联名：本企划不使用任何 IP（走名创自有品牌原创线），提交时归一为空 ip_strategy；
 *   2) 自有 IP：名创自研 / 自有艺术家 IP（YOYO、Nommi 糯米儿等），展示加「（自有IP）」；
 *   3) 外部联名 IP：外部授权 IP（三丽鸥、迪士尼等），仅限资源库内。
 *
 * 兼容：保留 IP_OPTIONS_FALLBACK / NO_IP_OPTION / ipKey / mergeIpOptions 旧导出与测试行为。
 * ============================================================ */

// 两档资源请求都失败时的基础外部 IP（仅兜底；'不带 IP' 为旧哨兵，会被 merge 过滤、由渲染层单独处理）
export const IP_OPTIONS_FALLBACK = [
  '三丽鸥',
  '迪士尼',
  'Chiikawa',
  '线条小狗',
  '不带 IP',
];

// 旧“不带 IP”哨兵（保留兼容，已被 NO_EXTERNAL_IP 取代）
export const NO_IP_OPTION = '不带 IP';

// 新三档之一：无外部联名（规范值 + 展示文案）
export const NO_EXTERNAL_IP = '无外部联名';
export const NO_EXTERNAL_LABEL = '无外部联名（原创设计 · 不走 IP 联名）';

// 名创自有 IP 规范名（与后端 ip_library.IP_LIBRARY_SEED 中 ipType=自有IP 对齐）
export const OWN_IP_NAMES = [
  'YOYO',
  'CHOUCHOU',
  'DUNDUN鸡',
  '蛋仔派对×YOYO',
  'Nommi 糯米儿',
  'PENPEN 企鹅',
  '中国熊猫',
  '萝卜街',
  'Kumaru',
  '气宝 Angry Aimee',
];

// 跨语言 / 角色 → 规范展示名（合并去重时把别名并到主名）
const IP_ALIAS = {
  sanrio: '三丽鸥',
  玉桂狗: '大耳狗（Cinnamoroll）',
  cinnamoroll: '大耳狗（Cinnamoroll）',
  库洛米: '三丽鸥',
  kuromi: '三丽鸥',
  美乐蒂: '三丽鸥',
  melody: '三丽鸥',
  hello_kitty: '三丽鸥',
  hellokitty: '三丽鸥',
  disney: '迪士尼',
  米奇: '迪士尼',
  米妮: '迪士尼',
  草莓熊: '迪士尼',
  史迪奇: '迪士尼',
  pokemon: '宝可梦',
  pokémon: '宝可梦',
  皮卡丘: '宝可梦',
  航海王: '海贼王',
  one_piece: '海贼王',
  onepiece: '海贼王',
  路飞: '海贼王',
  loopy: 'Loopy',
  露比: 'Loopy',
  chiikawa: 'Chiikawa',
  吉伊: 'Chiikawa',
  吉伊卡哇: 'Chiikawa',
  小八: 'Chiikawa',
  乌萨奇: 'Chiikawa',
  线条小狗: '线条小狗',
  maltese: '线条小狗',
};

/** 归一为去重/别名 key：小写去间隔符 → 剥括号补充 → 查别名表返回规范名（保留规范大小写，如 Chiikawa） */
export function ipKey(name) {
  if (!name) return '';
  const k = String(name).trim().toLowerCase().replace(/[\s·・._-]/g, '');
  const stripped = k.split(/[(（]/)[0].trim(); // 去括号补充：三丽鸥（Sanrio）→ 三丽鸥
  return IP_ALIAS[k] || IP_ALIAS[stripped] || stripped || k;
}

const OWN_KEYS = new Set(OWN_IP_NAMES.map(ipKey));
const OWN_ORDER = new Map(OWN_IP_NAMES.map((n, i) => [ipKey(n), i]));

/** 判断是否名创自有 IP：优先看资源库 ipType 标记，其次按规范名兜底 */
export function isOwnIp(name, ipType) {
  if (ipType === '自有IP') return true;
  return OWN_KEYS.has(ipKey(name));
}

function _asNameType(item) {
  if (item && typeof item === 'object') {
    return { name: String(item.name || item.nameCn || '').trim(), ipType: item.ipType || '' };
  }
  return { name: String(item || '').trim(), ipType: '' };
}

/**
 * 三源合并为纯名字列表（旧逻辑，保留给测试/平铺场景）：
 * fallback（基础兜底）→ curated（名创内部策展）→ library（扩充库），同名/别名只保留先到的主名。
 * 「不带 IP」「无外部联名」这类哨兵不进入合并结果（由渲染层单独追加）。
 */
export function mergeIpOptions(fallback = [], curated = [], library = []) {
  const seen = new Set();
  const merged = [];
  const all = [...fallback, ...curated, ...library];
  for (const raw of all) {
    const name = typeof raw === 'object'
      ? String(raw?.name || raw?.nameCn || '').trim()
      : String(raw || '').trim();
    if (!name || name === NO_IP_OPTION || name === NO_EXTERNAL_IP) continue;
    const key = ipKey(name); // 去重/别名归一走 ipKey；展示保留原始 name（大小写/写法）
    if (!key || seen.has(key)) continue;
    seen.add(key);
    merged.push(name);
  }
  return merged;
}

/**
 * 三档分组下拉（AntD Select options，支持 OptGroup 嵌套 {label, options}）。
 * 入参元素可为字符串或 {name, nameCn, ipType} 对象；输出顺序：
 *   不使用 IP（无外部联名）→ 自有 IP（按 OWN_IP_NAMES 顺序，标注「（自有IP）」）→ 外部联名 IP。
 */
export function buildIpSelectGroups(fallback = [], curated = [], library = []) {
  const seen = new Set();
  const own = [];
  const ext = [];
  const push = (item) => {
    const { name, ipType } = _asNameType(item);
    if (!name || name === NO_IP_OPTION || name === NO_EXTERNAL_IP) return;
    const key = ipKey(name); // 去重/别名归一走 ipKey；展示保留原始 name（大小写/写法）
    if (!key || seen.has(key)) return;
    seen.add(key);
    if (isOwnIp(name, ipType)) own.push(name);
    else ext.push(name);
  };
  [...fallback, ...curated, ...library].forEach(push);

  own.sort((a, b) => {
    const oa = OWN_ORDER.has(ipKey(a)) ? OWN_ORDER.get(ipKey(a)) : 999;
    const ob = OWN_ORDER.has(ipKey(b)) ? OWN_ORDER.get(ipKey(b)) : 999;
    return oa - ob || a.localeCompare(b, 'zh-Hans-CN');
  });

  return [
    {
      label: '不使用 IP',
      options: [{ value: NO_EXTERNAL_IP, label: NO_EXTERNAL_LABEL }],
    },
    {
      label: '自有 IP（名创自研）',
      options: own.map((n) => ({ value: n, label: `${n}（自有IP）` })),
    },
    {
      label: '外部联名 IP',
      options: ext.map((n) => ({ value: n, label: n })),
    },
  ];
}
