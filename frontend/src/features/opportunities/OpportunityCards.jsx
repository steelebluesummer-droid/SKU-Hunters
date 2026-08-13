import { useState } from 'react';
import { Card, Row, Col, Tag, Popover, Button } from 'antd';
import ProcessLog from '../../shared/components/ProcessLog';

// 机会生成：3 张方向卡，每张挂依据链（可回溯洞察），人选定 1 张进入企划生成
// props 驱动：数据由 TaskFlow 拉取后传入，不再 import 全局 mock
export default function OpportunityCards({ opportunities = [], selected, onSelect, processLog = [] }) {
  const [logDone, setLogDone] = useState(false);
  return (
    <div>
      {processLog.length > 0 && (
        <Card size="small" title="机会生成 · 思考过程" style={{ marginBottom: 16, background: 'var(--color-surface-alt)', border: '1px solid var(--color-border-strong)' }}>
          <ProcessLog lines={processLog} onDone={() => setLogDone(true)} />
        </Card>
      )}
      <div style={{ opacity: processLog.length === 0 || logDone ? 1 : 0, transition: 'opacity 0.5s', pointerEvents: processLog.length === 0 || logDone ? 'auto' : 'none' }}>
        <Card size="small" style={{ marginBottom: 16, background: 'var(--color-surface-alt)', border: '1px solid var(--color-border-strong)' }}>
          <b style={{ color: 'var(--color-action-primary)' }}>机会生成：</b>
          综合趋势信号、用户痛点、竞品空白、名创资产与流行元素，收敛出方向——每个方向的依据可点击回溯。
        </Card>
        <Row gutter={16}>
          {opportunities.map(o => (
            <Col xs={24} sm={24} md={8} key={o.id}>
              <Card
                className={`opp-card ${selected === o.id ? 'selected' : ''}`}
                tabIndex={0}
                role="button"
                aria-pressed={selected === o.id}
                onClick={() => onSelect(o.id)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(o.id); } }}
                title={<span style={{ fontSize: 16 }}>{o.emoji} {o.title}</span>}
                extra={<Tag color="purple">{o.direction}</Tag>}
              >
                <p style={{ fontSize: 13, minHeight: 42 }}>{o.pitch}</p>
                <div style={{ marginBottom: 8 }}>
                  {(o.keywords || []).map(k => <Tag key={k} style={{ whiteSpace: 'normal', wordBreak: 'break-word', maxWidth: '100%', height: 'auto', lineHeight: '1.6' }}>{k}</Tag>)}
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginBottom: 8 }}>建议价格带：<b>{o.priceBand}</b></div>
                <div style={{ borderTop: '1px dashed var(--color-border)', paddingTop: 8 }}>
                  <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>依据链：</div>
                  {(o.evidence || []).map((e, i) => (
                    <Popover key={i} content={e.text} title={e.from}>
                      <Tag color="default" style={{ fontSize: 11, marginBottom: 4, cursor: 'help' }}>
                        {e.from} #{i + 1}
                      </Tag>
                    </Popover>
                  ))}
                </div>
                <Button type={selected === o.id ? 'primary' : 'default'} block style={{ marginTop: 8 }}>
                  {selected === o.id ? '✓ 已选定该方向' : '选定该方向'}
                </Button>
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    </div>
  );
}
