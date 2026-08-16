/* ============================================================
 * SKU Hunters · TrendGallery（流行元素板 · Moodboard）
 * 使用 api/dashboard.js 的 getTrendGallery，接口失败不回退 fixture。
 * 情绪板版式：Hero 渐变标题 + 全出血色卡墙（点击复制）+ 花纹/形态/表情配图卡。
 * 色块 hex 非法时安全占位；色块同时显示色名、色值、来源（不依赖颜色）。
 * 动效：hover 微浮起 + 滚动进入淡入上移（IntersectionObserver，不引第三方库）。
 * ============================================================ */

import { useEffect, useRef, useState } from 'react';
import { Empty, message } from 'antd';
import { getTrendGallery } from '../../api/dashboard';
import StateCard from '../../shared/components/StateCard';
import PageHeader from '../plans/components/PageHeader';

// hex 校验：合法 #RGB / #RRGGBB 才使用，否则安全占位
function safeHex(hex) {
  return /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(hex || '') ? hex : '#d9d9d9';
}

// 根据色块亮度决定文字用深色还是浅色（浅底色 → 深字，深底色 → 浅字）
function textColorOn(hex) {
  const h = (hex || '').replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const r = parseInt(full.slice(0, 2), 16) || 0;
  const g = parseInt(full.slice(2, 4), 16) || 0;
  const b = parseInt(full.slice(4, 6), 16) || 0;
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.62 ? 'rgba(0,0,0,0.72)' : 'rgba(255,255,255,0.95)';
}

// 滚动进入淡入上移（IntersectionObserver，一次性触发）
function Reveal({ children, delay = 0 }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (typeof IntersectionObserver === 'undefined') return undefined;
    const ob = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            el.style.opacity = '1';
            el.style.transform = 'translateY(0)';
            ob.unobserve(el);
          }
        });
      },
      { threshold: 0.08 }
    );
    ob.observe(el);
    return () => ob.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      style={{
        opacity: 0,
        transform: 'translateY(14px)',
        transition: `opacity .5s ease ${delay}ms, transform .5s ease ${delay}ms`,
      }}
    >
      {children}
    </div>
  );
}

