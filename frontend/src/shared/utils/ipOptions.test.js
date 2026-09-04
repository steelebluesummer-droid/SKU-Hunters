/* ============================================================
 * IP 选项合并工具测试（NewPlan 页选项合并与降级逻辑）
 * ============================================================ */

import { describe, expect, it } from 'vitest';
import { IP_OPTIONS_FALLBACK, NO_IP_OPTION, ipKey, mergeIpOptions } from './ipOptions';

describe('ipKey 别名归一', () => {
  it('括号后缀剥离：三丽鸥（Sanrio）= 三丽鸥', () => {
    expect(ipKey('三丽鸥（Sanrio）')).toBe('三丽鸥');
    expect(ipKey('小黄人（神偷奶爸）')).toBe('小黄人');
    expect(ipKey('Chiikawa（吉伊卡哇）')).toBe('Chiikawa');
  });

  it('跨语言别名：航海王 = 海贼王、Pokémon = 宝可梦', () => {
    expect(ipKey('航海王')).toBe('海贼王');
    expect(ipKey('Pokémon')).toBe('宝可梦');
    expect(ipKey('Sanrio')).toBe('三丽鸥');
  });

  it('空值安全', () => {
    expect(ipKey('')).toBe('');
    expect(ipKey(null)).toBe('');
  });
});

describe('mergeIpOptions 三源合并', () => {
  const curated = ['三丽鸥', '迪士尼', '宝可梦', '航海王', '咱们裸熊'];
  const library = ['三丽鸥（Sanrio）', '宝可梦', '海贼王（ONE PIECE）', 'LABUBU × Hello Kitty', 'YOYO'];

  it('同名/别名去重，保留先到主名', () => {
    const merged = mergeIpOptions(IP_OPTIONS_FALLBACK, curated, library);
    const keys = merged.map(ipKey);
    expect(new Set(keys).size).toBe(keys.length); // 无重复
    expect(merged).toContain('三丽鸥');
    expect(merged).not.toContain('三丽鸥（Sanrio）'); // 别名不重复出现
  });

  it('含 40+ 选项（fallback ∪ 策展 ∪ 扩充）', () => {
    const bigLibrary = Array.from({ length: 33 }, (_, i) => `扩充IP${i + 1}`);
    const merged = mergeIpOptions(IP_OPTIONS_FALLBACK, curated, bigLibrary);
    expect(merged.length).toBeGreaterThanOrEqual(38);
  });

  it('「不带 IP」不进入合并结果（由渲染层单独追加）', () => {
    const merged = mergeIpOptions(IP_OPTIONS_FALLBACK, curated, library);
    expect(merged).not.toContain(NO_IP_OPTION);
  });

  it('两档全失败时降级：空输入返回空数组，NewPlan 保持 fallback', () => {
    expect(mergeIpOptions([], [], [])).toEqual([]);
    expect(mergeIpOptions(IP_OPTIONS_FALLBACK, [], [])).toEqual(
      IP_OPTIONS_FALLBACK.filter((n) => n !== NO_IP_OPTION),
    );
  });
});
