/* ============================================================
 * IP 选项合并工具（NewPlan 页使用）
 * 三源合并：fallback 5 项 ∪ 策展 12 IP ∪ 扩充库 33 IP，按别名归一去重。
 * 与后端 ip_library.ALIAS_NORMALIZE 同口径。
 * ============================================================ */

export const IP_OPTIONS_FALLBACK = ['三丽鸥', '迪士尼', 'Chiikawa', '线条小狗', '不带 IP'];
export const NO_IP_OPTION = '不带 IP';

const IP_ALIAS = {
  sanrio: '三丽鸥', disney: '迪士尼', 'harry potter': '哈利·波特', barbie: '芭比',
  'one piece': '海贼王', 航海王: '海贼王', marvel: '漫威', 'pokémon': '宝可梦', pokemon: '宝可梦',
  minions: '小黄人', 神偷奶爸: '小黄人', 'snoopy / peanuts': '史努比', 吉伊卡哇: 'Chiikawa', chiikawa: 'Chiikawa',
};

export function ipKey(name) {
  const k = (name || '').trim().toLowerCase();
  const stripped = k.split(/[(（]/)[0].trim();
  return IP_ALIAS[k] || IP_ALIAS[stripped] || stripped || k;
}

export function mergeIpOptions(fallback, curated, library) {
  const out = [];
  const seen = new Set();
  for (const name of [...(fallback || []), ...(curated || []), ...(library || [])]) {
    if (!name || name === NO_IP_OPTION) continue;
    const k = ipKey(name);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(name);
  }
  return out;
}