// 区块标题（情绪板口径：大号英文副标 + 中文主标）
function SectionTitle({ en, zh }) {
  return (
    <div style={{ margin: '28px 0 14px' }}>
      <div style={{ fontSize: 11, letterSpacing: 2, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>{en}</div>
      <h2 style={{ margin: '2px 0 0', fontSize: 20, fontWeight: 700 }}>{zh}</h2>
    </div>
  );
}

export default function TrendGallery() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getTrendGallery();
      setData(d || {});
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return (
      <div>
        <PageHeader title="流行元素板 · Trend Gallery" />
        <StateCard status="loading" />
      </div>
    );
  }
  if (error) {
    return (
      <div>
        <PageHeader title="流行元素板 · Trend Gallery" />
        <StateCard status="error" onRetry={load} emptyText="Trend Gallery 加载失败" />
      </div>
    );
  }

  const colors = data.colors || [];
  const patterns = data.patterns || [];
  const shapes = data.shapes || [];
  const expressions = data.expressions || [];

  const copyHex = (c) => {
    try {
      navigator.clipboard?.writeText(c.hex);
      message.success(`已复制 ${c.name} ${c.hex}`);
    } catch {
      message.info(c.hex);
    }
  };

  // Hero 渐变标题：取前 6 个趋势色做文字渐变（无数据则用安全色）
  const heroColors = colors.map((c) => safeHex(c.hex));
  const heroGradient =
    heroColors.length >= 2
      ? `linear-gradient(90deg, ${heroColors.slice(0, 6).join(', ')})`
      : 'var(--color-text)';

  return (
    <div>
      {/* Hero：大号渐变标题 + 副标 */}
      <Reveal>
        <div style={{ padding: '32px 0 8px', textAlign: 'center' }}>
          <div style={{ fontSize: 12, letterSpacing: 4, color: 'var(--color-text-muted)' }}>TREND GALLERY · MOODBOARD</div>
          <h1
            style={{
              margin: '8px 0 6px',
              fontSize: 52,
              fontWeight: 800,
              lineHeight: 1.1,
              background: heroGradient,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            流行元素板
          </h1>
          <p style={{ margin: 0, fontSize: 14, color: 'var(--color-text-secondary)' }}>
            小风扇 2026 春夏情绪板 · 跨品类采集（服装 / 食品 / 美妆 / 潮玩），企划生成时由创意设计模块调用融合
          </p>
        </div>
      </Reveal>

      {/* ① 配色趋势 → 全出血色卡墙 */}
      <Reveal delay={60}>
        <SectionTitle en="Color Palette" zh="配色趋势" />
        {colors.length === 0 ? (
          <Empty description="暂无配色数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
              gap: 12,
            }}
          >
            {colors.map((c) => (
              <div
                key={c.name}
                onClick={() => copyHex(c)}
                title="点击复制色值"
                style={{
                  position: 'relative',
                  background: safeHex(c.hex),
                  borderRadius: 10,
                  height: c.year ? 190 : 150,
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'flex-end',
                  padding: 12,
                  overflow: 'hidden',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
                  transition: 'transform .2s ease, box-shadow .2s ease',
                }}
                className="trend-swatch"
              >
                {c.year ? (
                  <span
                    style={{
                      position: 'absolute',
                      top: 10,
                      right: 10,
                      fontSize: 11,
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: 999,
                      background: 'rgba(255,255,255,0.85)',
                      color: '#333',
                    }}
                  >
                    {c.year}
                  </span>
                ) : null}
                <div style={{ color: textColorOn(c.hex), lineHeight: 1.5 }}>
                  <div style={{ fontWeight: 700, fontSize: 14, wordBreak: 'break-word' }}>{c.name}</div>
                  <div style={{ fontSize: 12, opacity: 0.9, fontFamily: 'ui-monospace, monospace' }}>{c.hex}</div>
                  <div style={{ fontSize: 11, opacity: 0.75, wordBreak: 'break-word' }}>{c.source}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Reveal>

      {/* ②③ 花纹 / 形态 → 上图下文缩略图卡 */}
      <Reveal delay={80}>
        <SectionTitle en="Patterns & Shapes" zh="花纹图案 · 形态结构" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16 }}>
          {[...patterns, ...shapes].map((p) => (
            <div
              key={p.name}
              style={{
                borderRadius: 12,
                overflow: 'hidden',
                background: 'var(--color-surface)',
                boxShadow: '0 1px 6px rgba(0,0,0,0.06)',
                transition: 'transform .2s ease, box-shadow .2s ease',
              }}
              className="trend-card"
            >
              {p.image ? (
                <img src={p.image} alt={p.name} style={{ width: '100%', height: 160, objectFit: 'cover', display: 'block' }} />
              ) : (
                <div style={{ width: '100%', height: 160, background: 'var(--color-surface-alt)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-muted)', fontSize: 12 }}>
                  无配图
                </div>
              )}
              <div style={{ padding: '12px 14px 14px' }}>
                <div style={{ fontWeight: 700, fontSize: 14, wordBreak: 'break-word' }}>{p.name}</div>
                {p.note ? <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4, wordBreak: 'break-word' }}>{p.note}</div> : null}
                {p.source ? <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 6 }}>{p.source}</div> : null}
              </div>
            </div>
          ))}
        </div>
      </Reveal>

      {/* ④ 表情化趋势 → 大图卡（IP 情绪语言） */}
      <Reveal delay={80}>
        <SectionTitle en="IP Emotion Language" zh="表情化趋势" />
        {expressions.length === 0 ? (
          <Empty description="暂无表情化数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
            {expressions.map((e) => (
              <div
                key={e.name}
                style={{
                  position: 'relative',
                  borderRadius: 14,
                  overflow: 'hidden',
                  height: 240,
                  boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                  transition: 'transform .2s ease, box-shadow .2s ease',
                }}
                className="trend-card"
              >
                {e.image ? (
                  <img src={e.image} alt={e.name} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                ) : (
                  <div style={{ width: '100%', height: '100%', background: 'var(--color-surface-alt)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 48 }}>
                    {e.emoji || '✨'}
                  </div>
                )}
                <div
                  style={{
                    position: 'absolute',
                    left: 0,
                    right: 0,
                    bottom: 0,
                    padding: '28px 14px 12px',
                    background: 'linear-gradient(transparent, rgba(0,0,0,0.72))',
                    color: '#fff',
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: 15 }}>{e.emoji ? `${e.emoji} ` : ''}{e.name}</div>
                  {e.note ? <div style={{ fontSize: 12, opacity: 0.92, marginTop: 2 }}>{e.note}</div> : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </Reveal>

      <p style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 28, textAlign: 'center' }}>
        数据来源：跨品类社媒采集样本 · 配图为公开网络搜索占位，商用前需替换为自有版权图
      </p>
    </div>
  );
}
