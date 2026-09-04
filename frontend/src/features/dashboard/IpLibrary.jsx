/* ============================================================
 * SKU Hunters · IpLibrary（IP 资源库 · 扩充）
 *
 * 与「名创内部 · IP 资源库」（InsightBase）并列的独立页面：
 * 承载飞书 base_ip_partnerships 的 33 条名创 IP 合作情报。
 * 三级结构：分类 Tab → IP 卡片（状态筛选 + 搜索）→ 详情抽屉（图轮播 + 产品信息）。
 * 图片：飞书附件经后端 /ip-library/image 代理；seed 档无图自动降级色块；
 * 支持 public/assets/ip-library/{slug}/ 本地图后补生效。
 * ============================================================ */

import { useEffect, useMemo, useState } from 'react';
import { Badge, Card, Col, Descriptions, Empty, Input, Modal, Rate, Row, Segmented, Tag } from 'antd';
import { getIpLibrary } from '../../api/dashboard';
import StateCard from '../../shared/components/StateCard';
import PageHeader from '../plans/components/PageHeader';

/** IP 图片三级降级：本地资产 → 飞书附件代理 → 色块占位 */
function IpLibImage({ ip, fileToken, className, fallback }) {
  const [stage, setStage] = useState(0); // 0=本地图 1=飞书代理 2=降级色块
  if (!fileToken || stage >= 2) return fallback;
  const src =
    stage === 0
      ? `/assets/ip-library/${ip.slug}/${fileToken}.jpg`
      : `/api/v1/ip-library/image?file_token=${encodeURIComponent(fileToken)}`;
  return <img src={src} alt={ip.name} className={className} onError={() => setStage((s) => s + 1)} />;
}

/** 详情抽屉左侧：产品图轮播（飞书档 ≥4 张；无图降级色块） */
function ImageCarousel({ ip }) {
  const tokens = ip.ipImage || [];
  const [idx, setIdx] = useState(0);
  if (!tokens.length) {
    return <div className="ip-carousel ip-carousel-fallback">{ip.name}</div>;
  }
  const current = tokens[Math.min(idx, tokens.length - 1)];
  return (
    <div className="ip-carousel" role="group" aria-label={`${ip.name} 产品图`}>
      <IpLibImage
        ip={ip}
        fileToken={current}
        className="ip-carousel-img"
        fallback={<div className="ip-carousel ip-carousel-fallback">{ip.name}</div>}
      />
      {tokens.length > 1 && (
        <div className="ip-carousel-dots" role="tablist" aria-label="产品图切换">
          {tokens.map((t, i) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={i === idx}
              aria-label={`第 ${i + 1} 张`}
              className={`ip-carousel-dot ${i === idx ? 'active' : ''}`}
              onClick={() => setIdx(i)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function IpLibCard({ ip, onOpen }) {
  const statusColor = { 持续合作: 'green', 战略共创: 'geekblue', 一次性联名: 'orange', 快闪限定: 'purple' }[ip.cooperationStatus] || 'default';
  return (
    <Card
      className="ip-card"
      size="small"
      hoverable
      onClick={() => onOpen(ip)}
      role="button"
      aria-label={`查看 ${ip.name} 详情`}
    >
      <IpLibImage ip={ip} fileToken={(ip.ipImage || [])[0]} className="ip-card-cover" fallback={<div className="ip-card-cover ip-card-cover-fallback">{ip.name}</div>} />
      <div className="ip-card-body">
        <div className="ip-card-heading">
          <div className="ip-card-name">
            <strong style={{ fontSize: 14 }}>{ip.name}</strong>
          </div>
          <span className="ip-potential">热度 {ip.ipHeat}</span>
        </div>
        <div className="ip-tags">
          <Tag color={statusColor}>{ip.cooperationStatus}</Tag>
          <Tag>{ip.ipType}</Tag>
        </div>
        <div className="ip-field"><span>授权方</span>{ip.licensor || '—'}</div>
        <div className="ip-field"><span>价格带</span>¥{ip.priceMin ?? '?'} – ¥{ip.priceMax ?? '?'}</div>
        <div className="ip-field"><span>风格</span>{ip.styleGroup} · {ip.audienceGroup}</div>
        <Rate disabled value={ip.potential} style={{ fontSize: 12, marginTop: 6 }} aria-label={`潜力 ${ip.potential} 星`} />
      </div>
    </Card>
  );
}

export default function IpLibrary() {
  const [status, setStatus] = useState('loading');
  const [ips, setIps] = useState([]);
  const [typeFilters, setTypeFilters] = useState([]);
  const [activeType, setActiveType] = useState('全部');
  const [activeStatus, setActiveStatus] = useState('全部');
  const [keyword, setKeyword] = useState('');
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    let alive = true;
    getIpLibrary()
      .then((data) => {
        if (!alive) return;
        setIps(data.ips || []);
        setTypeFilters(data.typeFilters || []);
        setStatus('success');
      })
      .catch(() => alive && setStatus('error'));
    return () => { alive = false; };
  }, []);

  const typeCounts = useMemo(() => {
    const m = new Map();
    ips.forEach((ip) => m.set(ip.ipType, (m.get(ip.ipType) || 0) + 1));
    return m;
  }, [ips]);

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return ips.filter((ip) => {
      if (activeType !== '全部' && ip.ipType !== activeType) return false;
      if (activeStatus !== '全部' && ip.cooperationStatus !== activeStatus) return false;
      if (kw && !`${ip.name} ${ip.licensor} ${ip.productLines} ${ip.starProducts}`.toLowerCase().includes(kw)) return false;
      return true;
    });
  }, [ips, activeType, activeStatus, keyword]);

  const grouped = useMemo(() => {
    if (activeType !== '全部') return [[activeType, filtered]];
    return typeFilters.map((t) => [t, filtered.filter((ip) => ip.ipType === t)]).filter(([, list]) => list.length);
  }, [filtered, activeType, typeFilters]);

  if (status === 'loading') return <><PageHeader title="IP 资源库（扩充）" /><StateCard status="loading" /></>;
  if (status === 'error') {
    return (
      <>
        <PageHeader title="IP 资源库（扩充）" />
        <StateCard status="error" onRetry={() => { setStatus('loading'); window.location.reload(); }} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="IP 资源库（扩充）"
        subtitle={`${ips.length} 条名创 IP 合作情报 · 授权方 / 合作状态 / 价格带 / 渠道策略（飞书 Base base_ip_partnerships）`}
      />
      <div className="ip-filters" role="search" aria-label="IP 筛选">
        <Segmented
          value={activeType}
          onChange={setActiveType}
          options={['全部', ...typeFilters].map((t) => ({
            value: t,
            label: t === '全部' ? `全部 (${ips.length})` : `${t} (${typeCounts.get(t) || 0})`,
          }))}
          aria-label="IP 分类"
        />
        <Segmented
          value={activeStatus}
          onChange={setActiveStatus}
          options={['全部', '持续合作', '战略共创', '一次性联名', '快闪限定']}
          aria-label="合作状态筛选"
        />
        <Input.Search
          placeholder="搜索 IP / 授权方 / 产品线 / 明星产品"
          allowClear
          onChange={(e) => setKeyword(e.target.value)}
          style={{ maxWidth: 280 }}
          aria-label="关键字搜索"
        />
      </div>

      {filtered.length === 0 ? (
        <StateCard status="empty" emptyText="没有匹配的 IP，换个筛选条件试试" />
      ) : (
        grouped.map(([type, list]) => (
          <section key={type} aria-label={`${type} 分类`} style={{ marginBottom: 20 }}>
            {activeType === '全部' && (
              <h3 style={{ fontSize: 14, margin: '0 0 10px', color: 'var(--color-text-secondary)' }}>
                {type} <Badge count={list.length} style={{ backgroundColor: 'var(--color-action-primary)' }} />
              </h3>
            )}
            <Row gutter={[12, 12]}>
              {list.map((ip) => (
                <Col key={ip.ipId} xs={24} sm={12} md={8} lg={6}>
                  <IpLibCard ip={ip} onOpen={setDetail} />
                </Col>
              ))}
            </Row>
          </section>
        ))
      )}

      <Modal
        open={!!detail}
        onCancel={() => setDetail(null)}
        width={1100}
        centered
        footer={null}
        title={detail ? `${detail.name} · IP 详情` : ''}
        destroyOnClose
      >
        {detail && (
          <Row gutter={[20, 16]}>
            <Col xs={24} md={9}>
              <ImageCarousel ip={detail} />
              {detail.sourceUrl && (
                <a href={detail.sourceUrl} target="_blank" rel="noreferrer" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
                  情报来源 ↗
                </a>
              )}
            </Col>
            <Col xs={24} md={15}>
              <Descriptions column={1} size="small" bordered labelStyle={{ width: 90, whiteSpace: 'nowrap' }} contentStyle={{ whiteSpace: 'normal' }} style={{ wordBreak: 'break-all' }}>
                <Descriptions.Item label="授权方">{detail.licensor}</Descriptions.Item>
                <Descriptions.Item label="合作状态">
                  <Tag>{detail.cooperationStatus}</Tag> 自 {detail.cooperationSince}
                </Descriptions.Item>
                <Descriptions.Item label="IP 类型">{detail.ipType} · {detail.styleGroup}</Descriptions.Item>
                <Descriptions.Item label="价格带">¥{detail.priceMin} – ¥{detail.priceMax}</Descriptions.Item>
                <Descriptions.Item label="渠道策略">{(detail.channelStrategy || []).join('、') || '—'}</Descriptions.Item>
                <Descriptions.Item label="最新系列">{detail.latestSeries}</Descriptions.Item>
                <Descriptions.Item label="产品线">{detail.productLines}</Descriptions.Item>
                <Descriptions.Item label="明星产品">{detail.starProducts}</Descriptions.Item>
                <Descriptions.Item label="备注">{detail.notes}</Descriptions.Item>
              </Descriptions>
            </Col>
          </Row>
        )}
      </Modal>
    </>
  );
}
